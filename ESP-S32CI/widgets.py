"""Small shared LVGL helpers used by every screen (fonts, colors, buttons)."""
import lvgl as lv

FONT_S = lv.font_montserrat_12
FONT_M = lv.font_montserrat_16
FONT_L = lv.font_montserrat_24

BG = lv.color_hex(0x10151A)
PANEL = lv.color_hex(0x1E2730)
TEXT = lv.color_hex(0xE8EEF2)
MUTED = lv.color_hex(0x8A99A6)
WATER = lv.color_hex(0x2E9BEA)
GREEN = lv.color_hex(0x2E7D32)
BLUE = lv.color_hex(0x1565C0)
AMBER = lv.color_hex(0xF9A825)
RED = lv.color_hex(0xC62828)
GREY = lv.color_hex(0x546E7A)
TEAL = lv.color_hex(0x00838F)
PURPLE = lv.color_hex(0x6A1B9A)
DARK_TEXT = lv.color_hex(0x10151A)

# Vessel capacities (grams of water), Phase0_Design.md sec 3.
CAPACITY = {"boiler": 3785, "collector": 7570, "reservoir": 34065}


def screen():
    scr = lv.obj()
    scr.set_style_bg_color(BG, 0)
    scr.set_style_text_color(TEXT, 0)
    scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return scr


def box(parent, x, y, w, h, color=PANEL, radius=6):
    o = lv.obj(parent)
    o.set_pos(x, y)
    o.set_size(w, h)
    o.set_style_bg_color(color, 0)
    o.set_style_bg_opa(lv.OPA.COVER, 0)
    o.set_style_border_width(0, 0)
    o.set_style_radius(radius, 0)
    o.set_style_pad_all(0, 0)
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    o.remove_flag(lv.obj.FLAG.CLICKABLE)
    return o


def label(parent, text, font=FONT_S, color=TEXT):
    lb = lv.label(parent)
    lb.set_text(text)
    lb.set_style_text_font(font, 0)
    lb.set_style_text_color(color, 0)
    return lb


# Called on every button press (set by main.py to the speaker's click).
on_press = None


def _pressed(e):
    if on_press is not None:
        on_press()


def button(parent, text, on_click, x, y, w, h, color=GREY, font=FONT_M):
    b = lv.button(parent)
    b.set_pos(x, y)
    b.set_size(w, h)
    b.set_style_bg_color(color, 0)
    b.set_style_radius(6, 0)
    lb = lv.label(b)
    lb.set_text(text)
    lb.set_style_text_font(font, 0)
    lb.center()
    b.add_event_cb(lambda e: on_click(), lv.EVENT.CLICKED, None)
    b.add_event_cb(_pressed, lv.EVENT.PRESSED, None)   # click on touch-down: feels immediate
    return b


# LVGL allocates from the MicroPython heap. Every label set_text() reallocates
# its text buffer and every style change forces a redraw with large temporary
# buffers, so doing either with an unchanged value just fragments the heap
# (which caused a MemoryError freeze). Remember the last value per object and
# skip no-op updates. Keys use id(): all these objects live for the whole run.
_last = {}


def forget_all():
    """Call after deleting LVGL objects: their ids may be reused by new ones,
    which would otherwise match stale entries and skip real updates."""
    _last.clear()


def changed(obj, prop, value):
    key = (id(obj), prop)
    if _last.get(key) == value:
        return False
    _last[key] = value
    return True


def set_text(lbl, text):
    if changed(lbl, "text", text):
        lbl.set_text(text)


# colors are the module-level lv.color_t constants above, so identity
# comparison is enough to detect a change
def set_text_color(obj, color):
    if changed(obj, "text_color", color):
        obj.set_style_text_color(color, 0)


def set_bg(obj, color):
    if changed(obj, "bg", color):
        obj.set_style_bg_color(color, 0)


def set_button_text(btn, text):
    # LVGL objects can't carry extra Python attributes; the label is child 0.
    if changed(btn, "text", text):
        btn.get_child(0).set_text(text)


def set_hidden(obj, hidden):
    if changed(obj, "hidden", hidden):
        if hidden:
            obj.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            obj.remove_flag(lv.obj.FLAG.HIDDEN)


def set_enabled(btn, enabled):
    if not changed(btn, "enabled", enabled):
        return
    if enabled:
        btn.remove_state(lv.STATE.DISABLED)
    else:
        btn.add_state(lv.STATE.DISABLED)


def fmt_g(g):
    if g is None:
        return "--"
    return "%.1f kg" % (g / 1000) if abs(g) >= 1000 else "%d g" % g


def pct(vessel, g):
    return max(0, min(100, int(100 * g / CAPACITY[vessel]))) if g is not None else 0
