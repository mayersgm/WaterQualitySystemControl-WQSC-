"""Calibration screen.

Scales: TARE (empty platform) then CAL with a reference weight.
TDS probes: ZERO with the probe in clean (distilled) water; the Pico refuses
an offset too large to be clean water.

Commands are only enabled while the system is parked (STOPPED / EMPTY / FAULT)
so nobody calibrates while valves may be open and water moving.
"""
import lvgl as lv
import widgets as w

# key, selector label; scales report "<key>_g", probes "<key>_ppm"
ITEMS = (("boiler", "BOILER"), ("collector", "COLLECT"), ("reservoir", "RESERV"),
         ("tds1", "TDS-1"), ("tds2", "TDS-2"))
PROBES = ("tds1", "tds2")
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
        w.button(card, "Yes", self._yes, 140, 74, 110, 36, w.GREEN, tone=w.TONE_CMD)
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
        w.label(head, "CALIBRATION", w.FONT_M).align(lv.ALIGN.LEFT_MID, 84, 0)

        self.sel = {}
        for i, (key, text) in enumerate(ITEMS):
            self.sel[key] = w.button(self.scr, text, lambda k=key: self._select(k),
                                     4 + i * 63, 36, 59, 30, w.PANEL, w.FONT_S)

        self.reading = w.label(self.scr, "--", w.FONT_L)
        self.reading.align(lv.ALIGN.TOP_MID, 0, 74)

        self.btn_tare = w.button(self.scr, "1. TARE", self._tare, 4, 110, 150, 36, w.BLUE,
                                 tone=w.TONE_CMD)
        self.btn_cal = w.button(self.scr, "2. CAL", self._cal, 166, 110, 150, 36, w.GREEN,
                                tone=w.TONE_CMD)

        # reference-weight row: scales only
        self.ref_row = [w.label(self.scr, "Reference:", color=w.MUTED)]
        self.ref_row[0].set_pos(6, 162)
        for text, delta, x in (("-100", -100, 76), ("-10", -10, 124),
                               ("+10", 10, 226), ("+100", 100, 272)):
            self.ref_row.append(w.button(self.scr, text, lambda d=delta: self._adj(d),
                                         x, 154, 44, 30, w.PANEL, w.FONT_S, tone=w.TONE_ADJ))
        self.ref_lbl = w.label(self.scr, "", w.FONT_M)
        self.ref_lbl.set_pos(174, 160)
        self.ref_row.append(self.ref_lbl)

        self.hint = w.label(self.scr, "", color=w.MUTED)
        self.hint.set_width(312)
        self.hint.set_pos(6, 196)

        self.confirm = Confirm(self.scr)
        self._select("boiler")
        self._adj(0)

    def _select(self, name):
        self.scale = name
        probe = name in PROBES
        for n, b in self.sel.items():
            w.set_bg(b, w.BLUE if n == name else w.PANEL)
        w.set_text(self.reading, "--")
        w.set_button_text(self.btn_tare, "ZERO probe" if probe else "1. TARE")
        for o in [self.btn_cal] + self.ref_row:
            w.set_hidden(o, probe)
        w.set_text(self.hint, 
            "Put the probe in distilled water, then ZERO." if probe else
            "Tare with the platform empty, then CAL with the reference on it.")

    def _adj(self, delta):
        self.ref_g = max(100, min(20000, self.ref_g + delta))
        w.set_text(self.ref_lbl, "%d g" % self.ref_g)

    def _tare(self):
        name = self.scale.upper()
        if self.scale in PROBES:
            self.confirm.ask("Is the %s probe in clean (distilled) water?" % name,
                             lambda: self._send("TDSCAL:" + name, "Zeroing %s..." % name))
            return
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
        w.set_text(self.hint, hint)

    def on_tdscal(self, msg):
        name = msg.get("sensor", "").upper()
        if msg.get("ok"):
            w.set_text(self.hint, "%s zeroed (offset %.3f V)." % (name, msg.get("offset_v", 0)))
        else:
            w.set_text(self.hint, "%s zero refused: %s" % (name, msg.get("err")))

    def update(self, s):
        self.state = s.get("state")
        if self.scale in PROBES:
            ppm = s.get(self.scale + "_ppm")
            w.set_text(self.reading, "--" if ppm is None else "%.1f ppm" % ppm)
        else:
            g = s.get(self.scale + "_g")
            w.set_text(self.reading, "--" if g is None else "%.1f g" % g)
        self.reading.align(lv.ALIGN.TOP_MID, 0, 74)
        ok = self.state in SAFE_STATES
        w.set_enabled(self.btn_tare, ok)
        w.set_enabled(self.btn_cal, ok)
        if not ok:
            w.set_text(self.hint, "Stop the system first (state is %s)." % self.state)
        elif self.hint.get_text().startswith("Stop the system"):
            self._select(self.scale)
