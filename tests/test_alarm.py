"""Host-side tests for ESP-S32CI/alarm.py (fake machine + time). Run:
python3 -m unittest discover tests"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ESP-S32CI"))


class FakePWM:
    def __init__(self, pin, freq=0, duty_u16=0):
        self.duty = duty_u16

    def freq(self, f):
        pass

    def duty_u16(self, d):
        self.duty = d


sys.modules.setdefault("machine", types.SimpleNamespace(Pin=lambda n: n, PWM=FakePWM))
import alarm  # noqa: E402


class FakeTime:
    now = 0

    @classmethod
    def ticks_ms(cls):
        return cls.now

    @staticmethod
    def ticks_add(a, b):
        return a + b

    @staticmethod
    def ticks_diff(a, b):
        return a - b


alarm.time = FakeTime


def status(faults=(), state="RUN", tds2=False):
    return {"state": state, "fault": {k: True for k in faults}, "alert": {"tds2": tds2}}


class AlarmTest(unittest.TestCase):
    def setUp(self):
        FakeTime.now = 0
        self.a = alarm.Alarm()

    def run_for(self, ms, st=None, link=True):
        for _ in range(ms // 20):
            FakeTime.now += 20
            self.a.update(st, link)

    def test_new_fault_beeps_until_ack(self):
        self.a.update(status(["overflow"]), True)
        self.assertIs(self.a._pattern, alarm.FAULT)
        self.run_for(5000, status(["overflow"]))
        self.assertIs(self.a._pattern, alarm.FAULT)  # still repeating
        self.a.silence(["overflow"])
        self.run_for(2000, status(["overflow"]))
        self.assertIsNone(self.a._pattern)

    def test_relatch_after_ack_stays_silent(self):
        self.a.update(status(["overflow"]), True)
        self.a.silence(["overflow"])
        self.run_for(1000, status([]))               # Pico cleared it on ACK
        self.run_for(3000, status(["overflow"]))     # condition still present
        self.assertIsNone(self.a._pattern)

    def test_different_fault_during_grace_beeps(self):
        self.a.update(status(["overflow"]), True)
        self.a.silence(["overflow"])
        self.run_for(1000, status(["overflow", "refill_timeout"]))
        self.assertIs(self.a._pattern, alarm.FAULT)

    def test_recurrence_after_grace_beeps(self):
        self.a.update(status(["tds1"]), True)
        self.a.silence(["tds1"])
        self.run_for(alarm.ACK_GRACE_MS + 1000, status([]))
        self.a.update(status(["tds1"]), True)
        self.assertIs(self.a._pattern, alarm.FAULT)

    def test_fault_clearing_stops_beep(self):
        self.a.update(status(["valve_stuck"]), True)
        self.a.update(status([]), True)
        self.assertIsNone(self.a._pattern)

    def test_chime_on_standby_and_tds2_edges_only(self):
        self.a.update(status(state="STANDBY"), True)
        self.assertIs(self.a._pattern, alarm.CHIME)
        self.run_for(2000, status(state="STANDBY"))
        self.assertIsNone(self.a._pattern)           # once, not repeating
        self.a.update(status(tds2=True), True)
        self.assertIs(self.a._pattern, alarm.CHIME)

    def test_link_lost_plays_then_stops(self):
        self.a.update(None, False)
        self.assertIs(self.a._pattern, alarm.LINK_LOST)
        self.run_for(10000, None, link=False)
        self.assertIsNone(self.a._pattern)
        self.assertEqual(self.a._pwm.duty, 0)


class ClickTest(unittest.TestCase):
    def setUp(self):
        FakeTime.now = 0
        self.a = alarm.Alarm()

    def advance(self, ms, st=None):
        for _ in range(ms // 5):
            FakeTime.now += 5
            self.a.update(st, True)

    def test_click_is_short_and_quiet(self):
        self.a.click()
        self.assertEqual(self.a._pwm.duty, alarm.CLICK_VOLUME)
        self.assertLess(alarm.CLICK_VOLUME, alarm.VOLUME)
        self.advance(40)
        self.assertEqual(self.a._pwm.duty, 0)

    def test_click_never_interrupts_an_alarm(self):
        self.a.update(status(["overflow"]), True)
        self.assertIs(self.a._pattern, alarm.FAULT)
        self.a.click()
        self.assertIs(self.a._pattern, alarm.FAULT)
        self.assertEqual(self.a._pwm.duty, alarm.VOLUME)

    def test_click_uses_the_buttons_tone(self):
        freqs = []
        self.a._pwm.freq = freqs.append
        self.a.click((1500, 35))
        self.assertEqual(freqs, [1500])
        self.advance(20)
        self.assertEqual(self.a._pwm.duty, alarm.CLICK_VOLUME)   # 35 ms tone still sounding
        self.advance(30)
        self.assertEqual(self.a._pwm.duty, 0)

    def test_rapid_taps_replace_the_click(self):
        freqs = []
        self.a._pwm.freq = freqs.append
        self.a.click((900, 60))
        self.a.click((3400, 10))
        self.assertEqual(freqs, [900, 3400])

    def test_alarm_after_click_plays_at_full_volume(self):
        self.a.click()
        self.a.update(status(["overflow"]), True)
        self.assertIs(self.a._pattern, alarm.FAULT)
        self.assertEqual(self.a._pwm.duty, alarm.VOLUME)


if __name__ == "__main__":
    unittest.main()
