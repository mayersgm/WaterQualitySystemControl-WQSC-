import time
import _thread
import json
from machine import Pin, UART

from scale import Scale
from sensors import Thermistor, TDSSensor

# ---------------------------------------------------------------------------
# Pin map — see Phase0_Design.md
# ---------------------------------------------------------------------------
UART_ID = 0
UART_TX_PIN = 0
UART_RX_PIN = 1
UART_BAUD = 9600       # bench wiring can't reliably carry 115200 -- see Phase0_Design.md

# BENCH TEST PINS (spare WQCS PCB, fixed screw-terminal wiring) -- revert to
# the production pin map (GP10/11/12/13/14) before real deployment (Phase 6).
class ActiveLowOutput:
    """Output for an opto-isolated relay module (817C input stage: LED anode
    to VCC through 1k, cathode to IN), which energizes when IN is pulled LOW.
    Open-drain so "off" releases the pin rather than driving it high, which
    could still leak through the opto LED if the module's VCC is 5V. value()
    takes/returns the logical state (1 = on/energized), like a plain Pin."""

    def __init__(self, pin_num):
        self._pin = Pin(pin_num, Pin.OPEN_DRAIN, value=1)
        self._on = 0

    def value(self, on=None):
        if on is None:
            return self._on
        self._on = 1 if on else 0
        self._pin.value(0 if self._on else 1)


MAIN_VALVE = ActiveLowOutput(19)      # motorized, water main -> boiler, overflow shutoff
REFILL_VALVE = ActiveLowOutput(18)    # 12V solenoid, boiler refill (bench PCB: legacy GP18, DVM-confirmed 2026-09-26)
TRANSFER_VALVE = ActiveLowOutput(21)  # motorized, collector -> reservoir
BOILER_RELAY = Pin(16, Pin.OUT)
# Pressure switch in the segment between the main valve and the refill
# solenoid: when the solenoid is (actually) closed, blocked water builds
# static pressure there and the switch trips; when the solenoid is (actually)
# open, flow relieves that pressure. Only meaningful while the main valve is
# open -- see the stuck-valve cross-check in _control_step.
PRESSURE_SW = Pin(11, Pin.IN, Pin.PULL_UP)
PRESSURE_SW_ACTIVE_HIGH = False  # bench sim relay polarity (GP10/PRESSURE_SIM_RELAY) confirmed 2026-09-27 -- re-verify against the real switch in Phase 6

# BENCH-ONLY SIMULATION -- there is no real pressure switch on the bench yet.
# GP10 drives a second, directly-wired (active-high, not opto) relay whose
# COM feeds GP11/PRESSURE_SW, standing in for a real switch's back-pressure
# signal. It must be pulsed in lockstep with the real refill solenoid (GP18)
# below. Remove PRESSURE_SIM_RELAY and this sync entirely once a real
# pressure switch is wired for Phase 6 -- production reads PRESSURE_SW from
# genuine hardware, nothing drives it from firmware.
PRESSURE_SIM_RELAY = Pin(10, Pin.OUT, value=0)
LED = Pin(25, Pin.OUT)             # core-0 heartbeat

for _pin in (MAIN_VALVE, REFILL_VALVE, TRANSFER_VALVE, BOILER_RELAY):
    _pin.value(0)

# ---------------------------------------------------------------------------
# Weight thresholds, grams post-tare — see Phase0_Design.md sec 3
# ---------------------------------------------------------------------------
BOILER_CAPACITY_G = 3785
# BENCH TEST THRESHOLDS (only ~1-2kg of reference weight available) -- revert
# every value marked "prod:" to the production number before Phase 6.
BOILER_TOPOFF_G = 300          # prod: 3200 -- refill turns on below this (covers cold-start empty too)
BOILER_FULL_G = 600            # prod: 3600 -- refill turns off at/above this
BOILER_OVERFLOW_G = 900        # prod: 3700 -- hard safety cutoff, above the normal FULL target
REFILL_TIMEOUT_S = 90          # BENCH TEST VALUE (10 for the step-6 timeout test) -- revert to 300 before real deployment (Phase 6)

COLLECTOR_CAPACITY_G = 7570
COLLECTOR_EMPTY_G = 100        # prod: 300
COLLECTOR_FULL_G = 500         # prod: 7200

RESERVOIR_CAPACITY_G = 34065
RESERVOIR_FULL_G = 800         # prod: 32000
RESERVOIR_TRANSFER_LOW_G = 400   # prod: 30000 -- "under capacity" trigger to start a transfer

TDS_FAULT_PPM = 50             # carried over from old system's contamination threshold

DEBOUNCE_CONFIRMS = 3           # consecutive control-loop passes to confirm a threshold crossing
LOOP_PERIOD_S = 1.0

# Operator commands. RUN/STANDBY are not commands -- they're reported below
# as derived *state* (what the system is actually doing), since sending RUN
# never did anything distinct in the old protocol (see Phase0_Design.md).
CMD_START, CMD_STOP, CMD_STERILIZE, CMD_EMPTY, CMD_RESET = (
    "START", "STOP", "STERILIZE", "EMPTY", "RESET"
)
KNOWN_CMDS = (CMD_START, CMD_STOP, CMD_STERILIZE, CMD_EMPTY, CMD_RESET)

# Reported state values (status "state" field, not operator-settable)
STATE_FAULT = "FAULT"
STATE_STOPPED = "STOPPED"
STATE_EMPTY = "EMPTY"
STATE_STANDBY = "STANDBY"      # collector AND reservoir both full -- paused
STATE_RUN = "RUN"              # actively distilling or sterilizing
STATE_IDLE = "IDLE"            # commanded START but not yet heating (e.g. boiler still filling)


class Debounce:
    """Requires N consecutive true readings before confirming a condition.
    Prevents a single noisy/mid-transition sensor sample from tripping a
    valve or fault decision (see Phase 1 calibration notes)."""

    def __init__(self, confirms=DEBOUNCE_CONFIRMS):
        self.confirms = confirms
        self.count = 0

    def check(self, condition):
        self.count = self.count + 1 if condition else 0
        return self.count >= self.confirms


class Wqcs:
    def __init__(self):
        self.scales = {
            "boiler": Scale("boiler", 2, 3),
            "collector": Scale("collector", 4, 5),
            "reservoir": Scale("reservoir", 6, 7),
        }
        self.thermistor = Thermistor(adc_pin=26)
        self.tds1 = TDSSensor("tds1", adc_pin=27)   # distiller -> collector
        self.tds2 = TDSSensor("tds2", adc_pin=28)   # distribution pump outlet

        self.cmd = CMD_STOP     # safe default until the operator sends START
        self._pending = []
        self._pending_lock = _thread.allocate_lock()

        self.heater_on = False
        self.refill_open = False
        self.refill_started_at = None
        self.transfer_active = False

        # Recoverable faults (need ACK/RESET to clear)
        self.fault_tds1 = False
        self.fault_overflow = False
        self.fault_refill_timeout = False
        self.fault_valve_stuck = False
        # Informational only, non-latching
        self.alert_tds2 = False

        self._db_boiler_full = Debounce()
        self._db_boiler_topoff = Debounce()
        self._db_boiler_overflow = Debounce()
        self._db_collector_full = Debounce()
        self._db_collector_empty = Debounce()
        self._db_reservoir_full = Debounce()
        self._db_reservoir_low = Debounce()
        self._db_tds1_fault = Debounce()
        self._db_tds2_alert = Debounce()
        self._db_valve_stuck_open = Debounce()    # commanded closed, pressure still says flowing
        self._db_valve_stuck_closed = Debounce()  # commanded open, pressure still says blocked

        self.last_status = {}

    # -- command queue: core 1 (UART) is the producer, core 0 the consumer --
    def queue_command(self, line):
        with self._pending_lock:
            self._pending.append(line)

    def _drain_commands(self):
        with self._pending_lock:
            cmds, self._pending = self._pending, []
        for line in cmds:
            self._handle_command(line)

    def _handle_command(self, line):
        line = line.strip().upper()
        if not line:
            return
        parts = line.split(":")
        verb = parts[0]

        if verb in KNOWN_CMDS:
            self.cmd = verb
            if verb == CMD_RESET:
                self.fault_tds1 = False
                self.fault_overflow = False
                self.fault_refill_timeout = False
                self.fault_valve_stuck = False

        elif verb == "TARE" and len(parts) == 2:
            name = parts[1].lower()
            if name in self.scales:
                self.scales[name].tare()

        elif verb == "CAL" and len(parts) == 3:
            name = parts[1].lower()
            if name in self.scales:
                try:
                    self.scales[name].calibrate(float(parts[2]))
                except (ValueError, RuntimeError) as e:
                    print(f"CAL error: {e}")

        elif verb == "ACK":
            self.fault_tds1 = False
            self.fault_overflow = False
            self.fault_refill_timeout = False
            self.fault_valve_stuck = False

    # -- main control loop (core 0) ------------------------------------------
    def run(self):
        _thread.start_new_thread(self._uart_thread, ())
        while True:
            self._drain_commands()
            self._control_step()
            time.sleep(LOOP_PERIOD_S)

    def _control_step(self):
        try:
            boiler_g = self.scales["boiler"].read_grams()
            collector_g = self.scales["collector"].read_grams()
            reservoir_g = self.scales["reservoir"].read_grams()
            temp_f = self.thermistor.read_fahrenheit()
            tds1_ppm = self.tds1.read_ppm()
            tds2_ppm = self.tds2.read_ppm()
            pressure_detected = bool(PRESSURE_SW.value()) == PRESSURE_SW_ACTIVE_HIGH
        except Exception as e:
            # A flaky/disconnected sensor must not leave actuators in a
            # stale or unknown state — force everything off and retry
            # next loop rather than crashing core 0.
            print(f"Sensor read error: {e}")
            MAIN_VALVE.value(0)
            REFILL_VALVE.value(0)
            TRANSFER_VALVE.value(0)
            BOILER_RELAY.value(0)
            self.heater_on = False
            self.refill_open = False
            self.transfer_active = False
            return

        # Only START drives the fill/refill/transfer maintenance loop.
        # STERILIZE uses whatever water is already in the boiler; STOP/EMPTY/
        # RESET park everything.
        active = self.cmd == CMD_START

        # ---- debounced condition checks ------------------------------------
        boiler_overflow = self._db_boiler_overflow.check(boiler_g >= BOILER_OVERFLOW_G)
        boiler_full = self._db_boiler_full.check(boiler_g >= BOILER_FULL_G)
        boiler_topoff = self._db_boiler_topoff.check(boiler_g < BOILER_TOPOFF_G)
        collector_full = self._db_collector_full.check(collector_g >= COLLECTOR_FULL_G)
        collector_empty = self._db_collector_empty.check(collector_g <= COLLECTOR_EMPTY_G)
        reservoir_full = self._db_reservoir_full.check(reservoir_g >= RESERVOIR_FULL_G)
        reservoir_low = self._db_reservoir_low.check(reservoir_g < RESERVOIR_TRANSFER_LOW_G)
        tds1_bad = self._db_tds1_fault.check(tds1_ppm >= TDS_FAULT_PPM)
        tds2_bad = self._db_tds2_alert.check(tds2_ppm >= TDS_FAULT_PPM)

        # ---- safety interlocks, checked every loop, independent of state --
        if boiler_overflow:
            self.fault_overflow = True
        if tds1_bad:
            self.fault_tds1 = True
        self.alert_tds2 = tds2_bad  # non-latching, informational only

        # STANDBY condition: nowhere for more distillate to go. If the
        # collector still has room, distillation can continue even with the
        # reservoir full (collector just holds output until a transfer opens
        # up room again) -- only pause once *both* are full.
        downstream_full = collector_full and reservoir_full

        main_close = (
            self.fault_overflow or self.fault_tds1 or self.fault_refill_timeout
            or self.fault_valve_stuck or downstream_full or not active
        )

        # ---- boiler fill: main valve stays open through the whole sequence,
        # the refill solenoid does the actual metering -----------------------
        MAIN_VALVE.value(0 if main_close else 1)

        want_refill = (not main_close) and (not boiler_full) and boiler_topoff
        if want_refill and not self.refill_open:
            self.refill_open = True
            self.refill_started_at = time.ticks_ms()
        if self.refill_open and (boiler_full or main_close):
            self.refill_open = False
            self.refill_started_at = None
        if self.refill_open and self.refill_started_at is not None:
            if time.ticks_diff(time.ticks_ms(), self.refill_started_at) > REFILL_TIMEOUT_S * 1000:
                self.fault_refill_timeout = True
                self.refill_open = False
                self.refill_started_at = None
        REFILL_VALVE.value(1 if self.refill_open else 0)
        PRESSURE_SIM_RELAY.value(1 if self.refill_open else 0)  # BENCH-ONLY, see note above

        # ---- stuck-solenoid cross-check via the pressure switch --------------
        # Only meaningful with the main valve actually open (source pressure
        # present); with it closed there's nothing to read either way.
        if not main_close:
            stuck_open = self._db_valve_stuck_open.check(not self.refill_open and not pressure_detected)
            stuck_closed = self._db_valve_stuck_closed.check(self.refill_open and pressure_detected)
            if stuck_open or stuck_closed:
                self.fault_valve_stuck = True
        else:
            self._db_valve_stuck_open.check(False)
            self._db_valve_stuck_closed.check(False)

        # ---- heater, dry-tank protected (never heat below the empty floor) --
        # STANDBY (downstream full) only pauses production (START); it
        # doesn't apply to STERILIZE, which doesn't produce collectible output.
        self.heater_on = (
            ((self.cmd == CMD_START and not downstream_full) or self.cmd == CMD_STERILIZE)
            and not self.fault_tds1
            and not self.fault_overflow
            and not self.fault_refill_timeout
            and not self.fault_valve_stuck
            and boiler_g >= 200
        )
        BOILER_RELAY.value(1 if self.heater_on else 0)

        # ---- collector -> reservoir transfer, gated on system being active --
        if not self.transfer_active and active and collector_full and reservoir_low:
            self.transfer_active = True
        if self.transfer_active and (not active or collector_empty or reservoir_full):
            self.transfer_active = False
        TRANSFER_VALVE.value(1 if self.transfer_active else 0)

        # ---- derived state, reported for the HMI/monitor --------------------
        if self.fault_tds1 or self.fault_overflow or self.fault_refill_timeout or self.fault_valve_stuck:
            state = STATE_FAULT
        elif self.cmd == CMD_STOP:
            state = STATE_STOPPED
        elif self.cmd == CMD_EMPTY:
            state = STATE_EMPTY
        elif self.cmd == CMD_START and downstream_full:
            state = STATE_STANDBY
        elif self.heater_on:
            state = STATE_RUN
        else:
            state = STATE_IDLE

        self.last_status = {
            "cmd": self.cmd,
            "state": state,
            "temp_f": temp_f,
            "tds1_ppm": round(tds1_ppm, 1),
            "tds2_ppm": round(tds2_ppm, 1),
            "boiler_g": round(boiler_g, 1),
            "collector_g": round(collector_g, 1),
            "reservoir_g": round(reservoir_g, 1),
            "boiler_pct": round(boiler_g / BOILER_CAPACITY_G * 100, 1),
            "collector_pct": round(collector_g / COLLECTOR_CAPACITY_G * 100, 1),
            "reservoir_pct": round(reservoir_g / RESERVOIR_CAPACITY_G * 100, 1),
            "valves": {
                "main": MAIN_VALVE.value(),
                "refill": REFILL_VALVE.value(),
                "transfer": TRANSFER_VALVE.value(),
            },
            "pressure_sw": pressure_detected,
            "heater": int(self.heater_on),
            "fault": {
                "tds1": self.fault_tds1,
                "overflow": self.fault_overflow,
                "refill_timeout": self.fault_refill_timeout,
                "valve_stuck": self.fault_valve_stuck,
            },
            "alert": {"tds2": self.alert_tds2},
        }
        # Local print on the Pico's own USB console -- independent of the
        # ESP32 UART link, so bench verification works even while that
        # link's telemetry direction is unreliable (see Phase0_Design.md).
        print(self.last_status)
        LED.value(not LED.value())

    # -- UART link to ESP32-S3 (core 1) --------------------------------------
    def _uart_thread(self):
        uart = UART(UART_ID, baudrate=UART_BAUD, tx=Pin(UART_TX_PIN), rx=Pin(UART_RX_PIN))
        buf = b""
        last_status_send = time.ticks_ms()
        while True:
            if uart.any():
                buf += uart.read()
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        self.queue_command(line.decode().strip())
                    except UnicodeError:
                        pass

            now = time.ticks_ms()
            if time.ticks_diff(now, last_status_send) >= 1000:
                if self.last_status:
                    uart.write(json.dumps(self.last_status).encode() + b"\n")
                last_status_send = now

            time.sleep_ms(50)


if __name__ == "__main__":
    Wqcs().run()
