from machine import Pin
from utime import sleep_us


class HX711:
    def __init__(self, dout_pin=16, sck_pin=17, gain=128):
        self.dout = Pin(dout_pin, Pin.IN)
        self.sck = Pin(sck_pin, Pin.OUT)
        self.sck.value(0)

        if gain == 128:
            self._pulse_count = 25
        elif gain == 64:
            self._pulse_count = 27
        elif gain == 32:
            self._pulse_count = 26
        else:
            raise ValueError("gain must be 128, 64, or 32")

        self.power_up()

    def is_ready(self):
        return self.dout.value() == 0

    def wait_ready(self, timeout_ms=1000):
        import utime
        start = utime.ticks_ms()
        while not self.is_ready():
            if utime.ticks_diff(utime.ticks_ms(), start) > timeout_ms:
                raise OSError("HX711 not ready — check wiring")
            sleep_us(100)

    def read_raw(self):
        self.wait_ready()

        value = 0
        for _ in range(24):
            self.sck.value(1)
            sleep_us(1)
            value = (value << 1) | self.dout.value()
            self.sck.value(0)
            sleep_us(1)

        # Extra pulses set the gain/channel for next read
        for _ in range(self._pulse_count - 24):
            self.sck.value(1)
            sleep_us(1)
            self.sck.value(0)
            sleep_us(1)

        # Convert from 24-bit two's complement
        if value & 0x800000:
            value -= 0x1000000

        return value

    def power_down(self):
        self.sck.value(0)
        self.sck.value(1)

    def power_up(self):
        self.sck.value(0)
        sleep_us(100)
