"""Water-level settings screen: operator-adjustable fill/drain setpoints.

Edits are local until Save, which sends all six values as one atomic SET so
the Pico validates them as a set. The Pico is the authority (it also enforces
the overflow ceiling / dry-tank floor it doesn't share); the ordering check
here just stops obviously invalid edits before they're sent.
"""
import lvgl as lv
import widgets as w

MIN_GAP_G = 200  # mirrors Pico/limits.py

# key, label, vessel, step (g)
ROWS = (
    ("boiler_topoff", "Boiler refill below", "boiler", 50),
    ("boiler_full", "Boiler FULL", "boiler", 50),
    ("collector_empty", "Collector EMPTY", "collector", 100),
    ("collector_full", "Collector FULL", "collector", 100),
    # the transfer only starts when reservoir + collector fit under this
    ("reservoir_full", "Reservoir capacity", "reservoir", 500),
)
PAIRS = (("boiler_topoff", "boiler_full"), ("collector_empty", "collector_full"))


class SettingsScreen:
    def __init__(self, on_command, on_back):
        self.on_command = on_command
        self.scr = w.screen()
        self.values = None
        self.saved = None
        self.pending = False  # a SET / RESET_LIMITS is awaiting the Pico's reply

        head = w.box(self.scr, 0, 0, 320, 30, w.PANEL, radius=0)
        w.button(head, lv.SYMBOL.LEFT + " Back", on_back, 2, 2, 70, 26, w.GREY, w.FONT_S)
        w.label(head, "WATER LEVELS", w.FONT_M).align(lv.ALIGN.LEFT_MID, 84, 0)

        self.val_lbls = {}
        for i, (key, text, vessel, step) in enumerate(ROWS):
            y = 34 + i * 27
            w.label(self.scr, text, color=w.MUTED).set_pos(6, y + 5)
            lbl = w.label(self.scr, "--", w.FONT_M)
            lbl.set_pos(132, y + 3)
            self.val_lbls[key] = lbl
            for sym, sign, x in ((lv.SYMBOL.MINUS, -1, 234), (lv.SYMBOL.PLUS, 1, 278)):
                b = w.button(self.scr, sym, lambda k=key, d=sign * step: self._adj(k, d),
                             x, y, 40, 25, w.PANEL, w.FONT_S, tone=w.TONE_ADJ)
                b.add_event_cb(lambda e, k=key, d=sign * step: self._adj(k, d),
                               lv.EVENT.LONG_PRESSED_REPEAT, None)

        # full-width message line between the rows (end at y=167) and the
        # buttons (y=201): two lines fit, enough for any Pico rejection reason
        self.status = w.label(self.scr, "", color=w.MUTED)
        self.status.set_width(308)
        self.status.set_pos(6, 170)
        w.button(self.scr, "Defaults", self._defaults, 2, 201, 110, 37, w.GREY, w.FONT_S,
                 tone=w.TONE_CMD)
        self.btn_save = w.button(self.scr, lv.SYMBOL.SAVE + " Save", self._save,
                                 208, 201, 110, 37, w.GREEN, tone=w.TONE_CMD)
        w.set_enabled(self.btn_save, False)
        w.set_text(self.status, "Waiting for Pico limits...")

    def load(self, limits):
        """Called when the screen is opened: start editing from the Pico's values."""
        if limits is None:
            return
        self.values = dict(limits)
        self.saved = dict(limits)
        self._refresh("")

    def on_reply(self, msg):
        """Any limits line from the Pico while this screen is open."""
        if not self.pending:
            # plain GET:LIMITS: take it unless the operator has unsaved edits
            if self.values is None or self.values == self.saved:
                self.load(msg["limits"])
            return
        self.pending = False
        self.saved = dict(msg["limits"])
        if msg.get("ok"):
            self.values = dict(self.saved)
            self._refresh("Saved.")
        else:
            self._refresh("Rejected: %s" % msg.get("err"))

    def _adj(self, key, delta):
        if self.values is None:
            return
        self.values[key] = max(0, self.values[key] + delta)
        self._refresh("")

    def _problem(self):
        for lo, hi in PAIRS:
            if self.values[lo] + MIN_GAP_G > self.values[hi]:
                return "%s too close to %s" % (lo.split("_")[1], hi.split("_")[1])
        for key, _, vessel, _ in ROWS:
            if self.values[key] > w.CAPACITY[vessel]:
                return "%s over capacity" % key
        if self.values["reservoir_full"] < self.values["collector_full"]:
            return "reservoir smaller than a full collector"
        return None

    def _refresh(self, note):
        # change-only updates: +/- auto-repeats ~10x/s, and redrawing every
        # label each time fragmented the heap until the HMI reset (2026-10-03)
        for key, _, vessel, _ in ROWS:
            g = self.values[key]
            changed = self.saved is not None and g != self.saved.get(key)
            w.set_text(self.val_lbls[key], "%s %d%%" % (w.fmt_g(g), w.pct(vessel, g)))
            w.set_text_color(self.val_lbls[key], w.AMBER if changed else w.TEXT)
        problem = self._problem()
        dirty = self.values != self.saved
        w.set_enabled(self.btn_save, dirty and problem is None)
        w.set_text(self.status, problem or note or ("Unsaved changes" if dirty else ""))
        w.set_text_color(self.status, w.RED if problem else w.MUTED)

    def _save(self):
        body = ",".join("%s=%d" % (r[0].upper(), self.values[r[0]]) for r in ROWS)
        self.pending = True
        self.on_command("SET:" + body)
        w.set_text(self.status, "Saving...")

    def _defaults(self):
        self.pending = True
        self.on_command("RESET_LIMITS")
        w.set_text(self.status, "Restoring defaults...")

    def update(self, s):
        pass
