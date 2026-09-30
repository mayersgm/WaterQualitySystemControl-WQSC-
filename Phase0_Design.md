# WQCS Hardware Upgrade — Phase 0 Design

Draft BOM, pin map, weight thresholds, and UART protocol for the new scale-based
control system. This supersedes the float-switch/I2C design described in
`System_Analysis.md`. Values marked (draft) should be confirmed/adjusted during
Phase 1 calibration and Phase 6 bench testing against the real containers.

## 1. Bill of materials

| Component | Qty | Notes |
|---|---|---|
| Raspberry Pi Pico 2 (RP2350A, plain — not W) | 1 | Main controller. Dual-core Arm Cortex-M33 (MicroPython runs Arm mode), 4MB flash, USB-C. No wireless needed — ESP32 owns all wireless duties. Pin/API-compatible with original Pico for everything this firmware uses. |
| ESP32 display module (DIYmalls/Sunton ESP32-2432S032C, plain ESP32-WROOM-32, not S3) | 1 | HMI, replaces PyPortal. UART to Pico via GPIO22 (TX) / GPIO35 (RX, input-only) on the board's P3 header. Owns BLE/WiFi for future iPhone app (Phase 8) — original ESP32 has WiFi + Bluetooth Classic + BLE. |
| Load cell, 50kg | 12 | 4 per scale × 3 scales |
| HX711 ADC | 3 | 1 per scale (4 cells → 1 summing junction box → 1 HX711) |
| Junction box (4-cell summing) | 3 | One per scale platform |
| 1 gal distiller boiler + cooling system | 1 | Existing design intent (condenser fan) |
| 2 gal water collection jar | 1 | |
| 9 gal storage reservoir | 1 | |
| Motorized valve — water main → boiler | 1 | Doubles as overflow safety shutoff |
| Motorized valve — collector → reservoir transfer | 1 | |
| 12V magnetic (solenoid) valve — boiler refill | 1 | Not motorized; DC solenoid, switched via relay/MOSFET same as the other valve outputs |
| Boiler drain valve | 1 | **Manual valve, no Pico control** — hand-operated, used only when cleaning the distiller |
| Boiler power relay/receptacle | 1 | |
| TDS sensor — TDS-1 | 1 | Inline, distiller output → collector |
| TDS sensor — TDS-2 | 1 | On distribution pump outlet (monitoring only) |
| NTC thermistor | 1 | Boiler temperature (carried over from old system) |
| Distribution pump (self-contained, pressure-activated) | 1 | Own pressure switch/power — **no Pico control line** |
| Pressure switch — main valve ↔ refill solenoid segment | 1 | Detects stuck-open/stuck-closed refill solenoid by reading back-pressure in the segment between the two valves (see §4) |

## 2. Pico pin map (draft)

Only 3 true ADC-capable pins exist on the Pico (GP26-28) — they map exactly to
the 3 analog signals needed (thermistor, TDS-1, TDS-2).

| Function | GPIO | Type |
|---|---|---|
| Boiler NTC thermistor | GP26 (ADC0) | Analog in |
| TDS-1 (distiller → collector) | GP27 (ADC1) | Analog in |
| TDS-2 (distribution pump outlet) | GP28 (ADC2) | Analog in |
| UART0 TX → ESP32 GPIO35 (RX) | GP0 | UART |
| UART0 RX ← ESP32 GPIO22 (TX) | GP1 | UART |
| Boiler scale HX711 DOUT | GP2 | Digital in |
| Boiler scale HX711 SCK | GP3 | Digital out |
| Collector scale HX711 DOUT | GP4 | Digital in |
| Collector scale HX711 SCK | GP5 | Digital out |
| Reservoir scale HX711 DOUT | GP6 | Digital in |
| Reservoir scale HX711 SCK | GP7 | Digital out |
| Main supply valve (motorized, overflow shutoff) | GP10 | Digital out (relay) |
| Boiler refill solenoid (12V magnetic valve) | GP11 | Digital out (relay/MOSFET, DC coil) |
| Transfer valve (motorized, collector → reservoir) | GP12 | Digital out (relay) |
| Boiler power relay | GP13 | Digital out (relay) |
| Pressure switch (main ↔ refill segment) | GP14 | Digital in, pull-up |
| Onboard LED (core-0 heartbeat) | GP25 | Digital out |

GP15-24 reserved/spare for future expansion. Boiler drain valve is manual
(hand-operated for cleaning) — no Pico GPIO, no firmware control path.

**Cooling fan**: no Pico GPIO at all — the fan is now permanently, physically
ganged to the boiler power relay (fan runs whenever the boiler relay is
energized, off when it isn't). No independent temperature-gated fan control is
possible or needed; `boiler_on()` in firmware doesn't need a separate fan
output the way the old (disabled) design anticipated.

## 3. Weight thresholds (draft — grams of water, post-tare)

Each scale is tared with the empty vessel on it (Phase 1), so these thresholds
are pure water-weight, not raw scale readings. Hysteresis bands prevent valve
chatter at the boundary.

| Vessel | Nominal capacity | EMPTY / LOW | FULL (target) | Notes |
|---|---|---|---|---|
| Boiler (1 gal ≈ 3785 g) | 3785 g | < 200 g | 3600 g (~95%) | `TOPOFF` refill triggers below ~3200 g during active distillation (mid-cycle top-off vs. cold-start full fill — same distinction the old MIN/MID/MAX logic made, now continuous) |
| Collector (2 gal ≈ 7570 g) | 7570 g | < 300 g | 7200 g (~95%) | Transfer opens once FULL **and** the reservoir can take the whole collector (reservoir + collector ≤ reservoir FULL). Fixed overflow fault at 7400 g. |
| Reservoir (9 gal ≈ 34065 g) | 34065 g | < 500 g | 32000 g (~94%) | FULL = usable capacity (operator-adjustable): a transfer only starts if the whole collector fits under it, and stops at FULL. Fixed overflow fault at 33500 g. |

## 4. UART protocol (Pico ↔ ESP32)

UART lets us drop the old fixed 96-byte I2C JSON buffer/single-command-byte
scheme in favor of a simple newline-delimited text protocol — consistent with
the `TARE` / `CAL:<grams>` convention already validated in
`LoadCells/main.py`.

**Commands, ESP32 → Pico** (one per line). `RUN` and `STANDBY` are **not**
commands — in the old protocol RUN was just the PyPortal's idle heartbeat and
never triggered anything distinct on its own, so it's dropped. Both are now
reported back as *derived state* instead (see below):
```
START | STOP | STERILIZE | EMPTY | RESET
TARE:BOILER | TARE:COLLECTOR | TARE:RESERVOIR
CAL:BOILER:<grams> | CAL:COLLECTOR:<grams> | CAL:RESERVOIR:<grams>
ACK        # clears recoverable faults (see fault list below)
GET:LIMITS                         # request the current water-level setpoints
SET:<KEY>:<grams>                  # change one setpoint, e.g. SET:BOILER_FULL:3400
SET:<KEY>=<g>,<KEY>=<g>,...        # change several atomically (validated as a set)
RESET_LIMITS                       # restore default setpoints
```
Adjustable keys (`Pico/limits.py`): `BOILER_TOPOFF`, `BOILER_FULL`,
`COLLECTOR_EMPTY`, `COLLECTOR_FULL`, `RESERVOIR_FULL` (the reservoir's usable
capacity for the transfer rule; shown as "Reservoir capacity" on the HMI). They're
persisted to `limits.json` on the Pico. The hard safety limits are **not**
adjustable: the boiler overflow ceiling, the dry-tank heater floor and the
vessel capacities. Every change is validated against them: paired setpoints
need a gap of at least 200 g, `BOILER_FULL` must be at least 100 g below
overflow, `BOILER_TOPOFF` must be at or above the dry-tank floor, and FULL
setpoints can't exceed capacity. An invalid change is rejected and leaves all
values unchanged.

**Limits reply, Pico → ESP32** (one-off line after each `GET:LIMITS` / `SET` /
`RESET_LIMITS`, not part of the 1 Hz status stream):
```json
{"limits":{"boiler_topoff":3200,"boiler_full":3600,"collector_empty":300,
 "collector_full":7200,"reservoir_full":32000},
 "ok":true,"err":null}
```
On rejection, `ok` is false, `err` gives the reason, and `limits` shows the
unchanged values. `PicoLink` routes these lines to `last_limits`, not
`last_status`.

**Status, Pico → ESP32** (JSON per line, pushed at ~1 Hz from core 1):
```json
{"cmd":"START","state":"RUN","temp_f":172.4,"tds1_ppm":8,"tds2_ppm":11,
 "boiler_g":3550,"collector_g":7100,"reservoir_g":31500,
 "valves":{"main":0,"refill":0,"transfer":1},
 "pressure_sw":true,
 "heater":1,
 "fault":{"tds1":false,"overflow":false,"refill_timeout":false,"valve_stuck":false,
          "collector_overflow":false,"reservoir_overflow":false,"transfer_leak":false},
 "alert":{"tds2":false}}
```
Fill percentages aren't sent. The HMI computes them from `*_g` and the vessel
capacities in §3, which keeps the line short. The Pico's UART also uses
`txbuf=1024` plus a write-all loop, because rp2 `uart.write()` silently drops
whatever doesn't fit in the TX buffer (default is about 288 bytes including
the FIFO).

`cmd` is what the operator last sent; `state` is what the system is actually
doing right now, one of:
- `RUN` — actively distilling (`START`, downstream not full) or sterilizing (`STERILIZE`)
- `STANDBY` — commanded `START` but paused: the collector is FULL and the reservoir can't take its entire contents (reservoir + collector > reservoir FULL), so there's nowhere for more distillate to go. Resumes automatically once the reservoir is drawn down enough for the transfer to fit.
- `STOPPED` — `STOP`
- `EMPTY` — `EMPTY` (parked for manual draining)
- `FAULT` — any of the four recoverable faults below is latched
- `IDLE` — commanded `START` but not yet heating (e.g. boiler still filling)

`fault` entries are recoverable-halt conditions (need `ACK`); `alert` entries
(TDS-2) are informational only and never gate an actuator. The boiler drain
valve is manual (see §1) and never appears in status — it isn't Pico-controlled.

**Main supply valve** (water main → boiler) stays open for the entire
boiler-fill sequence, active only while commanded `START`; the refill valve
does the actual metering/on-off. The main valve force-closes on any of:
- boiler overflow (weight-based safety interlock)
- TDS-1 fault (halt distillation — no point admitting more source water)
- refill timeout (refill valve stuck open past its failsafe cap)
- **refill solenoid stuck** (see below — cross-checked via the pressure switch)
- the `STANDBY` condition (collector FULL and the reservoir can't take it all)
- collector overflow (fixed ceiling — e.g. transfer valve stuck closed)
- reservoir overflow (fixed ceiling — e.g. transfer valve stuck open)
- transfer leak: with the transfer closed, the collector drops ≥300 g from its peak **and** the reservoir rises ≥150 g from its low point (weight-based, no timing, since gravity flow can be arbitrarily slow)

All are checked every loop, independent of the normal fill/transfer state
machine, same as the other safety interlocks in Phase 5. The heater is
additionally protected against dry-tank operation (forced off below a
near-empty boiler-weight floor, regardless of command).

**Stuck-solenoid detection**: the pressure switch sits in the segment between
the main valve and the refill solenoid. With the main valve open, a closed
solenoid blocks flow and that segment builds static back-pressure (switch
trips); an open solenoid lets water flow through and relieves it (switch
doesn't trip). Every loop, while the main valve is open, the Pico compares
what it *commanded* the refill solenoid to be against what the pressure
switch says is *actually* happening:
- commanded closed, but no back-pressure builds (switch never trips) → solenoid stuck **open** — the original failure mode this was added for: a stuck-open solenoid would otherwise only be caught indirectly, after boiler weight climbs all the way to the overflow threshold.
- commanded open, but the switch still reads blocked/high-pressure → solenoid stuck **closed** — caught in seconds via this cross-check instead of waiting out the full 300 s refill timeout.

Either mismatch, confirmed over 3 consecutive loop passes (same debounce
pattern as the other conditions), latches a recoverable `valve_stuck` fault
that force-closes the main valve and heater, requiring `ACK`. The reading is
only meaningful while the main valve is open — with it closed there's no
source pressure to observe either way, so the check is skipped (not treated
as evidence of anything). **Switch polarity is a placeholder pending Phase 6
bench verification** (`PRESSURE_SW_ACTIVE_HIGH` in `Pico/main.py`).

## 5. Status

Phase 0 complete. All open items resolved:
- Cooling fan: physically ganged to boiler relay, no Pico control needed.
- Boiler drain valve: manual, hand-operated for cleaning only, no Pico control.
- Main supply valve: stays open through the fill sequence, force-closes on
  boiler overflow / TDS-1 fault / reservoir-full.

## 6. Bench test setup (pre-Phase 6 dry run)

A bench mockup validates the Phase 2 firmware logic without touching the real
distiller. Built on a **spare WQCS PCB** (fixed screw-terminal wiring left
over from the old system — its boiler-relay terminal happens to already be
GPIO16, matching the old `BOILER_POWER` pin), so the bench uses a different
GPIO assignment than the production pin map in §2. `Pico/main.py` has these
temporarily overridden with a "BENCH TEST PINS" comment block — **must
revert to the production pins before real deployment (Phase 6)**:

| Role | Production pin | Bench pin (spare PCB) |
|---|---|---|
| Boiler heater relay (red LED) | GP13 | **GPIO16** |
| Refill solenoid (relay) | GP11 | **GPIO10** |
| Pressure switch (relay's own contact) | GP14 | **GPIO11** |
| Main valve (green LED) | GP10 | **GPIO19** |
| Transfer valve (LED) | GP12 | **GPIO21** |
| Scales (boiler/collector/reservoir) | GP2/3, GP4/5, GP6/7 | unchanged |

The refill relay's dry contact also stands in for the pressure switch —
wired to reproduce a *healthy* solenoid (commanded closed → back-pressure /
commanded open → no back-pressure); can be deliberately miswired to provoke
the stuck-valve fault on purpose. The 3 real calibrated scales are used
as-is. TDS-1/TDS-2 (GP27/GP28) are temporarily tied to GND until the TDS
modules arrive (an unwired/floating ADC pin could otherwise spuriously trip
the latching TDS-1 fault); thermistor (GP26) can be left floating (harmless
— informational only, gates nothing). The ESP32 display (wired per §1/§2
above) stands in for the operator, sending commands and displaying status
once its firmware exists.

`REFILL_TIMEOUT_S` is temporarily set to **10** in `Pico/main.py` (bench-only
value — **must revert to 300 before real deployment**, tracked for Phase 6).

## 7. Transfer rule and collector/reservoir protection (added 2026-09-29)

- A transfer starts only when the collector is FULL **and** the reservoir can take
  the collector's entire contents: `reservoir + collector ≤ reservoir FULL`. It
  stops when the collector reaches EMPTY or the reservoir reaches FULL. This
  replaced the old reservoir LOW trigger, which left a gap: with the reservoir
  between LOW and FULL, a full collector neither transferred nor paused
  production, and could overflow.
- The transfer is **blocked** while TDS-1, reservoir-overflow or transfer-leak
  faults are latched, so suspect distillate or a suspect valve never moves water
  into the reservoir. A collector overflow does not block it, since transferring
  relieves the collector.
- All protection is weight-based, not timed, because the transfer is gravity-fed
  and can be arbitrarily slow. Stuck-closed shows up as a collector overflow;
  stuck-open shows up as a transfer leak or a reservoir overflow.
- Covered by host tests in `tests/test_control.py`, which run the real
  `Pico/main.py` control step against scripted weights.

