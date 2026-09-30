# Phase 2 Bench Test Sequence

Prerequisites: wiring per `Phase0_Design.md` §6, `REFILL_TIMEOUT_S=10` in
`Pico/main.py`, TDS-1/TDS-2 grounded, ESP32 terminal connected and able to
send command lines / show the JSON status stream over UART.

Legend: G=green LED (main valve), B=blue LED (transfer valve), R=red LED
(boiler heater), RLY=refill relay (solenoid stand-in).

## 1. Power-on / idle sanity check
- Power up, send nothing.
- **Expect**: `state: STOPPED` (default `cmd=STOP`), all LEDs off, RLY off,
  `pressure_sw` reads whatever the relay's de-energized contact state is
  (note the value — this is your baseline for confirming polarity later).

## 2. Calibration check (if not already confirmed)
- Send `TARE:BOILER`, `TARE:COLLECTOR`, `TARE:RESERVOIR` with each platform
  empty, then `CAL:<NAME>:<grams>` with a reference weight.
- **Expect**: status `boiler_g`/`collector_g`/`reservoir_g` all read ~0 with
  platforms empty.

## 3. Cold-start fill
- Place weight on boiler scale to simulate ~0g (empty).
- Send `START`.
- **Expect**: G on (main valve), RLY on (refill), `state: IDLE` (not yet
  heating), `fault.*` all false.
- Slowly add weight to the boiler scale, watching it climb through 3200g
  (`BOILER_TOPOFF_G`) toward 3600g.
- **Expect**: RLY stays on continuously the whole way through (it only turns
  off at FULL, not at the topoff threshold — topoff is what turns it *on*
  when starting from below that line).
- Continue adding weight past 3600g (`BOILER_FULL_G`).
- **Expect**: within ~3s (debounce), RLY turns off. G stays on (main valve
  stays open through the whole sequence). `state` becomes `RUN` (heater/R
  turns on, assuming boiler_g ≥ 200g dry-tank floor, which it is).

## 4. Healthy refill cross-check (confirms pressure switch polarity)
- With boiler still ~FULL, remove some weight to drop below 3200g again.
- **Expect**: RLY turns back on (topoff). Watch `pressure_sw` in status —
  it should flip to the "no back-pressure" reading within a second or two of
  RLY energizing. If it doesn't change at all, your relay contact isn't
  wired to actually reflect solenoid state — check the P3/GP14 wiring.
- Add weight back past FULL.
- **Expect**: RLY off, `pressure_sw` flips back to "back-pressure present."
- **This confirms/sets `PRESSURE_SW_ACTIVE_HIGH`**: whichever raw boolean
  you observe when RLY is *off* (commanded-closed) should map to
  `pressure_detected=True` in the JSON. If it's showing `False` when RLY is
  off, flip the constant in `Pico/main.py` and re-flash.

## 5. Stuck-valve fault (deliberate)
- With boiler below FULL (so RLY wants to be on) and main valve open, hold
  the relay's contact in the "no back-pressure" position by hand (or
  physically disconnect the pressure-switch wire) while RLY is OFF (i.e.
  fake "commanded closed but flowing").
- **Expect**: after 3 confirm passes (~3s), `fault.valve_stuck` latches
  true, `state: FAULT`, G/R/RLY all forced off.
- Send `ACK`.
- **Expect**: fault clears, system re-evaluates and resumes normally on the
  next loop (assuming the pressure-switch wiring is restored to normal).

## 6. Refill timeout fault
- With `REFILL_TIMEOUT_S=10`, hold boiler weight steady below 3200g (don't
  let it reach FULL) for >10s while RLY is on.
- **Expect**: `fault.refill_timeout` latches, RLY/G/R force off, `state:
  FAULT`. `ACK` to clear.

## 7. Boiler overflow fault
- Push boiler weight past 3700g (`BOILER_OVERFLOW_G`).
- **Expect**: within ~3s, `fault.overflow` latches, G/RLY/R force off
  regardless of anything else. `ACK` to clear (bring weight back down first,
  otherwise it'll immediately re-trip).

> **Superseded 2026-09-29 (steps 8–9):** STANDBY and the transfer trigger now
> follow the capacity rule in `Phase0_Design.md` §7. A transfer starts when the
> collector is FULL and `reservoir + collector ≤ reservoir FULL`. STANDBY happens
> when the collector is FULL and it doesn't fit. Reservoir LOW no longer exists.
> The collector-overflow, reservoir-overflow and transfer-leak faults are new.
> The logic is covered by `tests/test_control.py`. Re-run these two steps on the
> bench against the new rule.

## 8. STANDBY (collector + reservoir both full)
- Reset boiler to a normal mid-range weight (e.g. 3400g) so heater is
  otherwise eligible to run. Send `START` fresh (or `ACK`+re-add weight if
  coming from a fault above).
- Push collector scale to ≥7200g AND reservoir scale to ≥32000g.
- **Expect**: within ~3s, `state: STANDBY`. R (heater) and G (main valve)
  turn off — but this is *not* a fault, no `ACK` needed. `fault.*` all
  stay false.
- Drop reservoir weight back below 32000g (collector still full).
- **Expect**: `state` returns to `RUN`/`IDLE` — production resumes since
  only reservoir was full, collector alone doesn't pause it (per your
  "collector AND reservoir" rule).

## 9. Collector → reservoir transfer
- With `cmd=START`, push collector to ≥7200g (full) and keep reservoir below
  30000g (`RESERVOIR_TRANSFER_LOW_G`).
- **Expect**: B (transfer valve) turns on within ~3s.
- Drop collector weight to ≤300g (simulating it draining into the
  reservoir).
- **Expect**: B turns off (collector empty).
- Repeat, but this time raise reservoir weight to ≥32000g instead of
  draining the collector.
- **Expect**: B turns off (reservoir full) even though collector is still
  full.

## 10. STOP / EMPTY / RESET
- Mid-fill (RLY or B on), send `STOP`.
- **Expect**: everything (G/R/B/RLY) off immediately, `state: STOPPED`.
- Send `START` again, then `EMPTY`.
- **Expect**: everything off, `state: EMPTY`.
- Send `RESET`.
- **Expect**: `cmd` back to a clean state, any latched faults cleared,
  `state: STOPPED`.

## Notes while running
- Every fault/state transition should take ~3 debounce passes (~3s at
  `LOOP_PERIOD_S=1.0`) to confirm, except refill-timeout (exactly 10s in
  this bench config) — a transition that happens instantly on a single
  reading, or one that never happens despite clearly crossing a threshold,
  is worth investigating before moving to the next step.
- Record whatever `PRESSURE_SW_ACTIVE_HIGH` value step 4 lands on — that's
  the answer to the Phase 6 placeholder question in `Pico/main.py`.
