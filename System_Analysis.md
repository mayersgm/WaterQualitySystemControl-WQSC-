# WQCS (Water Quality Control System) — Current System Analysis

## 1. Overall Architecture

The system is a two-controller design connected over I2C:

| Role | Device | File | Responsibility |
|---|---|---|---|
| **Controller (I2C master / HMI)** | Adafruit PyPortal | `code.py` | Touchscreen UI, operator commands, status display, does **no** control logic itself |
| **Responder (I2C target / brains)** | Raspberry Pi Pico (RP2040, MicroPython) | `main.py` | Reads all sensors/switches, runs the state machine, drives all relays/valves |
| **Low-level I2C driver** | Pico | `I2C_Responder.py` | Bit/register-level implementation of an I2C *target* (slave) mode, because stock MicroPython (as of when this was written) had no native I2C slave/responder support |

**Why this split exists:** MicroPython on the RP2040 didn't support I2C peripheral (slave) mode natively, so `I2C_Responder.py` pokes the RP2040's I2C hardware registers directly (`IC_SAR`, `IC_CON`, `IC_DATA_CMD`, `IC_RAW_INTR_STAT`, GPIO function-select registers, etc.) to make the Pico answer as an I2C target at address `0x41`. The PyPortal is the I2C bus **controller**: every ~1 second it writes a 1-byte command to the Pico, then reads back a fixed 96-byte buffer containing a JSON status string.

### Command protocol (shared constants in both files)
```
RUN       0x11  autonomous/idle polling mode
START     0x12  begin distillation
STANDBY   0x13  (defined, unused in current logic)
STOP      0x14  halt any active function
STERILIZE 0x15  run boiler sterilization cycle
EMPTY     0x16  drain boiler for cleaning
RESET     0x17  re-initialize Pico to default state
```

### Status JSON (Pico → PyPortal)
```json
{"t": "<temp °F>", "d": <TDS ppm>, "b": <boiler pwr 0/1>, "r": <reservoir level 0-3>,
 "f": <water flow 0/1>, "ref_active": <bool>, "ref_count": <seconds left>, "e": <error 0/1>}
```

---

## 2. Device-by-Device Roles

### 2.1 Boiler limit switches (2x float switches — "boiler empty/full")
- **Hardware:** `BOILER_TANK_LIMIT_LO` (GP10) and `BOILER_TANK_LIMIT_HI` (GP11), both `Pin.IN` with internal pull-ups.
- **Read via:** `PyPicoIO.pico2040(port=6)` (`B_limL`/`B_limH`).
- **Decode logic:**
  - LO=1 & HI=1 → returns `3`
  - LO=1 & HI=0 → returns `1`
  - HI=1 (LO=0) → returns `2`
  - both 0 → returns `0`
- **How it's used:** `distillation_process()`'s `boiler_waterlevel_state` compares this reading against `MIN_LIMIT (0x02)`, `MID_LIMIT (0x03)`, `MAX_LIMIT (0x01)`:
  - Reading == `MIN_LIMIT` (boiler at/near empty) → opens the refill valve with a **long timeout (`T_LONG` = 300 s)**, because the tank is starting from empty and needs a full fill.
  - Reading == `MID_LIMIT` (partial level, i.e. mid-cycle depletion during distillation) → opens the refill valve with a **short timeout (`T_SHORT` = 30 s)** — a "top-off" refill.
  - Reading == `MAX_LIMIT` (boiler full) → if the boiler heater is on, it's told to shut off (`boiler_on(False)`) before moving on to check the reservoir.
- **Purpose:** These two switches let the firmware distinguish three tank states (empty / partially depleted / full) using only two single-point float switches, and choose an appropriately-scaled refill timeout for each case rather than a single fixed timer — this bounds how long the fill solenoid can stay open if the float mechanism sticks (see `refill_error()` failsafe below).
- **Note:** The constant names (`MIN_LIMIT=0x02`, `MID_LIMIT=0x03`, `MAX_LIMIT=0x01`) don't map monotonically to the switch-combination return values (`0,1,2,3`) in an obvious way — worth double-checking wiring/logic when redesigning, since this is one of the more fragile/confusing parts of the current code.

### 2.2 Heater switch (Boiler power relay)
- **Hardware:** `BOILER_POWER` (GP16, `Pin.OUT`, pulled down, default `False`) — drives a relay/SSR presumably switching AC power to the boiler heating element.
- **Companion pin:** `BOILER_WATER_VALVE` (GP19, open-drain) is toggled to the **inverse** of the boiler power command inside `pico2040(port=2)`: `BOILER_WATER_VALVE.value(not cmd)`. So turning the heater ON closes this valve, and turning it OFF opens it — this looks like a safety interlock so the boiler can't be actively supplying water/pumping while the heating element is energized (or vice versa, depending on valve's normally-open/closed wiring).
- **Controlled by:** `Wqcs_Mcu.boiler_on(sw)` — the single choke point for turning the heater on/off. When switched off, it also forces the cooling fan output off and clears `status_reg["FAN"]`.
- **Decision logic:** `reservoir_status()` and `cmd_status()` turn the boiler on when a `START`/`STANDBY`-ish command is active and the reservoir isn't full, and turn it off when the reservoir is full or the command is `STOP`. The `boiler_waterlevel_state` also force-shuts it off once the boiler tank read is `MAX_LIMIT` and water is still flowing (to avoid dry/over-boil condition once tank hits max and downstream flow stops).
- **Purpose:** Central "is the distillation actually cooking" actuator, gated by both tank level, reservoir level, and the active command from the PyPortal.

### 2.3 Water reservoir dual float level sensors
- **Hardware:** `RESERVOIR_TANK_LIMIT_LO` (GP13) and `RESERVOIR_TANK_LIMIT_HI` (GP12), pull-up inputs — the *distilled water* output reservoir, separate from the boiler.
- **Read via:** `pico2040(port=4)` using the same 2-switch encoding as the boiler (returns 0–3).
- **Mapped to human levels:** `get_reservoir_level()` translates the raw port-4 reading (`FULL=3`, `FIRST_LEVEL=2`, `SECOND_LEVEL=1`, `BELOW_LEVEL=0`) into the `"r"` field of the status JSON, which the PyPortal displays as `Empty/Low/Medium/Full`.
- **Purpose:**
  - Drives the main state machine decision of whether to keep distilling (`reservoir_waterlevel_state`) — if the reservoir is full, the boiler is shut off and system effectively pauses (`reservoir_status()` sets `RESERVOIR = FULL`, calls `boiler_on(False)`).
  - On the PyPortal side, when in `STANDBY` for longer than `standby_resume_time` (5 min) it checks reservoir fullness before **auto-resuming distillation** — i.e. the reservoir sensor is what tells the system "there's now room to keep distilling" after water has been drawn off.

### 2.4 Cooling fan control — **disabled**
- **Hardware:** `COOLING_FAN` (GP17, `Pin.OUT`, pulled down). Initialized to `.value(True)` at boot (default state) and driven via `pico2040(port=3)`.
- **Current state:** All the code paths that would actually decide to turn the fan on/off are commented out:
  ```python
  # self.pi.pico2040(FAN, True)
  # status_reg["FAN"]= True
  ```
  in `coolingfan_state`, and the PyPortal's status field `"f"` is simply read and shown but never drives a control decision. `boiler_on(False)` does actively turn the fan **off** (that path is live), but nothing in the current firmware ever commands it **on** — confirming the note that fan control has been disabled. It's effectively along for the ride: wired, defaulted to a fixed state, but not actively cycled by the control loop.
- **Likely original intent:** Turn on a condenser/cooling fan whenever boiler temperature is below `TEMP_LIMIT1` (150°F) presumably to aid condensing vapor into the reservoir, and turn off otherwise/when boiler is off.

### 2.5 Supporting sensors/actuators (context for the above)
- **Boiler refill valve** (`BOILER_REFILL_VALVE`, GP18, open-drain) — solenoid opened by `refill_boiler()` to add water to the boiler, closed on timeout or on reaching `MAX_LIMIT`. Governed by the two boiler float switches (2.1).
- **Boiler drain valve** (`BOILER_DRAIN_VALVE`, GP21, open-drain) — opened during `EMPTY` command to drain the boiler for cleaning; closed once command changes away from `EMPTY`.
- **Water flow switch** (`WATER_FLOW_SW`, GP28) — a flow sensor/paddle switch reporting whether water is currently flowing (`"f"` in status JSON); used in `boiler_waterlevel_state` to decide if boiler-off is warranted once tank is full.
- **NTC thermistor temperature sensor** (ADC26) — boiler temperature via Steinhart-Hart equation, reported in °F; used for the cooling-fan decision (currently inert) and general status display.
- **TDS (Total Dissolved Solids) sensor** (ADC28) — measures water quality of the distillate via a median-filtered, temperature-compensated polynomial curve; calibrated/offset value persisted to `tds_cal.txt` on the Pico's flash. If TDS ≥ 50 ppm, `tds_status()` treats this as a contamination fault: shuts the boiler off, closes the refill valve, and **latches into an infinite error loop** requiring a physical reset/power-cycle (no path back out of that `while True` other than restart) — this is a significant existing failure mode worth revisiting in a redesign.
- **Refill timeout errors** — similarly, `refill_error()` (triggered if the boiler doesn't reach `MAX_LIMIT` within its allotted timer) also spins forever in an error loop; only the PyPortal's `handle_refill_error()` polls for a touchscreen RESET press to escape it (Pico side has no way out except restart).

---

## 3. Control Flow Summary

1. **PyPortal (`code.py`)** — Every ~1 s, `read_status()` writes the *current selected command byte* to the Pico over I2C, then reads the 96-byte JSON buffer back. It never runs any control decisions itself; buttons just change which command byte gets sent (`RUN` when idle, `START`/`STERILIZE`/`EMPTY` when a button is toggled active, `STOP` to cancel, `RESET` to fully reinitialize). It also independently tracks elapsed-time timers for display (distillation/sterilization/standby/refill) and has a client-side "auto-resume from standby after 5 min if reservoir isn't full" behavior.
2. **Pico (`main.py`)** — On its second core (`_thread`), `I2C_Slave.get_i2c_cmd()` continuously services the I2C responder: pulls in the latest command byte, stores it as `status_reg["CMD"]`, and pushes back the latest JSON status. On the main core, `distillation_process()` runs a state machine (`system_status_state → boiler_waterlevel_state → reservoir_waterlevel_state → coolingfan_state → back to system_status_state`, or straight to `boiler_waterlevel_state`/`reservoir_waterlevel_state` depending on `cmd_status()`), continuously re-evaluating: current command, boiler tank level, reservoir level, TDS safety check (every loop), and (nominally, though currently disabled) cooling fan state.
3. **Failure handling** is currently "fail-stop": TDS contamination and refill timeouts each put the Pico into a permanent polling loop with `status_reg["ERROR"]=True`; only a manual RESET (power cycle or Pico-side restart, since there's no in-loop way for the Pico's error loops to receive a fresh command over the already-busy thread) clears it. The PyPortal reflects this by flashing red/beeping until a screen RESET press is detected.

---

## 4. Notable Existing Issues (for awareness before any redesign)

- `main.py` line 228 contains `time.sleep(0.5)VREF` — this is a syntax error as written (a stray token appended to a valid statement) and would prevent the file from parsing/running as shown. Either the copy has been altered in transit or there's a local variant that removed it — worth confirming which version is actually flashed to the device.
- The boiler-level constant names (`MIN_LIMIT`/`MID_LIMIT`/`MAX_LIMIT` = `0x02`/`0x03`/`0x01`) don't line up intuitively with the 0–3 values returned by the dual-switch read — functionally correct if consistent, but easy to get wrong when modifying.
- Both safety-critical error states (TDS over-limit, refill timeout) are unrecoverable without a full restart — no graduated response (e.g., alert-then-retry) exists.
- Cooling fan is wired and polled but not actually controlled (confirmed disabled, as stated).
- `STANDBY` command is defined but not distinctly handled in `cmd_status()` — it's not clear it does anything different from `RUN`/absence of active command.

---

*This document reflects the code as currently found in `code.py`, `main.py`, and `I2C_Responder.py` in the `WQCS` folder.*
