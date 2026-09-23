import json
from hx711 import HX711

SAMPLE_COUNT = 5       # readings per measurement (median filter)
TARE_SAMPLES = 20      # readings averaged for tare


class Scale:
    def __init__(self, name, dout_pin, sck_pin):
        self.name = name
        self.cal_file = f"cal_{name}.json"
        self.hx = HX711(dout_pin, sck_pin)
        self.zero_offset = 0
        self.units_per_gram = 1.0
        self._tared = False
        self._load_calibration()

    # ------------------------------------------------------------------
    # Calibration persistence
    # ------------------------------------------------------------------

    def _load_calibration(self):
        try:
            with open(self.cal_file) as f:
                data = json.load(f)
            self.zero_offset = data["zero_offset"]
            self.units_per_gram = data["units_per_gram"]
            self._tared = True
            print(f"[{self.name}] Calibration loaded: offset={self.zero_offset}, upg={self.units_per_gram:.4f}")
        except (OSError, KeyError):
            print(f"[{self.name}] No calibration found. Send TARE:{self.name.upper()} then CAL:{self.name.upper()}:<grams>")

    def _save_calibration(self):
        with open(self.cal_file, "w") as f:
            json.dump({
                "zero_offset": self.zero_offset,
                "units_per_gram": self.units_per_gram,
            }, f)
        print(f"[{self.name}] Calibration saved.")

    # ------------------------------------------------------------------
    # Core reads
    # ------------------------------------------------------------------

    def _median_raw(self, n=SAMPLE_COUNT):
        samples = sorted(self.hx.read_raw() for _ in range(n))
        return samples[n // 2]

    def _average_raw(self, n=TARE_SAMPLES):
        return sum(self.hx.read_raw() for _ in range(n)) // n

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tare(self):
        """Zero the scale with whatever is on it (including empty platform)."""
        print(f"[{self.name}] Taring ({TARE_SAMPLES} samples)...")
        self.zero_offset = self._average_raw()
        self._tared = True
        self._save_calibration()
        print(f"[{self.name}] Tare done. Offset = {self.zero_offset}")

    def calibrate(self, known_grams: float):
        """Place a known weight on the scale, then call this."""
        if not self._tared:
            raise RuntimeError("Tare first before calibrating")
        print(f"[{self.name}] Calibrating with {known_grams}g ({TARE_SAMPLES} samples)...")
        raw = self._average_raw()
        delta = raw - self.zero_offset
        if delta == 0:
            raise RuntimeError("No weight detected. Check wiring.")
        self.units_per_gram = delta / known_grams
        self._save_calibration()
        print(f"[{self.name}] Calibration done. units_per_gram = {self.units_per_gram:.4f}")

    def read_grams(self) -> float:
        """Return current weight in grams."""
        raw = self._median_raw()
        return (raw - self.zero_offset) / self.units_per_gram

    def read_kg(self) -> float:
        return self.read_grams() / 1000.0

    def is_calibrated(self) -> bool:
        return self._tared and self.units_per_gram != 1.0
