"""Fake MicroPython modules so Pico/main.py's real control logic runs on the Mac.

Import this module before importing Pico `main`; then build a harness with
make_controller(), which swaps the hardware sensors for scripted fakes.
"""
import os
import sys
import types

PICO = os.path.join(os.path.dirname(__file__), "..", "Pico")


class Pin:
    OUT, IN, OPEN_DRAIN, PULL_UP, PULL_DOWN = 1, 2, 3, 4, 5

    def __init__(self, num, mode=None, pull=None, value=None):
        self.num, self._v = num, 0 if value is None else value

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = v

    def init(self, *a, **k):
        pass


class _Dummy:
    def __init__(self, *a, **k):
        pass

    def read_u16(self):
        return 0

    def any(self):
        return 0


def install():
    sys.modules["machine"] = types.SimpleNamespace(
        Pin=Pin, UART=_Dummy, ADC=_Dummy,
        disable_irq=lambda: 0, enable_irq=lambda s: None)
    sys.modules["utime"] = types.SimpleNamespace(sleep_us=lambda us: None)

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    sys.modules["_thread"] = types.SimpleNamespace(allocate_lock=_Lock,
                                                   start_new_thread=lambda f, a: None)
    if PICO not in sys.path:
        sys.path.insert(0, PICO)


class FakeClock:
    now = 0

    @classmethod
    def ticks_ms(cls):
        return cls.now

    @staticmethod
    def ticks_diff(a, b):
        return a - b

    @staticmethod
    def sleep(s):
        pass


class Value:
    """Scripted sensor: tests set .v; read methods return it."""

    def __init__(self, v=0.0):
        self.v = v

    def read_grams(self):
        return self.v

    def read_ppm(self, *a):
        return self.v

    def read_fahrenheit(self):
        return self.v


def make_controller(workdir):
    """A real Wqcs with fake sensors, running in `workdir` (for limits.json)."""
    install()
    os.chdir(workdir)
    import main
    main.time = FakeClock
    main.print = lambda *a, **k: None
    w = main.Wqcs()
    w.scales = {n: Value() for n in ("boiler", "collector", "reservoir")}
    w.thermistor = Value(70.0)
    w.tds1, w.tds2 = Value(0.0), Value(0.0)
    return main, w
