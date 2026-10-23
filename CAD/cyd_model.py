"""STEP model of the ESP32-2432S032C (Sunton 3.2" "Cheap Yellow Display", capacitive).

No vendor 3D model exists (the manufacturer pack has only a front drawing), so
this is built from that drawing plus the user's caliper measurements
(2026-10-22). It's accurate where it matters for enclosures: outline, holes,
glass, active area, stack height, back depth, USB-C and RGB LED position.
Back-side parts are a single envelope (exact connector positions unknown).

Frame (front view = screen side, landscape): +X right (USB-C end), +Y up,
+Z out of the screen. Origin = board centre on the PCB's back face.
  PCB back z 0, front z 1.6; glass front z 1.6 + STACK; back parts to -BACK.

Run:  ~/venvs/cad/bin/python CAD/cyd_model.py   -> CAD/ESP32-2432S032C.step
Import cyd_model.board_parts() for fit checks.
"""
import os

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))

PCB_W, PCB_H, PCB_T = 93.7, 55.0, 1.6        # drawing
HOLES = (86.7, 48.0)                          # drawing; dia 3.2 (R1.6)
HOLE_D = 3.2
GLASS = (77.3, 54.6)                          # edges 4.7 mm inside the hole centres (drawing)
ACTIVE = (64.8, 48.6)                         # spec sheet
ACTIVE_DX = -2.6                              # toward the LED end (left in this frame)
STACK = 4.9                                   # measured 4.8-5.0: PCB front to glass front
BACK = 5.0                                    # measured: back connectors
BACK_SPEAKER = 7.0                            # measured: with the speaker plugged in
BACK_MARGIN = 4.0                             # envelope keeps clear of the hole margins
SPEAKER_PLUG = (12.0, 10.0, -30.0, 0.0)       # w, h, centre x, centre y: "more to the left" (approx)
USB_C = (7.4, 9.0, 3.2, 0.6)                  # depth (x), width (y), height (z), overhang past the edge
RGB_LED = (5.0, 5.0, 1.6, -PCB_W / 2 + 1.75 + 2.5, -PCB_H / 2 + 9.2)   # w, h, t, centre x, y (measured)


def board_parts():
    """{name: solid} in the board frame."""
    pcb = (cq.Workplane("XY").rect(PCB_W, PCB_H).extrude(PCB_T).edges("|Z").fillet(1.0)
           .faces(">Z").workplane()
           .rect(HOLES[0], HOLES[1], forConstruction=True).vertices().hole(HOLE_D)).val()
    front = PCB_T
    module = cq.Solid.makeBox(GLASS[0], GLASS[1], STACK - 0.3,
                              cq.Vector(-GLASS[0] / 2, -GLASS[1] / 2, front))
    glass = cq.Solid.makeBox(GLASS[0], GLASS[1], 0.3,
                             cq.Vector(-GLASS[0] / 2, -GLASS[1] / 2, front + STACK - 0.3))
    active = cq.Solid.makeBox(ACTIVE[0], ACTIVE[1], 0.05,
                              cq.Vector(ACTIVE_DX - ACTIVE[0] / 2, -ACTIVE[1] / 2, front + STACK - 0.04))
    ew, eh = PCB_W - 2 * BACK_MARGIN - 6, PCB_H - 2 * BACK_MARGIN
    back = cq.Solid.makeBox(ew, eh, BACK, cq.Vector(-ew / 2, -eh / 2, -BACK))
    sw, sh, sx, sy = SPEAKER_PLUG
    plug = cq.Solid.makeBox(sw, sh, BACK_SPEAKER - BACK, cq.Vector(sx - sw / 2, sy - sh / 2, -BACK_SPEAKER))
    ud, uw, uh, over = USB_C
    usb = cq.Solid.makeBox(ud, uw, uh, cq.Vector(PCB_W / 2 + over - ud, -uw / 2, -uh))
    lw, lh, lt, lx, ly = RGB_LED
    led = cq.Solid.makeBox(lw, lh, lt, cq.Vector(lx - lw / 2, ly - lh / 2, front))
    return {"pcb": pcb, "display_module": module, "glass": glass, "active_area": active,
            "back_parts_envelope": back, "speaker_plug_zone": plug, "usb_c": usb, "rgb_led": led}


COLORS = {"pcb": (0.95, 0.8, 0.1), "display_module": (0.2, 0.2, 0.2), "glass": (0.3, 0.4, 0.5),
          "active_area": (0.1, 0.3, 0.9), "back_parts_envelope": (0.6, 0.6, 0.6),
          "speaker_plug_zone": (0.9, 0.3, 0.3), "usb_c": (0.75, 0.75, 0.75), "rgb_led": (1.0, 1.0, 1.0)}


def main():
    parts = board_parts()
    asm = cq.Assembly(name="ESP32-2432S032C")
    for name, solid in parts.items():
        asm.add(solid, name=name, color=cq.Color(*COLORS[name]))
    out = os.path.join(HERE, "ESP32-2432S032C.step")
    asm.export(out)
    for name, solid in parts.items():
        b = solid.BoundingBox()
        print("%-20s %6.1f x %5.1f x %4.2f  z %5.2f..%5.2f  valid=%s" % (
            name, b.xlen, b.ylen, b.zlen, b.zmin, b.zmax, solid.isValid()))
    print("wrote", out)


if __name__ == "__main__":
    main()
