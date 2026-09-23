from machine import Pin, disable_irq, enable_irq
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

        # The SCK/DOUT pulse train is timing-critical -- if any interrupt
        # (including one triggered by the other core, e.g. a sleep timer
        # alarm) stalls a pulse past the HX711's ~60us SCK-high limit, the
        # chip resets mid-conversion and returns a corrupted/garbage value
        # that looks like a fixed near-rail reading rather than an obvious
        # error. Confirmed on real hardware (2026-09-22): a plain
        # `time.sleep_ms()` loop on the other core reliably corrupted every
        # read until this window was made atomic against interrupts.
        irq_state = disable_irq()
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
        enable_irq(irq_state)

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
