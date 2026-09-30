# WQCS touchscreen HMI (lvgl_micropython firmware, ESP32-2432S032C).
#
# Pure operator interface: shows Pico status and sends operator commands.
# All control and safety logic lives on the Pico. Debug console: import console
import gc
import sys
import time
import machine
import lvgl as lv
import hw
from pico_link import PicoLink
from dashboard import Dashboard
from calibration import CalibrationScreen
from settings import SettingsScreen
from alarm import Alarm

LINK_TIMEOUT_MS = 3000
HEAP_LOG_MS = 60 * 1000
GC_EVERY_MS = 1000              # frequent collection keeps free heap contiguous
LV_ERRORS_BEFORE_RESET = 5      # within LV_ERROR_WINDOW_MS
LV_ERROR_WINDOW_MS = 60 * 1000

# Hardware watchdog: fed only while the LVGL render loop is proven alive, so a
# render stall *or* a whole-program hang reboots the HMI instead of leaving a
# frozen screen. Armed late so tools/esp_deploy.py can still break in at boot.
WDT_ARM_AFTER_MS = 20000
WDT_TIMEOUT_MS = 10000
RENDER_STALL_MS = 5000


def log_crash(tag, e):
    """Print and append to crash.log (survives resets; read with mpremote cat)."""
    sys.print_exception(e)
    if isinstance(e, MemoryError):
        return  # writing the file needs memory we may not have
    try:
        with open("crash.log", "a") as f:
            f.write("--- %s uptime %d ms, heap free %d\n" % (tag, time.ticks_ms(), gc.mem_free()))
            sys.print_exception(e, f)
    except Exception:  # never let logging raise inside an error handler
        pass


def note(text):
    try:
        with open("crash.log", "a") as f:
            f.write("--- %s\n" % text)
    except Exception:
        pass


class App:
    def __init__(self):
        self._lv_errors = []
        if machine.reset_cause() == machine.WDT_RESET:
            print("booted after a WATCHDOG reset")
            note("watchdog reset (render stall or hang) detected at boot")
        hw.init(exception_hook=self._on_lv_error)
        self.link = PicoLink()
        self.limits = None
        self.last_rx = None
        self.link_ok = False

        self.alarm = Alarm()
        self.dashboard = Dashboard(self.send, self.show_cal, self.show_levels, self.ack)
        self.cal = CalibrationScreen(self.send, self.show_dashboard)
        self.levels = SettingsScreen(self.send, self.show_dashboard)
        self.active = self.dashboard
        lv.screen_load(self.dashboard.scr)
        self.send("GET:LIMITS")

    def _on_lv_error(self, e):
        # An exception in an LVGL callback: log it and keep rendering, but
        # hard-reset if they keep coming. Out of memory mid-render leaves
        # LVGL in an unknown state, so reset immediately (~3 s to recover).
        if isinstance(e, MemoryError):
            print("MemoryError in render; hard reset")
            machine.reset()
        log_crash("lvgl callback", e)
        now = time.ticks_ms()
        self._lv_errors = [t for t in self._lv_errors
                           if time.ticks_diff(now, t) < LV_ERROR_WINDOW_MS] + [now]
        if len(self._lv_errors) >= LV_ERRORS_BEFORE_RESET:
            print("repeated LVGL errors; hard reset")
            machine.reset()

    def ack(self):
        """ACK silences the alarm for the faults latched now, then clears them on the Pico."""
        faults = [k for k, on in self.link.last_status.get("fault", {}).items() if on]
        self.alarm.silence(faults)
        self.send("ACK")

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

        tdscal = self.link.last_tdscal
        if tdscal is not None:
            self.link.last_tdscal = None
            print("<- tdscal", tdscal)
            self.cal.on_tdscal(tdscal)

        if self.link_ok and (self.last_rx is None or
                             time.ticks_diff(now, self.last_rx) > LINK_TIMEOUT_MS):
            self.link_ok = False
            self.dashboard.show_link_lost(self.link.link_errors)

        self.alarm.update(status, self.link_ok)

    def run(self):
        last_heap_log = last_gc = time.ticks_ms()
        wdt = None
        last_frame, frame_seen = -1, time.ticks_ms()
        while True:
            self.step()
            now = time.ticks_ms()

            # render liveness: the dashboard's lv timer only runs while LVGL does
            if self.dashboard.frame != last_frame:
                last_frame, frame_seen = self.dashboard.frame, now
            if wdt is None and now > WDT_ARM_AFTER_MS:
                wdt = machine.WDT(timeout=WDT_TIMEOUT_MS)
                print("watchdog armed")
            if wdt is not None and time.ticks_diff(now, frame_seen) < RENDER_STALL_MS:
                wdt.feed()

            if time.ticks_diff(now, last_heap_log) > HEAP_LOG_MS:
                last_heap_log = last_gc = now
                before = gc.mem_free()
                gc.collect()
                # "after" is the real headroom; a steady decline means a leak
                print("heap free before/after gc %d/%d uptime s %d" % (
                    before, gc.mem_free(), now // 1000))
            elif time.ticks_diff(now, last_gc) > GC_EVERY_MS:
                last_gc = now
                gc.collect()
            time.sleep_ms(20)


try:
    App().run()
except Exception as e:  # KeyboardInterrupt (Ctrl-C from a laptop) is not caught
    log_crash("main loop", e)
    print("HMI crashed; hard reset in 5 s (Ctrl-C to stay in the REPL)")
    time.sleep(5)
    # hard, not soft: a soft reset leaves the SPI bus driver with a dangling
    # pointer and the next hw.init() panics (see BUILD.md)
    machine.reset()
