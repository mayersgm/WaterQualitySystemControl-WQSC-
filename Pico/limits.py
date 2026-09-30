"""Operator-adjustable vessel water-level limits (grams, post-tare).

Only fill/drain setpoints are adjustable here. The hard safety limits (each
vessel's overflow ceiling, the dry-tank heater floor) are fixed constants
passed in by the caller and are never operator-settable; every change is
validated against them before it is applied or persisted.

reservoir_full doubles as the reservoir's usable capacity: a transfer only
starts when the reservoir can take the collector's entire contents without
exceeding it (see Pico/main.py).
"""
import json

KEYS = (
    "boiler_topoff",    # refill turns on below this
    "boiler_full",      # refill turns off at/above this
    "collector_empty",  # transfer stops at/below this
    "collector_full",   # transfer may start at/above this
    "reservoir_full",   # usable reservoir capacity; transfer stops at/above this
)

MIN_GAP_G = 200         # minimum hysteresis between paired on/off setpoints
OVERFLOW_MARGIN_G = 100  # every FULL must stay this far below its overflow ceiling

# Rejection reasons are shown to the operator on the HMI, so they use the
# HMI's names for each setting and state the allowed value.
FULL_NAMES = {"boiler": "Boiler FULL", "collector": "Collector FULL",
              "reservoir": "Reservoir capacity"}


class Limits:
    def __init__(self, defaults, overflow, dry_floor_g, path="limits.json"):
        """overflow: {"boiler": g, "collector": g, "reservoir": g} fixed ceilings."""
        self.defaults = {k: defaults[k] for k in KEYS}
        self.overflow = overflow
        self.dry_floor_g = dry_floor_g
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
            return "Boiler refill level min %d g (dry-tank floor)" % self.dry_floor_g
        if v["boiler_topoff"] + MIN_GAP_G > v["boiler_full"]:
            return "Boiler FULL must be %d g above the refill level" % MIN_GAP_G
        if v["collector_empty"] + MIN_GAP_G > v["collector_full"]:
            return "Collector FULL must be %d g above EMPTY" % MIN_GAP_G
        for vessel in ("boiler", "collector", "reservoir"):
            ceiling = self.overflow[vessel] - OVERFLOW_MARGIN_G
            if v[vessel + "_full"] > ceiling:
                return "%s max %d g (overflow at %d g)" % (
                    FULL_NAMES[vessel], ceiling, self.overflow[vessel])
        if v["reservoir_full"] < self.overflow["collector"]:
            # the collector can legitimately hold up to its overflow ceiling;
            # an empty reservoir must be able to take all of it, or a transfer
            # could never fit and production would stay in STANDBY forever
            return "Reservoir capacity min %d g (must hold a full collector)" % (
                self.overflow["collector"])
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
