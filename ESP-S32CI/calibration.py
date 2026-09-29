"""Scale calibration screen: TARE (empty platform) then CAL with a reference weight.

Commands are only enabled while the system is parked (STOPPED / EMPTY / FAULT)
so nobody tares a scale while valves may be open and water moving.
"""
import lvgl as lv
import widgets as w

SCALES = ("boiler", "collector", "reservoir")
SAFE_STATES = ("STOPPED", "EMPTY", "FAULT")


class Confirm:
    """Minimal modal yes/no overlay."""

    def __init__(self, parent):
        self.root = w.box(parent, 0, 0, 320, 240, lv.color_hex(0x000000), radius=0)
        self.root.set_style_bg_opa(lv.OPA._70, 0)
        self.root.add_flag(lv.obj.FLAG.CLICKABLE)  # swallow touches behind it
        card = w.box(self.root, 30, 60, 260, 120)
        self.msg = w.label(card, "", w.FONT_M)
        self.msg.set_width(240)
        self.msg.set_pos(10, 12)
        self.on_yes = None
        w.button(card, "Cancel", self.hide, 10, 74, 110, 36, w.GREY)
        w.button(card, "Yes", self._yes, 140, 74, 110, 36, w.GREEN)
        self.hide()

    def ask(self, text, on_yes):
        self.msg.set_text(text)
        self.on_yes = on_yes
        self.root.remove_flag(lv.obj.FLAG.HIDDEN)
        self.root.move_foreground()

    def hide(self):
        self.root.add_flag(lv.obj.FLAG.HIDDEN)

    def _yes(self):
        self.hide()
        if self.on_yes:
            self.on_yes()


class CalibrationScreen:
    def __init__(self, on_command, on_back):
        self.on_command = on_command
        self.scr = w.screen()
        self.scale = "boiler"
        self.ref_g = 1000
        self.state = None

        head = w.box(self.scr, 0, 0, 320, 30, w.PANEL, radius=0)
        w.button(head, lv.SYMBOL.LEFT + " Back", on_back, 2, 2, 70, 26, w.GREY, w.FONT_S)
        w.label(head, "SCALE CALIBRATION", w.FONT_M).align(lv.ALIGN.LEFT_MID, 84, 0)

        self.sel = {}
        for i, name in enumerate(SCALES):
            self.sel[name] = w.button(self.scr, name.upper(),
                                      lambda n=name: self._select(n),
                                      4 + i * 105, 36, 101, 30, w.PANEL, w.FONT_S)

        self.reading = w.label(self.scr, "--", w.FONT_L)
        self.reading.align(lv.ALIGN.TOP_MID, 0, 74)

        self.btn_tare = w.button(self.scr, "1. TARE", self._tare, 4, 110, 150, 36, w.BLUE)
        self.btn_cal = w.button(self.scr, "2. CAL", self._cal, 166, 110, 150, 36, w.GREEN)

        w.label(self.scr, "Reference:", color=w.MUTED).set_pos(6, 162)
        for text, delta, x in (("-100", -100, 76), ("-10", -10, 124)):
            w.button(self.scr, text, lambda d=delta: self._adj(d), x, 154, 44, 30, w.PANEL, w.FONT_S)
        self.ref_lbl = w.label(self.scr, "", w.FONT_M)
        self.ref_lbl.set_pos(174, 160)
        for text, delta, x in (("+10", 10, 226), ("+100", 100, 272)):
            w.button(self.scr, text, lambda d=delta: self._adj(d), x, 154, 44, 30, w.PANEL, w.FONT_S)

        self.hint = w.label(self.scr, "", color=w.MUTED)
        self.hint.set_width(312)
        self.hint.set_pos(6, 196)

        self.confirm = Confirm(self.scr)
        self._select("boiler")
        self._adj(0)

    def _select(self, name):
        self.scale = name
        for n, b in self.sel.items():
            b.set_style_bg_color(w.BLUE if n == name else w.PANEL, 0)
        self.reading.set_text("--")

    def _adj(self, delta):
        self.ref_g = max(100, min(20000, self.ref_g + delta))
        self.ref_lbl.set_text("%d g" % self.ref_g)

    def _tare(self):
        name = self.scale.upper()
        self.confirm.ask("Is the %s platform completely empty?" % name,
                         lambda: self._send("TARE:" + name,
                                            "Sent TARE. Reading should settle near 0 g."))

    def _cal(self):
        name = self.scale.upper()
        self.confirm.ask("Is exactly %d g on the %s platform?" % (self.ref_g, name),
                         lambda: self._send("CAL:%s:%d" % (name, self.ref_g),
                                            "Sent CAL. Reading should settle near %d g." % self.ref_g))

    def _send(self, cmd, hint):
        self.on_command(cmd)
        self.hint.set_text(hint)

    def update(self, s):
        self.state = s.get("state")
        g = s.get(self.scale + "_g")
        self.reading.set_text("--" if g is None else "%.1f g" % g)
        self.reading.align(lv.ALIGN.TOP_MID, 0, 74)
        ok = self.state in SAFE_STATES
        w.set_enabled(self.btn_tare, ok)
        w.set_enabled(self.btn_cal, ok)
        if not ok:
            self.hint.set_text("Stop the system first (state is %s)." % self.state)
        elif self.hint.get_text().startswith("Stop the system"):
            self.hint.set_text("Tare with the platform empty, then CAL with the reference on it.")
