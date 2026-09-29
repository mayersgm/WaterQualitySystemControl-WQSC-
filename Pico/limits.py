"""Operator-adjustable vessel water-level limits (grams, post-tare).

Only fill/drain setpoints are adjustable here. The hard safety limits (boiler
overflow ceiling, dry-tank heater floor, vessel capacities) are fixed
constants passed in by the caller and are never operator-settable; every
change is validated against them before it is applied or persisted.
"""
import json

KEYS = (
    "boiler_topoff",    # refill turns on below this
    "boiler_full",      # refill turns off at/above this
    "collector_empty",  # transfer stops at/below this
    "collector_full",   # transfer may start at/above this
    "reservoir_low",    # transfer may start below this
    "reservoir_full",   # transfer stops at/above this
)

MIN_GAP_G = 200         # minimum hysteresis between paired on/off setpoints
OVERFLOW_MARGIN_G = 100  # boiler_full must stay this far below the overflow ceiling


class Limits:
    def __init__(self, defaults, overflow_g, dry_floor_g, capacities, path="limits.json"):
        self.defaults = dict(defaults)
        self.overflow_g = overflow_g
        self.dry_floor_g = dry_floor_g
        self.capacities = capacities  # {"collector": g, "reservoir": g}
        self.path = path
        err = self.validate(self.defaults)
        if err:
            raise ValueError("default limits invalid: " + err)
        self.values = dict(self.defaults)
        self._load()

    def __getitem__(self, key):
        return self.values[key]

    def validate(self, v):
        """Return None if the full set `v` is safe, else a short reason."""
        for k in KEYS:
            if k not in v:
                return "missing " + k
            if not isinstance(v[k], (int, float)) or v[k] < 0:
                return k + " must be a non-negative number"
        if v["boiler_topoff"] < self.dry_floor_g:
            return "boiler_topoff below dry-tank floor %d" % self.dry_floor_g
        if v["boiler_topoff"] + MIN_GAP_G > v["boiler_full"]:
            return "boiler_full must be >= boiler_topoff + %d" % MIN_GAP_G
        if v["boiler_full"] + OVERFLOW_MARGIN_G > self.overflow_g:
            return "boiler_full must be <= overflow %d - %d" % (self.overflow_g, OVERFLOW_MARGIN_G)
        if v["collector_empty"] + MIN_GAP_G > v["collector_full"]:
            return "collector_full must be >= collector_empty + %d" % MIN_GAP_G
        if v["collector_full"] > self.capacities["collector"]:
            return "collector_full exceeds capacity %d" % self.capacities["collector"]
        if v["reservoir_low"] + MIN_GAP_G > v["reservoir_full"]:
            return "reservoir_full must be >= reservoir_low + %d" % MIN_GAP_G
        if v["reservoir_full"] > self.capacities["reservoir"]:
            return "reservoir_full exceeds capacity %d" % self.capacities["reservoir"]
        return None

    def update(self, changes):
        """Apply {key: grams} atomically if the resulting set is valid.
        Returns None on success (and persists), else the rejection reason."""
        for k in changes:
            if k not in KEYS:
                return "unknown key " + k
        proposed = dict(self.values)
        proposed.update(changes)
        err = self.validate(proposed)
        if err:
            return err
        self.values = proposed
        self._save()
        return None

    def reset(self):
        self.values = dict(self.defaults)
        self._save()

    def _load(self):
        try:
            with open(self.path) as f:
                stored = json.load(f)
        except (OSError, ValueError):
            return
        merged = dict(self.defaults)
        merged.update({k: stored[k] for k in KEYS if k in stored})
        err = self.validate(merged)
        if err:
            # e.g. the fixed safety constants changed since this was saved
            print("limits.json ignored (%s); using defaults" % err)
            return
        self.values = merged
        print("Limits loaded:", self.values)

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.values, f)
