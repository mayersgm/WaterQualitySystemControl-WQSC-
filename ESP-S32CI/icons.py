"""Animated status indicators built from LVGL shapes/symbols (no image files).

Each indicator has set_active(bool) and step(frame); the dashboard calls
step() from one ~150 ms LVGL timer so every animation shares a clock.
"""
import lvgl as lv
from widgets import box, label, AMBER, RED, WATER, GREY, GREEN, MUTED, FONT_M

_FLICKER = (0, 2, 1, 3, 1, 0, 2, 3)


class Flame:
    """Heater: three stacked flame blobs that flicker while on, grey when off."""

    def __init__(self, parent, x, y):
        self.root = box(parent, x, y, 24, 30, color=lv.color_hex(0x000000), radius=0)
        self.root.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self.outer = box(self.root, 2, 6, 20, 24, RED, radius=10)
        self.mid = box(self.root, 5, 11, 14, 19, lv.color_hex(0xFF7A00), radius=8)
        self.inner = box(self.root, 8, 17, 8, 13, AMBER, radius=5)
        self.active = None
        self.set_active(False)

    def set_active(self, on):
        if on == self.active:
            return
        self.active = on
        for part in (self.outer, self.mid, self.inner):
            part.set_style_bg_opa(lv.OPA.COVER if on else lv.OPA._30, 0)
        if not on:
            self.outer.set_style_bg_color(GREY, 0)
            self.mid.set_style_bg_color(GREY, 0)
            self.inner.set_style_bg_color(GREY, 0)
        else:
            self.outer.set_style_bg_color(RED, 0)
            self.mid.set_style_bg_color(lv.color_hex(0xFF7A00), 0)
            self.inner.set_style_bg_color(AMBER, 0)

    def step(self, frame):
        if not self.active:
            return
        f = _FLICKER[frame % len(_FLICKER)]
        self.outer.set_height(21 + f)
        self.outer.set_y(9 - f)
        self.mid.set_height(15 + f)
        self.mid.set_y(15 - f)
        self.inner.set_height(9 + (3 - f))
        self.inner.set_y(21 - (3 - f))


class Drops:
    """Refill: water-drop symbols falling while the refill valve is open."""

    def __init__(self, parent, x, y, height=26):
        self.x, self.y, self.height = x, y, height
        self.drops = []
        for i in range(2):
            d = label(parent, lv.SYMBOL.TINT, FONT_M, WATER)
            d.set_pos(x + i * 10, y)
            self.drops.append(d)
        self.active = None
        self.set_active(False)

    def set_active(self, on):
        if on == self.active:
            return
        self.active = on
        for d in self.drops:
            if on:
                d.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                d.add_flag(lv.obj.FLAG.HIDDEN)

    def step(self, frame):
        if not self.active:
            return
        for i, d in enumerate(self.drops):
            phase = (frame * 4 + i * self.height // 2) % self.height
            d.set_y(self.y + phase)


class Valve:
    """Static open/closed valve badge: filled green when open, grey outline when closed."""

    def __init__(self, parent, x, y, text):
        self.dot = box(parent, x, y + 2, 10, 10, GREY, radius=5)
        self.lbl = label(parent, text, color=MUTED)
        self.lbl.set_pos(x + 14, y)
        self.active = None
        self.set_active(False)

    def set_active(self, on):
        if on == self.active:
            return
        self.active = on
        self.dot.set_style_bg_color(GREEN if on else GREY, 0)
        self.dot.set_style_bg_opa(lv.OPA.COVER if on else lv.OPA._40, 0)
        self.lbl.set_style_text_color(GREEN if on else MUTED, 0)

    def step(self, frame):
        pass


class FlowArrow:
    """Transfer: a row of chevrons with a highlight sweeping left-to-right."""

    def __init__(self, parent, x, y, count=3):
        self.chevrons = []
        for i in range(count):
            c = label(parent, lv.SYMBOL.RIGHT, FONT_M, MUTED)
            c.set_pos(x + i * 11, y)
            self.chevrons.append(c)
        self.active = None
        self.set_active(False)

    def set_active(self, on):
        if on == self.active:
            return
        self.active = on
        for c in self.chevrons:
            c.set_style_text_color(MUTED, 0)
            c.set_style_text_opa(lv.OPA._40 if not on else lv.OPA.COVER, 0)

    def step(self, frame):
        if not self.active:
            return
        lit = frame % len(self.chevrons)
        for i, c in enumerate(self.chevrons):
            c.set_style_text_color(WATER if i == lit else MUTED, 0)
