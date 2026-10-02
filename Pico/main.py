import time
import _thread
import json
from machine import Pin, UART

from scale import Scale
from sensors import Thermistor, TDSSensor
from limits import Limits

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



def all_outputs_off():
    """Fail-safe: heater off, every valve closed. Safe to call from either core."""
    for pin in (MAIN_VALVE, REFILL_VALVE, TRANSFER_VALVE, BOILER_RELAY, PRESSURE_SIM_RELAY):
        pin.value(0)


all_outputs_off()

# ---------------------------------------------------------------------------
# Weight thresholds, grams post-tare — see Phase0_Design.md sec 3
# ---------------------------------------------------------------------------
BOILER_CAPACITY_G = 3785
COLLECTOR_CAPACITY_G = 7570
RESERVOIR_CAPACITY_G = 34065

# Fixed safety limits -- NOT operator-adjustable.
# BENCH TEST VALUES (only ~1-2kg of reference weight available) -- revert
# every value marked "prod:" to the production number before Phase 6.
BOILER_OVERFLOW_G = 900        # prod: 3700 -- hard safety cutoff, above any FULL setpoint
COLLECTOR_OVERFLOW_G = 900     # prod: 7400 -- catches a transfer valve stuck closed
RESERVOIR_OVERFLOW_G = 1200    # prod: 33500 -- catches a transfer valve stuck open
DRY_TANK_FLOOR_G = 200         # heater never runs below this boiler weight
REFILL_TIMEOUT_S = 90          # prod: 300 (10 for the step-6 timeout test)

# Transfer-valve leak check (no timing -- gravity flow can be arbitrarily
# slow). With the transfer closed the collector can only gain weight and the
# reservoir can only gain by leaking, so a drop from the collector's peak AND
# a rise from the reservoir's low point since closing means it's passing water.
LEAK_DROP_G = 300
LEAK_RISE_G = 150

# Default fill/drain setpoints, used until the operator changes them from the
# HMI (SET:...), which persists them to limits.json -- see limits.py.
DEFAULT_LIMITS = {
    "boiler_topoff": 300,      # prod: 3200 -- refill turns on below this (covers cold-start empty too)
    "boiler_full": 600,        # prod: 3600 -- refill turns off at/above this
    "collector_empty": 100,    # prod: 300
    "collector_full": 500,     # prod: 7200
    "reservoir_full": 1000,    # prod: 32000 -- usable reservoir capacity for the transfer rule
                               #   (must be >= COLLECTOR_OVERFLOW_G, see limits.py)
}

FAULT_KEYS = ("tds1", "overflow", "refill_timeout", "valve_stuck",
              "collector_overflow", "reservoir_overflow", "transfer_leak",
              "controller")   # control loop raised or stalled (see loop_once/supervise)

TDS_FAULT_PPM = 50             # carried over from old system's contamination threshold

DEBOUNCE_CONFIRMS = 3           # consecutive control-loop passes to confirm a threshold crossing
LOOP_PERIOD_S = 1.0
# Core 1 forces every output off and stops sending status if core 0's control
# loop hasn't completed a pass for this long (a blocked sensor read, or core 0
# dead after an uncaught exception). Before 2026-10-01, core 1 kept re-sending
# the last status with the heater on while nothing was enforcing the interlocks.
STALL_MS = 5000

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

        self.limits = Limits(
            DEFAULT_LIMITS,
            {"boiler": BOILER_OVERFLOW_G, "collector": COLLECTOR_OVERFLOW_G,
             "reservoir": RESERVOIR_OVERFLOW_G},
            DRY_TANK_FLOOR_G,
        )

        self.cmd = CMD_STOP     # safe default until the operator sends START
        self._pending = []
        self._pending_lock = _thread.allocate_lock()
        # One-off reply lines (e.g. limits) queued by core 0 for core 1 to send
        self._outbox = []
        self._outbox_lock = _thread.allocate_lock()

        self.heater_on = False
        self.refill_open = False
        self.refill_started_at = None
        self.transfer_active = False
        # leak-check references, re-armed whenever the transfer valve closes
        self._leak_ref_collector = None
        self._leak_ref_reservoir = None

        # Recoverable faults (need ACK/RESET to clear). Any latched fault stops
        # distillation: main valve closed, refill and heater off.
        self.faults = {k: False for k in FAULT_KEYS}
        # Informational only, non-latching
        self.alert_tds2 = False

        self._db_boiler_full = Debounce()
        self._db_boiler_topoff = Debounce()
        self._db_boiler_overflow = Debounce()
        self._db_collector_full = Debounce()
        self._db_collector_empty = Debounce()
        self._db_reservoir_full = Debounce()
        self._db_collector_overflow = Debounce()
        self._db_reservoir_overflow = Debounce()
        self._db_transfer_fits = Debounce()   # reservoir can take the whole collector
        self._db_transfer_leak = Debounce()
        self._db_tds1_fault = Debounce()
        self._db_tds2_alert = Debounce()
        self._db_valve_stuck_open = Debounce()    # commanded closed, pressure still says flowing
        self._db_valve_stuck_closed = Debounce()  # commanded open, pressure still says blocked

        self.last_status = {}
        self._beat = time.ticks_ms()   # core 0 heartbeat, written once per pass
        self._stalled = False          # set by core 1 when the heartbeat goes stale

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
                self._clear_faults()

        elif verb == "TARE" and len(parts) == 2:
            name = parts[1].lower()
            if name in self.scales:
                self.scales[name].tare()
                self._leak_ref_collector = None  # weights jumped; re-arm leak check
                self._leak_ref_reservoir = None

        elif verb == "CAL" and len(parts) == 3:
            name = parts[1].lower()
            if name in self.scales:
                try:
                    self.scales[name].calibrate(float(parts[2]))
                except (ValueError, RuntimeError) as e:
                    print(f"CAL error: {e}")

        elif verb == "ACK":
            self._clear_faults()

        # SET:<KEY>:<g>  or atomically  SET:<KEY>=<g>,<KEY>=<g>,...
        elif verb == "SET" and len(parts) in (2, 3):
            try:
                if len(parts) == 3:
                    changes = {parts[1].lower(): float(parts[2])}
                else:
                    changes = {}
                    for item in parts[1].split(","):
                        k, v = item.split("=")
                        changes[k.strip().lower()] = float(v)
                err = self.limits.update(changes)
            except ValueError:
                err = "malformed SET"
            self._reply_limits(err)

        # TDSCAL:TDS1 / TDSCAL:TDS2 -- zero the probe (must be in clean water)
        elif verb == "TDSCAL" and len(parts) == 2:
            sensor = {"TDS1": self.tds1, "TDS2": self.tds2}.get(parts[1])
            if sensor is None:
                self._reply({"tdscal": {"sensor": parts[1].lower(), "ok": False,
                                        "err": "unknown sensor"}})
            else:
                try:
                    v = sensor.calibrate_zero()
                    self._reply({"tdscal": {"sensor": sensor.name, "ok": True,
                                            "offset_v": round(v, 4)}})
                except ValueError as e:
                    self._reply({"tdscal": {"sensor": sensor.name, "ok": False,
                                            "err": str(e)}})

        elif verb == "GET" and len(parts) == 2 and parts[1] == "LIMITS":
            self._reply_limits(None)

        elif verb == "RESET_LIMITS":
            self.limits.reset()
            self._reply_limits(None)

    def _check_transfer_leak(self, collector_g, reservoir_g):
        """True (debounced) if the closed transfer valve is passing water.

        While closed, track the collector's peak and the reservoir's low point;
        distillate only raises the collector and the pump only lowers the
        reservoir, so a collector drop plus a reservoir rise from those marks
        means water is moving between them. Pump draw can only hide a leak
        (the overflow faults are the backstop), never fake one."""
        if self.transfer_active:
            self._db_transfer_leak.check(False)
            return False
        if self._leak_ref_collector is None:
            self._leak_ref_collector = collector_g
            self._leak_ref_reservoir = reservoir_g
        self._leak_ref_collector = max(self._leak_ref_collector, collector_g)
        self._leak_ref_reservoir = min(self._leak_ref_reservoir, reservoir_g)
        leaking = (self._leak_ref_collector - collector_g >= LEAK_DROP_G and
                   reservoir_g - self._leak_ref_reservoir >= LEAK_RISE_G)
        return self._db_transfer_leak.check(leaking)

    def _clear_faults(self):
        for k in self.faults:
            self.faults[k] = False
        # after a leak ACK, judge any further leaking from the current weights
        self._leak_ref_collector = None
        self._leak_ref_reservoir = None

    def _reply_limits(self, err):
        self._reply({"limits": self.limits.values, "ok": err is None, "err": err})

    def _reply(self, msg):
        """Queue a one-off reply line for core 1 to send to the ESP32."""
        print(msg)
        with self._outbox_lock:
            self._outbox.append(json.dumps(msg).encode() + b"\n")

    # -- main control loop (core 0) ------------------------------------------
    def run(self):
        _thread.start_new_thread(self._uart_thread, ())
        while True:
            self.loop_once()
            time.sleep(LOOP_PERIOD_S)

    def loop_once(self):
        """One control pass. Never raises: an error leaves every output off
        and latches the 'controller' fault (ACK to clear) instead of killing
        core 0 while core 1 keeps reporting stale status."""
        if self._stalled:
            # core 1 already forced the outputs off while this loop was stuck
            self._stalled = False
            self.faults["controller"] = True
            print("control loop was stalled; outputs had been forced off")
        try:
            self._drain_commands()
            self._control_step()
        except Exception as e:
            print("control loop error:", repr(e))
            all_outputs_off()
            self.heater_on = self.refill_open = self.transfer_active = False
            self.refill_started_at = None
            self.faults["controller"] = True
            self.last_status = dict(self.last_status, state=STATE_FAULT, heater=0,
                                    valves={"main": 0, "refill": 0, "transfer": 0},
                                    fault=dict(self.faults))
        self._beat = time.ticks_ms()

    def supervise(self, now):
        """Core 1, every pass: True while core 0's control loop is alive. If it
        has stalled, keep every output off; the caller stops sending status so
        the ESP32 shows NO LINK (and pushes a phone alert) rather than frozen
        values."""
        if time.ticks_diff(now, self._beat) <= STALL_MS:
            return True
        all_outputs_off()
        if not self._stalled:
            self._stalled = True
            print("control loop stalled > %d ms; outputs forced off" % STALL_MS)
        return False

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
        lim = self.limits
        boiler_full = self._db_boiler_full.check(boiler_g >= lim["boiler_full"])
        boiler_topoff = self._db_boiler_topoff.check(boiler_g < lim["boiler_topoff"])
        collector_full = self._db_collector_full.check(collector_g >= lim["collector_full"])
        collector_empty = self._db_collector_empty.check(collector_g <= lim["collector_empty"])
        reservoir_full = self._db_reservoir_full.check(reservoir_g >= lim["reservoir_full"])
        # Capacity rule: a transfer only starts if the reservoir can take the
        # collector's entire contents (gravity flow may be slow, so this is
        # decided by weight up front rather than by timing the transfer).
        fits = collector_g + reservoir_g <= lim["reservoir_full"]
        transfer_fits = self._db_transfer_fits.check(fits)
        tds1_bad = self._db_tds1_fault.check(tds1_ppm >= TDS_FAULT_PPM)
        tds2_bad = self._db_tds2_alert.check(tds2_ppm >= TDS_FAULT_PPM)

        # ---- safety interlocks, checked every loop, independent of state --
        if boiler_overflow:
            self.faults["overflow"] = True
        if self._db_collector_overflow.check(collector_g >= COLLECTOR_OVERFLOW_G):
            self.faults["collector_overflow"] = True   # e.g. transfer stuck closed
        if self._db_reservoir_overflow.check(reservoir_g >= RESERVOIR_OVERFLOW_G):
            self.faults["reservoir_overflow"] = True   # e.g. transfer stuck open
        if tds1_bad:
            self.faults["tds1"] = True
        if self._check_transfer_leak(collector_g, reservoir_g):
            self.faults["transfer_leak"] = True
        self.alert_tds2 = tds2_bad  # non-latching, informational only
        any_fault = any(self.faults.values())

        # STANDBY: the collector is at/above FULL, whatever the reservoir holds
        # (little headroom above FULL, and a gravity transfer can be slow).
        # Production pauses; if the whole collector fits in the reservoir the
        # transfer drains it meanwhile, and production resumes once the
        # collector drops below FULL. If it doesn't fit, STANDBY holds until
        # the reservoir is drawn down.
        downstream_full = collector_full

        main_close = any_fault or downstream_full or not active

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
                self.faults["refill_timeout"] = True
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
                self.faults["valve_stuck"] = True
        else:
            self._db_valve_stuck_open.check(False)
            self._db_valve_stuck_closed.check(False)

        # ---- heater, dry-tank protected (never heat below the empty floor) --
        # STANDBY (downstream full) only pauses production (START); it
        # doesn't apply to STERILIZE, which doesn't produce collectible output.
        self.heater_on = (
            ((self.cmd == CMD_START and not downstream_full) or self.cmd == CMD_STERILIZE)
            and not any_fault
            and boiler_g >= DRY_TANK_FLOOR_G
        )
        BOILER_RELAY.value(1 if self.heater_on else 0)

        # ---- collector -> reservoir transfer, gated on system being active --
        # Blocked while the collector may hold bad water (TDS-1) or the
        # transfer path itself is suspect (leak / reservoir overflow). A
        # collector overflow does NOT block it: transferring relieves it.
        blocked = (self.faults["tds1"] or self.faults["transfer_leak"]
                   or self.faults["reservoir_overflow"])
        if (not self.transfer_active and active and not blocked
                and collector_full and transfer_fits):
            self.transfer_active = True
            self._leak_ref_collector = self._leak_ref_reservoir = None
        if self.transfer_active and (not active or blocked or collector_empty or reservoir_full):
            self.transfer_active = False
        TRANSFER_VALVE.value(1 if self.transfer_active else 0)

        # ---- derived state, reported for the HMI/monitor --------------------
        if any_fault:
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
            "valves": {
                "main": MAIN_VALVE.value(),
                "refill": REFILL_VALVE.value(),
                "transfer": TRANSFER_VALVE.value(),
            },
            "pressure_sw": pressure_detected,
            "heater": int(self.heater_on),
            "fault": dict(self.faults),
            "alert": {"tds2": self.alert_tds2},
        }
        # Local print on the Pico's own USB console -- independent of the
        # ESP32 UART link, so bench verification works even while that
        # link's telemetry direction is unreliable (see Phase0_Design.md).
        print(self.last_status)
        LED.value(not LED.value())

    # -- UART link to ESP32-S3 (core 1) --------------------------------------
    def _uart_thread(self):
        # txbuf must exceed one status line: rp2's uart.write() queues only
        # what fits in the TX ring buffer (default 256B + 32B FIFO) and
        # silently drops the rest, which truncated every ~400B status line.
        uart = UART(UART_ID, baudrate=UART_BAUD, tx=Pin(UART_TX_PIN), rx=Pin(UART_RX_PIN),
                    txbuf=1024, rxbuf=256)
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

            with self._outbox_lock:
                replies, self._outbox = self._outbox, []
            for line in replies:
                self._write_all(uart, line)

            now = time.ticks_ms()
            alive = self.supervise(now)
            if time.ticks_diff(now, last_status_send) >= 1000:
                if self.last_status and alive:
                    self._write_all(uart, json.dumps(self.last_status).encode() + b"\n")
                last_status_send = now

            time.sleep_ms(50)

    @staticmethod
    def _write_all(uart, data):
        mv = memoryview(data)
        while mv:
            n = uart.write(mv) or 0
            mv = mv[n:]
            if not n:
                time.sleep_ms(5)


if __name__ == "__main__":
    Wqcs().run()
