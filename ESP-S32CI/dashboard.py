"""Main operator screen: state, vessel levels, live indicators, commands."""
import lvgl as lv
import widgets as w
from icons import Flame, Drops, Valve, FlowArrow

BAR_Y, BAR_H = 20, 86

STATE_STYLE = {
    "RUN": (w.GREEN, "RUN - distilling"),
    "IDLE": (w.BLUE, "IDLE - filling boiler"),
    "STANDBY": (w.AMBER, "STANDBY - vessels full"),
    "STOPPED": (w.GREY, "STOPPED"),
    "EMPTY": (w.TEAL, "EMPTY - drain mode"),
    "FAULT": (w.RED, "FAULT"),
}

# setpoints drawn as markers on each vessel
MARKERS = {
    "boiler": ("boiler_topoff", "boiler_full"),
    "collector": ("collector_empty", "collector_full"),
    "reservoir": ("reservoir_low", "reservoir_full"),
}


class _Vessel:
    def __init__(self, parent, name, title, x):
        self.name = name
        self.panel = w.box(parent, x, 34, 104, 134)
        w.label(self.panel, title, color=w.MUTED).set_pos(6, 3)
        self.bar = lv.bar(self.panel)
        self.bar.set_pos(8, BAR_Y)
        self.bar.set_size(40, BAR_H)
        self.bar.set_range(0, 100)
        self.bar.set_style_radius(4, 0)
        self.bar.set_style_radius(2, lv.PART.INDICATOR)
        self.bar.set_style_bg_color(lv.color_hex(0x0B1015), 0)
        self.bar.set_style_bg_opa(lv.OPA.COVER, 0)
        self.bar.set_style_bg_color(w.WATER, lv.PART.INDICATOR)
        self.markers = {}
        for key in MARKERS[name]:
            m = w.box(self.panel, 4, BAR_Y, 48, 2, w.AMBER, radius=0)
            m.add_flag(lv.obj.FLAG.HIDDEN)
            self.markers[key] = m
        self.grams = w.label(self.panel, "--", w.FONT_M)
        self.grams.set_pos(6, 110)
        self.pct = w.label(self.panel, "", color=w.MUTED)
        self.pct.set_pos(56, 3)

    def set_weight(self, g):
        p = w.pct(self.name, g)
        self.bar.set_value(p, True)  # LVGL 9: lv_anim_enable_t is a bool, no lv.ANIM enum
        self.grams.set_text(w.fmt_g(g))
        self.pct.set_text("%d%%" % p)

    def set_limits(self, limits):
        for key, m in self.markers.items():
            if key in limits:
                p = w.pct(self.name, limits[key])
                m.set_y(BAR_Y + BAR_H - 1 - (BAR_H * p) // 100)
                m.remove_flag(lv.obj.FLAG.HIDDEN)


class Dashboard:
    def __init__(self, on_command, on_cal, on_levels):
        self.on_command = on_command
        self.scr = w.screen()
        self.cmd = None
        self.frame = 0

        self.banner = w.box(self.scr, 0, 0, 320, 30, w.GREY, radius=0)
        self.state_lbl = w.label(self.banner, "WAITING FOR PICO...", w.FONT_M)
        self.state_lbl.align(lv.ALIGN.LEFT_MID, 8, 0)
        w.button(self.banner, "CAL", on_cal, 222, 2, 44, 26, w.PANEL, w.FONT_S)
        w.button(self.banner, lv.SYMBOL.SETTINGS + " LVL", on_levels, 270, 2, 48, 26,
                 w.PANEL, w.FONT_S)

        self.vessels = {
            "boiler": _Vessel(self.scr, "boiler", "BOILER", 2),
            "collector": _Vessel(self.scr, "collector", "COLLECTOR", 108),
            "reservoir": _Vessel(self.scr, "reservoir", "RESERVOIR", 214),
        }
        bp = self.vessels["boiler"].panel
        self.main_valve = Valve(bp, 54, 20, "MAIN")
        self.drops = Drops(bp, 58, 36)
        self.flame = Flame(bp, 62, 72)
        self.psw = Valve(bp, 54, 112, "PSW")
        cp = self.vessels["collector"].panel
        w.label(cp, "XFER", color=w.MUTED).set_pos(58, 48)
        self.flow = FlowArrow(cp, 56, 64)
        self.animated = (self.flame, self.drops, self.flow)

        self.readouts = w.box(self.scr, 0, 171, 320, 26, w.PANEL, radius=0)
        self.readout_lbl = w.label(self.readouts, "", w.FONT_M)
        self.readout_lbl.align(lv.ALIGN.LEFT_MID, 8, 0)
        self.tds2_badge = w.label(self.readouts, "TDS2 HIGH", color=w.AMBER)
        self.tds2_badge.align(lv.ALIGN.RIGHT_MID, -8, 0)
        self.tds2_badge.add_flag(lv.obj.FLAG.HIDDEN)

        self.fault_bar = w.box(self.scr, 0, 171, 320, 26, w.RED, radius=0)
        self.fault_lbl = w.label(self.fault_bar, "", w.FONT_S)
        self.fault_lbl.align(lv.ALIGN.LEFT_MID, 8, 0)
        w.button(self.fault_bar, "ACK", lambda: on_command("ACK"), 262, 1, 56, 24,
                 lv.color_hex(0x7F0000), w.FONT_M)
        self.fault_bar.add_flag(lv.obj.FLAG.HIDDEN)

        self.btn_start = w.button(self.scr, "START", self._start_stop, 2, 201, 76, 37, w.GREEN)
        self.btn_ster = w.button(self.scr, "STERILIZE", self._sterilize, 82, 201, 76, 37,
                                 w.PURPLE, w.FONT_S)
        self.btn_empty = w.button(self.scr, "EMPTY", self._empty, 162, 201, 76, 37, w.TEAL)
        w.button(self.scr, "RESET", lambda: on_command("RESET"), 242, 201, 76, 37, w.GREY)

        lv.timer_create(self._animate, 150, None)

    # -- commands: labels follow the Pico's reported cmd, not local state --
    def _start_stop(self):
        self.on_command("STOP" if self.cmd == "START" else "START")

    def _sterilize(self):
        self.on_command("STOP" if self.cmd == "STERILIZE" else "STERILIZE")

    def _empty(self):
        self.on_command("STOP" if self.cmd == "EMPTY" else "EMPTY")

    def _animate(self, timer):
        self.frame += 1
        for icon in self.animated:
            icon.step(self.frame)

    # -- data in --
    def update(self, s):
        self.cmd = s.get("cmd")
        state = s.get("state", "")
        color, text = STATE_STYLE.get(state, (w.GREY, state))
        if state == "RUN" and self.cmd == "STERILIZE":
            text = "RUN - sterilizing"
        self.banner.set_style_bg_color(color, 0)
        self.state_lbl.set_style_text_color(
            lv.color_hex(0x10151A) if color == w.AMBER else w.TEXT, 0)
        self.state_lbl.set_text(text)

        for name, v in self.vessels.items():
            v.set_weight(s.get(name + "_g"))

        valves = s.get("valves", {})
        self.main_valve.set_active(bool(valves.get("main")))
        self.drops.set_active(bool(valves.get("refill")))
        self.flow.set_active(bool(valves.get("transfer")))
        self.flame.set_active(bool(s.get("heater")))
        self.psw.set_active(bool(s.get("pressure_sw")))

        temp = s.get("temp_f")
        self.readout_lbl.set_text("%s F   TDS1 %d   TDS2 %d ppm" % (
            "--" if temp is None else "%.0f" % temp,
            s.get("tds1_ppm") or 0, s.get("tds2_ppm") or 0))
        if s.get("alert", {}).get("tds2"):
            self.tds2_badge.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.tds2_badge.add_flag(lv.obj.FLAG.HIDDEN)

        faults = [k for k, on in s.get("fault", {}).items() if on]
        if faults:
            self.fault_lbl.set_text("FAULT: " + ", ".join(faults))
            self.fault_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.fault_bar.add_flag(lv.obj.FLAG.HIDDEN)

        w.set_button_text(self.btn_start, "STOP" if self.cmd == "START" else "START")
        self.btn_start.set_style_bg_color(w.RED if self.cmd == "START" else w.GREEN, 0)
        w.set_button_text(self.btn_ster, "CANCEL" if self.cmd == "STERILIZE" else "STERILIZE")
        w.set_button_text(self.btn_empty, "CANCEL" if self.cmd == "EMPTY" else "EMPTY")

    def update_limits(self, limits):
        for v in self.vessels.values():
            v.set_limits(limits)

    def show_link_lost(self, errors):
        self.banner.set_style_bg_color(w.PURPLE, 0)
        self.state_lbl.set_style_text_color(w.TEXT, 0)
        self.state_lbl.set_text("NO LINK TO PICO" + (" (err %d)" % errors if errors else ""))
