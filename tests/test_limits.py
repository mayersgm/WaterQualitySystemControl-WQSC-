"""Host-side (CPython) tests for Pico/limits.py. Run: python3 -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Pico"))
from limits import Limits  # noqa: E402

PROD = {
    "boiler_topoff": 3200, "boiler_full": 3600,
    "collector_empty": 300, "collector_full": 7200,
    "reservoir_full": 32000,
}
OVERFLOW = {"boiler": 3700, "collector": 7400, "reservoir": 33500}


class LimitsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "limits.json")

    def tearDown(self):
        self.dir.cleanup()

    def make(self, defaults=PROD, overflow=OVERFLOW):
        return Limits(defaults, overflow, 200, path=self.path)

    def test_defaults_used_without_file(self):
        self.assertEqual(self.make().values, PROD)

    def test_old_reservoir_low_key_in_defaults_is_ignored(self):
        self.assertEqual(self.make(defaults=dict(PROD, reservoir_low=30000)).values, PROD)

    def test_valid_update_applies_and_persists(self):
        self.assertIsNone(self.make().update({"boiler_full": 3400}))
        self.assertEqual(self.make()["boiler_full"], 3400)

    def test_atomic_multi_key_update(self):
        # lowering both is invalid one key at a time (full first), valid together
        lim = self.make()
        self.assertIsNotNone(lim.update({"boiler_full": 3100}))
        self.assertIsNone(lim.update({"boiler_topoff": 2800, "boiler_full": 3100}))
        self.assertEqual((lim["boiler_topoff"], lim["boiler_full"]), (2800, 3100))

    def test_rejections_leave_values_unchanged(self):
        lim = self.make()
        bad = [
            {"boiler_full": 3650},          # within 100g of boiler overflow
            {"boiler_topoff": 3500},        # < 200g below full
            {"boiler_topoff": 150},         # below dry-tank floor
            {"collector_full": 7350},       # within 100g of collector overflow
            {"collector_empty": 7100},      # gap < 200
            {"reservoir_full": 33450},      # within 100g of reservoir overflow
            {"reservoir_full": 7300},       # smaller than a collector at its overflow ceiling
            {"reservoir_low": 1000},        # removed key
            {"boiler_full": -5},            # negative
        ]
        for change in bad:
            self.assertIsNotNone(lim.update(change), change)
        self.assertEqual(lim.values, PROD)

    def test_reset_restores_defaults(self):
        lim = self.make()
        lim.update({"collector_full": 6000})
        lim.reset()
        self.assertEqual(self.make().values, PROD)

    def test_stored_values_invalid_for_new_constants_fall_back(self):
        self.make().update({"boiler_full": 3500})
        bench = dict(PROD, boiler_topoff=300, boiler_full=600)
        lim = self.make(defaults=bench, overflow=dict(OVERFLOW, boiler=900))
        self.assertEqual(lim["boiler_full"], 600)

    def test_invalid_defaults_raise(self):
        with self.assertRaises(ValueError):
            self.make(overflow=dict(OVERFLOW, boiler=900))


if __name__ == "__main__":
    unittest.main()
