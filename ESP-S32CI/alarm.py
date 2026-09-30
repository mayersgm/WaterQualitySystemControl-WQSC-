"""Audible alerts through the board's speaker amplifier (GPIO26, FM8002A).

Needs a small 8 ohm speaker on the SPEAK connector. Non-blocking: call
update() every main-loop pass; patterns are sequenced from ticks_ms.

  - new fault latched     -> urgent repeating beep until ACK (silence())
  - TDS-2 alert / STANDBY -> one short chime when it starts
  - link to Pico lost     -> double beep, twice

ACK silences faults already latched; the alarm only sounds again for a fault
that wasn't latched at ACK time, or one that clears and comes back. ACK also
clears faults on the Pico, which re-latches within ~3 s if the condition is
still present -- so ACKed faults get a grace period before they can re-sound.
"""
import time
from machine import Pin, PWM

SPEAKER_PIN = 26
VOLUME = 16384  # duty_u16; 32768 = loudest square wave
ACK_GRACE_MS = 30000

# (freq_hz, ms) steps; freq 0 = silence. "repeat" patterns loop until stopped.
FAULT = ((2400, 160), (0, 90), (2400, 160), (0, 700))
CHIME = ((1600, 120), (0, 60), (2000, 160))
LINK_LOST = ((700, 200), (0, 150), (700, 200), (0, 900)) * 2


class Alarm:
    def __init__(self, pin=SPEAKER_PIN):
        self._pwm = PWM(Pin(pin), freq=1000, duty_u16=0)
        self._pattern = None
        self._repeat = False
        self._step = 0
        self._step_end = 0
        self._sounded_faults = set()   # faults already beeped for
        self._acked = set()            # faults ACKed within the grace period
        self._grace_end = 0
        self._prev_alert = False
        self._prev_state = None
        self._prev_link = True

    # -- pattern player --
    def _play(self, pattern, repeat=False):
        self._pattern, self._repeat, self._step = pattern, repeat, 0
        self._start_step()

    def _start_step(self):
        freq, ms = self._pattern[self._step]
        if freq:
            self._pwm.freq(freq)
            self._pwm.duty_u16(VOLUME)
        else:
            self._pwm.duty_u16(0)
        self._step_end = time.ticks_add(time.ticks_ms(), ms)

    def _tick(self):
        if self._pattern is None or time.ticks_diff(time.ticks_ms(), self._step_end) < 0:
            return
        self._step += 1
        if self._step >= len(self._pattern):
            if not self._repeat:
                self.stop()
                return
            self._step = 0
        self._start_step()

    def stop(self):
        self._pattern = None
        self._pwm.duty_u16(0)

    # -- policy --
    def silence(self, current_faults=()):
        """ACK: stop, and don't re-sound for these faults during the grace period."""
        self._acked = set(current_faults)
        self._sounded_faults |= self._acked
        self._grace_end = time.ticks_add(time.ticks_ms(), ACK_GRACE_MS)
        self.stop()

    def update(self, status, link_ok):
        if not link_ok and self._prev_link:
            self._play(LINK_LOST)
        self._prev_link = link_ok

        if status is not None:
            faults = {k for k, on in status.get("fault", {}).items() if on}
            in_grace = time.ticks_diff(self._grace_end, time.ticks_ms()) > 0
            if not in_grace:
                self._acked = set()
            # forget faults that cleared, so a recurrence sounds again
            self._sounded_faults &= faults
            new = faults - self._sounded_faults - self._acked
            if new:
                self._sounded_faults |= new
                self._play(FAULT, repeat=True)
            elif not faults and self._pattern is FAULT:
                self.stop()

            alert = bool(status.get("alert", {}).get("tds2"))
            state = status.get("state")
            if not faults and self._pattern is None and (
                    (alert and not self._prev_alert) or
                    (state == "STANDBY" and self._prev_state != "STANDBY")):
                self._play(CHIME)
            self._prev_alert, self._prev_state = alert, state

        self._tick()
