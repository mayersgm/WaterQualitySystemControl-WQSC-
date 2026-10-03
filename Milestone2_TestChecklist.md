# Milestone 2 Hardware Test Checklist

Manual tests for the phone app, push alerts and the safety work done during
Milestone 2 (2026-10-01 to 10-03). The code behind each test is already
covered by the host tests (`python3 -m unittest discover tests`). These
confirm it on the real hardware.

**Before every test:**
- Tap **STOP** and check that the touchscreen shows `STOPPED`, unless the test
  says otherwise. Nothing here needs the heater on.
- Phone on the **ASUS** WiFi, page open at `http://192.168.50.140/`.
- Weights are bench values: boiler overflow 900 g, collector overflow 900 g,
  reservoir overflow 1200 g, collector FULL 500 g, reservoir capacity 1000 g.

Useful while testing:
- `http://192.168.50.140/status`: live status as JSON.
- `http://192.168.50.140/log`: WiFi history (connects, drops, recovery).
- Bottom of the phone page: touchscreen uptime and push alerts sent/failed.

## Already verified on hardware

| Date | What |
|---|---|
| 09-29 | Milestone 1: dashboard, CAL, Levels and NO LINK screens |
| 10-01 | Phone page loads with live status. STOP from the phone received. Wrong PIN refused (HTTP 403). |
| 10-01 | Pushes "no link to Pico" and "link restored" received |
| 10-01 | Pico control-loop stall: outputs off within 5 s, NO LINK shown, push received |
| 10-02 | WiFi power saving off: page loads on the first try after idling. Test alert received. |
| 10-03 | Speaker alarms, and button clicks with per-button tones |
| 10-03 | 24 KB system-memory reserve: holds with the screen's memory full, and WiFi still works |

## 1. Every phone button
- [ ] **START**: the page asks "Start distilling?". After confirming, the
  touchscreen changes to START (button shows STOP, state IDLE or RUN). Tap
  **STOP** on the phone afterwards.
- [ ] **STERILIZE**: confirm prompt, then the touchscreen shows
  "RUN - sterilizing". Tap **CANCEL** on the phone and it goes back to
  STOPPED.
- [ ] **EMPTY**: no prompt. The touchscreen shows "EMPTY - drain mode". Tap
  **CANCEL**.
- [ ] **RESET**: accepted (a "RESET sent" message appears). Heater and valves
  stay off.
- [ ] ACK is covered in test 2.
- Note: phone commands make no click on the touchscreen. Only touchscreen
  presses do.

## 2. Real fault: alarm, push, ACK from the phone
- [ ] Put weight on the **boiler** past **900 g**.
- **Expect** within about 3 s: the touchscreen banner turns red,
  "FAULT BOILER OVFL". The speaker sounds the repeating fault alarm. The phone
  gets an urgent push, "WQCS FAULT: Boiler overflow", and the page shows an
  **ACK fault** button.
- [ ] Remove the weight first, back under 900 g, so the fault doesn't
  re-latch, then tap **ACK fault** on the phone.
- **Expect**: the alarm stops, the fault clears and the banner shows STOPPED.
  The page's "alerts sent" count went up by 1.

## 3. Wrong-PIN lockout
- [ ] On the phone, tap "Change PIN", then send a command and enter a wrong
  PIN. Repeat 5 times. Each says "wrong PIN".
- [ ] 6th try, even with the **right** PIN: "too many wrong PINs; wait a
  minute".
- [ ] After 1 minute the right PIN works again.

## 4. Sensor failure
- [ ] Unplug **one HX711 board's power (VCC) wire**, for example the
  collector's.
- **Expect** within about 1 s: status shows `FAULT`, heater off, valves
  closed. The phone page's top line shows "Pico: OSError('HX711 not
  ready…')".
- **If instead** that vessel just shows a wild or frozen weight with no
  fault, write down the value. That's a real finding: the driver can't tell a
  floating data line from a reading, and it would need a plausibility check
  added.
- **Expect** after about 5 s: the `SENSOR` fault is latched (red banner), the
  alarm sounds, and a push arrives, "WQCS FAULT: Sensor read failing".
- [ ] Plug the wire back in, then **ACK**. The fault clears and weights read
  normally again.

## 5. WiFi recovery
- [ ] In the ASUS app or web page, turn the 2.4 GHz WiFi **off** for about
  3 minutes.
- **Expect**: the touchscreen keeps working normally the whole time. The
  Pico isn't affected.
- [ ] Turn the WiFi back on.
- **Expect**: within about 30 s the phone page works again. `/log` shows
  `lost`, `restarting the WiFi driver` (after 2 min), then `connected`. The
  touchscreen does **not** restart, because that step only happens after
  10 min down.

## 6. Touchscreen while the phone watches
- [ ] Leave the phone page open, refreshing every 2 s, for 10 minutes.
  Meanwhile use the touchscreen: open Levels, hold +/− for a while, go Back,
  open CAL, go Back, and repeat a few times.
- **Expect**: no freeze or restart. The phone page's "touchscreen up" time
  keeps counting without dropping back to 0.

## 7. Multi-day run (normal operation)
- [ ] Let it run for several days as usual.
- **Expect**: the phone page's "touchscreen up" time keeps growing, "failed"
  alerts stay at 0, and `/log` shows no unexplained drops. Anything odd: note
  the time and tell Claude, who can read the serial and WiFi logs.

## Later: needs TDS modules or a full collector
- [ ] **TDS-2 outlet alert**: TDS-2 ≥ 50 ppm. Push "outlet TDS high"
  (informational, no fault).
- [ ] **TDS-1 fault**: TDS-1 ≥ 50 ppm. Fault, transfer blocked, push.
- [ ] **Reservoir full**: in START, collector ≥ 500 g with the reservoir too
  full to take it (collector + reservoir > 1000 g). Banner shows
  "STANDBY - no room", push "reservoir full" after about 3 s. The routine
  "STANDBY - transferring" never pushes.

## Notes while running
Record the date, the result and anything unexpected next to each test.
