"""Display/touch bring-up check. From the REPL:  import hwtest; hwtest.run(30)
Touch mapping check (one target at a time):  hwtest.touch_map()

Shows red/green/blue swatches (verifies color byte order) and four corner
targets (verifies rotation), and prints every touch point so touch mapping
can be compared against where the finger actually was.
"""
import time
import lvgl as lv
import hw


def run(seconds=30):
    hw.init()
    scr = lv.obj()
    scr.set_style_bg_color(lv.color_hex(0x000000), 0)
    scr.remove_flag(lv.obj.FLAG.SCROLLABLE)

    for i, (name, hexv) in enumerate((("RED", 0xFF0000), ("GREEN", 0x00FF00), ("BLUE", 0x0000FF))):
        sw = lv.obj(scr)
        sw.set_size(90, 50)
        sw.set_pos(10 + i * 100, 95)
        sw.set_style_bg_color(lv.color_hex(hexv), 0)
        sw.remove_flag(lv.obj.FLAG.CLICKABLE)
        lb = lv.label(sw)
        lb.set_text(name)
        lb.set_style_text_color(lv.color_hex(0xFFFFFF if name == "BLUE" else 0x000000), 0)
        lb.center()

    for name, align in (("TL", lv.ALIGN.TOP_LEFT), ("TR", lv.ALIGN.TOP_RIGHT),
                        ("BL", lv.ALIGN.BOTTOM_LEFT), ("BR", lv.ALIGN.BOTTOM_RIGHT)):
        lb = lv.label(scr)
        lb.set_text(name)
        lb.set_style_text_font(lv.font_montserrat_24, 0)
        lb.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        lb.align(align, 0, 0)

    title = lv.label(scr)
    title.set_text("Touch each corner")
    title.set_style_text_color(lv.color_hex(0xFFFF00), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 40)

    dot = lv.obj(scr)
    dot.set_size(12, 12)
    dot.set_style_radius(6, 0)
    dot.set_style_bg_color(lv.color_hex(0xFF00FF), 0)
    dot.remove_flag(lv.obj.FLAG.CLICKABLE)
    dot.add_flag(lv.obj.FLAG.HIDDEN)

    def on_press(e):
        p = lv.point_t()
        lv.indev_active().get_point(p)
        print("touch", p.x, p.y)
        dot.set_pos(p.x - 6, p.y - 6)
        dot.remove_flag(lv.obj.FLAG.HIDDEN)

    scr.add_event_cb(on_press, lv.EVENT.PRESSED, None)
    lv.screen_load(scr)
    print("display", lv.display_get_default().get_horizontal_resolution(), "x",
          lv.display_get_default().get_vertical_resolution())

    end = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        time.sleep_ms(20)
    print("done")


TARGETS = (("top-left", 20, 20), ("top-right", 300, 20), ("bottom-right", 300, 220),
           ("bottom-left", 20, 220), ("center", 160, 120))


def touch_map(timeout_s=90):
    """Show one crosshair at a time; for each touch log the raw GT911 point,
    the driver's transformed point, and LVGL's final point, next to the target."""
    _, indev = hw.init()
    raw = {}
    orig_calc = indev._calc_coords

    def spy(x, y):
        out = orig_calc(x, y)
        raw["in"], raw["out"] = (x, y), out
        return out

    indev._calc_coords = spy

    scr = lv.obj()
    scr.set_style_bg_color(lv.color_hex(0x000000), 0)
    scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
    cross = lv.label(scr)
    cross.set_text(lv.SYMBOL.PLUS)
    cross.set_style_text_font(lv.font_montserrat_24, 0)
    cross.set_style_text_color(lv.color_hex(0x00FF00), 0)
    msg = lv.label(scr)
    msg.set_style_text_color(lv.color_hex(0xFFFF00), 0)
    msg.align(lv.ALIGN.CENTER, 0, 30)
    state = {"i": 0, "armed": True}

    def show():
        name, x, y = TARGETS[state["i"]]
        cross.set_pos(x - 8, y - 12)
        msg.set_text("Touch the green + (%s) %d/%d" % (name, state["i"] + 1, len(TARGETS)))

    def on_press(e):
        if not state["armed"] or state["i"] >= len(TARGETS):
            return
        state["armed"] = False
        p = lv.point_t()
        lv.indev_active().get_point(p)
        name, tx, ty = TARGETS[state["i"]]
        print("TARGET %-12s (%3d,%3d)  raw %s  driver %s  lvgl (%d,%d)" % (
            name, tx, ty, raw.get("in"), raw.get("out"), p.x, p.y))

    def on_release(e):
        if state["armed"]:
            return
        state["armed"] = True
        state["i"] += 1
        if state["i"] < len(TARGETS):
            show()
        else:
            msg.set_text("Done - thank you")
            cross.add_flag(lv.obj.FLAG.HIDDEN)

    scr.add_event_cb(on_press, lv.EVENT.PRESSED, None)
    scr.add_event_cb(on_release, lv.EVENT.RELEASED, None)
    lv.screen_load(scr)
    show()

    end = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while state["i"] < len(TARGETS) and time.ticks_diff(end, time.ticks_ms()) > 0:
        time.sleep_ms(20)
    indev._calc_coords = orig_calc
    print("done", state["i"], "of", len(TARGETS))
