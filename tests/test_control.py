"""Runs the Pico's real _control_step against scripted weights (bench limits:
collector_full 500, collector_empty 100, reservoir_full 1000; overflow ceilings
boiler 900 / collector 900 / reservoir 1200)."""
import os
import tempfile
import unittest

import fake_pico


class ControlTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        self.main, self.w = fake_pico.make_controller(self.dir.name)
        # the bench pressure-switch stand-in follows the refill command; keep it
        # "healthy" so the unrelated stuck-solenoid check never trips here
        self.w.cmd = "START"
        self.set(boiler=600, collector=0, reservoir=0)

    def tearDown(self):
        os.chdir(self._cwd)
        self.dir.cleanup()

    def set(self, **grams):
        for name, g in grams.items():
            self.w.scales[name].v = g

    def step(self, n=4):
        m = self.main
        for _ in range(n):
            # healthy pressure switch: blocked when refill closed, flowing when open
            m.PRESSURE_SW.value(0 if self.w.refill_open == m.PRESSURE_SW_ACTIVE_HIGH else 1)
            self.w._control_step()
        return self.w.last_status

    def faults(self):
        return {k for k, v in self.w.last_status["fault"].items() if v}

    # -- the capacity rule, and the old overflow gap it closes --
    def test_full_collector_that_does_not_fit_pauses_production(self):
        # 520 + 600 = 1120 > reservoir_full 1000. The old logic (transfer only
        # below reservoir_low, pause only when BOTH full) did neither here and
        # kept distilling into a full collector.
        self.set(collector=520, reservoir=600)
        s = self.step()
        self.assertEqual(s["state"], "STANDBY")
        self.assertEqual(s["heater"], 0)
        self.assertEqual(s["valves"]["main"], 0)
        self.assertEqual(s["valves"]["transfer"], 0)

    def test_transfer_starts_once_the_whole_collector_fits(self):
        self.set(collector=520, reservoir=600)
        self.step()
        self.set(reservoir=450)                      # pump drew it down: 970 <= 1000
        s = self.step()
        self.assertEqual(s["valves"]["transfer"], 1)
        self.assertEqual(s["state"], "STANDBY")      # still paused: collector >= FULL

    def test_full_collector_pauses_even_when_it_fits(self):
        # user rule 2026-09-29: collector at/above FULL -> STANDBY whatever the
        # reservoir holds; the transfer drains it meanwhile, production resumes
        # once the collector is back below FULL.
        self.set(collector=520, reservoir=0)
        s = self.step()
        self.assertEqual((s["state"], s["heater"], s["valves"]["main"]), ("STANDBY", 0, 0))
        self.assertEqual(s["valves"]["transfer"], 1)
        self.set(collector=400, reservoir=120)       # drained below FULL
        s = self.step()
        self.assertEqual((s["state"], s["heater"]), ("RUN", 1))
        self.assertEqual(s["valves"]["transfer"], 1)  # keeps going to EMPTY

    def test_production_pauses_if_total_outgrows_capacity_mid_transfer(self):
        # bench case 2026-09-29: transfer running, then the total grew to
        # 1798 g > 1000 g; production kept going because STANDBY was skipped
        # during transfers. Now it pauses; the transfer runs on to FULL.
        self.set(collector=520, reservoir=100)
        self.assertEqual(self.step()["valves"]["transfer"], 1)
        self.set(collector=824, reservoir=974)
        s = self.step()
        self.assertEqual((s["state"], s["heater"], s["valves"]["main"]), ("STANDBY", 0, 0))
        self.assertEqual(s["valves"]["transfer"], 1)
        self.set(reservoir=1000)                     # reservoir FULL ends the transfer
        self.assertEqual(self.step()["valves"]["transfer"], 0)

    def test_nearly_overflowing_collector_always_fits_empty_reservoir(self):
        # bench case 2026-09-29: collector at 860 g never fit the old 800 g
        # capacity even into an empty reservoir -> STANDBY forever. Validation
        # now requires reservoir capacity >= the collector overflow ceiling.
        self.set(collector=860, reservoir=20)
        self.assertEqual(self.step()["valves"]["transfer"], 1)

    def test_transfer_runs_until_collector_empty(self):
        self.set(collector=520, reservoir=100)
        self.assertEqual(self.step()["valves"]["transfer"], 1)
        self.set(collector=300, reservoir=320)       # gravity, slow: still open
        self.assertEqual(self.step()["valves"]["transfer"], 1)
        self.set(collector=80, reservoir=540)
        self.assertEqual(self.step()["valves"]["transfer"], 0)
        self.assertEqual(self.faults(), set())       # a normal transfer isn't a leak

    # -- overflow faults (valve stuck closed / open) --
    def test_collector_overflow_stops_distillation(self):
        self.set(collector=950, reservoir=5000)      # can't fit, keeps filling
        s = self.step()
        self.assertIn("collector_overflow", self.faults())
        self.assertEqual((s["heater"], s["valves"]["main"], s["state"]), (0, 0, "FAULT"))

    def test_reservoir_overflow_stops_distillation_and_blocks_transfer(self):
        self.set(collector=520, reservoir=1250)
        s = self.step()
        self.assertIn("reservoir_overflow", self.faults())
        self.assertEqual((s["heater"], s["valves"]["transfer"]), (0, 0))

    # -- leak detection (no timing) --
    def test_closed_valve_leak_detected(self):
        self.set(collector=450, reservoir=100)       # not full: valve stays closed
        self.step()
        self.set(collector=100, reservoir=440)       # water moved anyway
        s = self.step()
        self.assertIn("transfer_leak", self.faults())
        self.assertEqual((s["heater"], s["valves"]["transfer"]), (0, 0))

    def test_lifting_collector_jar_is_not_a_leak(self):
        self.set(collector=450, reservoir=100)
        self.step()
        self.set(collector=0)                        # jar lifted, reservoir unchanged
        self.step()
        self.assertNotIn("transfer_leak", self.faults())

    def test_ack_rearms_leak_check_from_current_weights(self):
        self.set(collector=450, reservoir=100)
        self.step()
        self.set(collector=100, reservoir=440)
        self.step()
        self.w._handle_command("ACK")
        self.step()
        self.assertNotIn("transfer_leak", self.faults())

    # -- contaminated distillate must not reach the reservoir --
    def test_tds1_fault_blocks_transfer(self):
        self.w.tds1.v = 80
        self.set(collector=520, reservoir=100)
        s = self.step()
        self.assertIn("tds1", self.faults())
        self.assertEqual(s["valves"]["transfer"], 0)

    def test_status_reports_every_fault_key(self):
        self.assertEqual(set(self.step()["fault"]), set(self.main.FAULT_KEYS))


if __name__ == "__main__":
    unittest.main()
