# WQCS touchscreen HMI (lvgl_micropython firmware, ESP32-2432S032C).
#
# Pure operator interface: shows Pico status and sends operator commands.
# All control and safety logic lives on the Pico. Debug console: import console
import time
import lvgl as lv
import hw
from pico_link import PicoLink
from dashboard import Dashboard
from calibration import CalibrationScreen
from settings import SettingsScreen

LINK_TIMEOUT_MS = 3000


class App:
    def __init__(self):
        hw.init()
        self.link = PicoLink()
        self.limits = None
        self.last_rx = None
        self.link_ok = False

        self.dashboard = Dashboard(self.send, self.show_cal, self.show_levels)
        self.cal = CalibrationScreen(self.send, self.show_dashboard)
        self.levels = SettingsScreen(self.send, self.show_dashboard)
        self.active = self.dashboard
        lv.screen_load(self.dashboard.scr)
        self.send("GET:LIMITS")

    def send(self, cmd):
        print("->", cmd)
        self.link.send(cmd)

    def _show(self, screen):
        self.active = screen
        lv.screen_load(screen.scr)
        if self.link.last_status:
            screen.update(self.link.last_status)

    def show_dashboard(self):
        self._show(self.dashboard)

    def show_cal(self):
        self._show(self.cal)

    def show_levels(self):
        self.levels.load(self.limits)
        self._show(self.levels)
        self.send("GET:LIMITS")

    def step(self):
        status = self.link.poll()
        now = time.ticks_ms()

        reply = self.link.last_limits
        if reply is not None:
            self.link.last_limits = None
            self.last_rx = now
            print("<- limits", reply)
            self.limits = reply["limits"]
            self.dashboard.update_limits(self.limits)
            if self.active is self.levels:
                self.levels.on_reply(reply)

        if status is not None:
            self.last_rx = now
            self.link_ok = True
            self.active.update(status)
            if self.active is not self.dashboard:
                self.dashboard.update(status)
            if self.limits is None:
                self.send("GET:LIMITS")  # Pico booted after us, or the reply was lost

        if self.link_ok and (self.last_rx is None or
                             time.ticks_diff(now, self.last_rx) > LINK_TIMEOUT_MS):
            self.link_ok = False
            self.dashboard.show_link_lost(self.link.link_errors)

    def run(self):
        while True:
            self.step()
            time.sleep_ms(20)


try:
    App().run()
except Exception as e:  # KeyboardInterrupt (Ctrl-C from a laptop) is not caught
    import sys
    import machine
    sys.print_exception(e)
    try:
        with open("crash.log", "a") as f:  # survives the reset; read with mpremote cat
            f.write("--- uptime %d ms\n" % time.ticks_ms())
            sys.print_exception(e, f)
    except OSError:
        pass
    print("HMI crashed; hard reset in 5 s (Ctrl-C to stay in the REPL)")
    time.sleep(5)
    # hard, not soft: a soft reset leaves the SPI bus driver with a dangling
    # pointer and the next hw.init() panics (see BUILD.md)
    machine.reset()
