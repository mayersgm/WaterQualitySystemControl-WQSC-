import json
import math
import time
from machine import ADC


class Thermistor:
    """Boiler NTC thermistor, Steinhart-Hart equation (carried over from old main.py)."""

    def __init__(self, adc_pin=26, vref=3.26, series_resistance=100000,
                 beta=3950, nominal_resistance=50000, nominal_temp=25):
        self.adc = ADC(adc_pin)
        self.vref = vref
        self.adc_res = 65535
        self.series_resistance = series_resistance
        self.beta = beta
        self.nominal_temp = nominal_temp
        self.nominal_resistance = nominal_resistance

    def read_fahrenheit(self, num_samples=10):
        adc_sum = 0
        for _ in range(num_samples):
            adc_sum += self.adc.read_u16()
        adc_value = adc_sum / num_samples
        voltage = (adc_value / self.adc_res) * self.vref
        if voltage <= 0 or voltage >= self.vref:
            return None

        resistance = self.series_resistance * (voltage / (self.vref - voltage))
        steinhart = math.log(resistance / self.nominal_resistance) / self.beta
        steinhart += 1.0 / (self.nominal_temp + 273.15)
        celsius = (1.0 / steinhart) - 273.15
        if not (-10 <= celsius <= 150):
            return None
        return (celsius * 9 / 5) + 32


class TDSSensor:
    """
    Median-filtered, temperature-compensated TDS (ppm) reader.
    Two instances are used: TDS-1 (distiller -> collector) and TDS-2
    (distribution pump outlet), each with its own zero-offset calibration
    file, same persistence pattern as Scale's per-vessel calibration files.
    """

    def __init__(self, name, adc_pin, vref=3.26, sample_count=10):
        self.name = name
        self.cal_file = f"tds_cal_{name}.json"
        self.adc = ADC(adc_pin)
        self.vref = vref
        self.adc_res = 65535
        self.sample_count = sample_count
        self.offset_voltage = self._load_offset()

    def _load_offset(self):
        try:
            with open(self.cal_file) as f:
                return json.load(f)["offset_voltage"]
        except (OSError, KeyError, ValueError):
            return 0.0

    def calibrate_zero(self, samples=20):
        """Call with the probe in clean/reference water to zero it out."""
        total = 0
        for _ in range(samples):
            total += self.adc.read_u16()
            time.sleep(0.02)
        self.offset_voltage = (total / samples / self.adc_res) * self.vref
        with open(self.cal_file, "w") as f:
            json.dump({"offset_voltage": self.offset_voltage}, f)
        return self.offset_voltage

    def read_ppm(self, temperature_c=25.0):
        samples = sorted(self.adc.read_u16() for _ in range(self.sample_count))
        median_adc = samples[self.sample_count // 2]
        voltage = (median_adc / self.adc_res) * self.vref - self.offset_voltage
        if voltage < 0.005:
            voltage = 0.0

        compensation = 1.0 + 0.02 * (temperature_c - 25.0)
        compensated_voltage = voltage / compensation

        ppm = (
            133.42 * compensated_voltage ** 3
            - 255.86 * compensated_voltage ** 2
            + 857.39 * compensated_voltage
        ) * 0.5
        return max(0.0, ppm)
