"""Display bezel v2: the existing PyPortal display case, refitted for the
ESP32-2432S032C (3.2" CYD).

Inputs (Fusion exports): WQCS_Display_Case_v1.step (open ring 71 x 99 x 11 mm
with a flange that seats on the display section's cover pads) and
Display_Cover.step (front bezel with a locating lip that drops into the ring).

Ring v2 (2026-10-22): the PyPortal's reset-switch housing (8.5 x 8.5 x 4.5 mm
block on the inner left wall) is cut away and its 6 x 6 mm wall hole filled
flush; neither is needed for the CYD. The four corner screw bosses (bezel
screws) are trimmed on their inner face, behind the board's depth only, to
BOSS_CLEARANCE from the CYD board's long edges: with the measured 4.9 mm
stack the board sits deep enough to catch them. Otherwise the ring is unchanged: its
cavity is 68.2 x 96.3 mm, and the CYD board
(93.7 x 55, long axis along the ring's long axis) clears it by ~1.3 mm at
the ends and the old PyPortal corner posts by ~0.7 mm. The bezel changes:
  - window: same size (both are 3.2" 320x240 panels: 48.6 x 64.8 active),
    moved CYD_ACTIVE_DZ along the long axis to the CYD's off-centre active
    area (the old opening is filled and the new one cut);
  - four standoffs on the bezel's back, on the CYD's 86.7 x 48 hole pattern,
    CYD_STACK long so the glass sits against the bezel's back (the old
    PyPortal sat the same 4 mm behind it). M3 screws from the CYD's back.

Outputs: Display_Cover_v2.step, WQCS_Display_Case_v2.step; Display_v2_fit_check.step (ring + bezel +
the CYD model from cyd_model.py, review only, gitignored). Clash volumes are printed per CYD part.

Run:  ~/venvs/cad/bin/python CAD/wqcs_display_v2.py
Bezel coordinates: x across the short side, z along the long side, y through
the bezel (front face y -2.5, back face y -1.0, lip to y 2.0; +y = into the box).
"""
import os

import cadquery as cq

import cyd_model

HERE = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(HERE, "WQCS_Display_Case_v1.step")
BEZEL = os.path.join(HERE, "Display_Cover.step")

# bezel -> case placement, from the four shared dia-8 corner holes
# (bezel (-31.791, 0.760) == case (0.095, 0.242)); bezel back face on the ring rim
BEZEL_TO_CASE = (31.886, 22.27 + 1.0, -0.518)   # dx, dy, dz
BEZEL_FRONT_Y, BEZEL_BACK_Y = -2.5, -1.0

# ESP32-2432S032C (Sunton drawing). ** verify with calipers **
CYD_W, CYD_L = 55.0, 93.7          # board: short side along x, long side along z
CYD_HOLES = (48.0, 86.7)           # x, z
CYD_PCB_T = 1.6
CYD_STACK = 4.3                    # 4.9 (caliper) left a 0.5-0.7 mm gap at the glass on the
                                   # test print (2026-10-24), so the real stack is ~4.3
CYD_BACK_DEPTH = 7.0               # measured: back connectors 5 mm, 7 mm with the speaker plugged in
CYD_GLASS = (54.6, 77.3)           # x, z: edges 4.7 mm inside the hole centres (drawing)
ACTIVE = (48.6, 64.8)              # x, z
# The user's board, seen from the front, is the drawing rotated 180 deg: RGB LED at
# bottom-left, USB-C centred on the right edge. The active area is offset toward the
# LED end (drawing: 17.1 mm from the FPC end, 11.6 from the LED end), i.e. away from
# the USB. The USB end goes to the ring's z+ end (USB_NOTCH), so the offset is -z.
CYD_ACTIVE_DZ = -2.6               # active-area centre from board centre along z
WINDOW_MARGIN = 0.3                # per side, as on the v1 bezel (49.2 x 65.4 window)
# board centre in bezel coordinates = ring cavity centre (case x 31.7, z 45.85)
# shifted CYD_DZ toward the bottom end: the ring's top end has the old PyPortal USB
# notch's internal tabs at case z 92.5..93.0, which the board's end edge would touch
CYD_DZ = -0.6
CYD_CX, CYD_CZ = 31.7 - BEZEL_TO_CASE[0], 45.85 - BEZEL_TO_CASE[2] + CYD_DZ

OLD_WINDOW = (-24.6, 24.6, 13.7, 79.1)   # x0, x1, z0, z1 (measured)
# The v1 window has a 1 mm x 45 deg chamfer on its front edge (front-face opening
# x -25.3..25.3, z 12.99..79.79) and r1 back corners. The fill must cover the whole
# chamfered opening: filling only the back opening left a V-gap at the front, and
# the strip printed detached (2026-10-24).
OLD_WINDOW_FRONT = (-25.3, 25.3, 12.99, 79.79)
WINDOW_CHAMFER, WINDOW_CORNER_R = 1.0, 1.0   # match v1
# USB-C access through the ring's z+ end wall (case coordinates), centred on the
# board's short axis, from just behind the bezel lip to the flange
USB_NOTCH = dict(cx=31.7, w=14.0, y0=25.3, y1=33.27, z0=92.4, z1=96.0)
# USB-C receptacle centre 1.6 mm behind the PCB's back face (measured). A standard
# plug (12.4 x 6.5 overmold) then reaches 0.35 mm past the flange's outer face, so
# the flange gets a matching relief from the ring wall out to its edge.
USB_CENTRE_BEHIND_PCB = 1.6
USB_PLUG = (12.4, 6.5)               # overmold width, height
FLANGE_USB_RELIEF = dict(y0=33.2, y1=34.1, z0=92.4, z1=99.6)   # case coords; x as USB_NOTCH
# ring (case) -> enclosure: flange holes (74.5 x 104.5, centre case x 31.89 z 44.48) sit on the
# enclosure's cover pads (centre x -20.45 y 24.0), flange back (case y 35.26) on the pads (z 14)
def case_to_enclosure(xc, yc, zc):
    return zc - 64.93, 55.89 - xc, 49.26 - yc
STANDOFF_D, STANDOFF_PILOT_D = 6.0, 2.5  # M3 self-tapper


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


# PyPortal reset-switch housing (case coordinates): block on the inner face of
# the left wall, and the switch opening through the wall (x -3.91..-2.41)
SWITCH_BLOCK = (-2.42, 2.12, 25.70, 34.30, 43.95, 52.55)   # x0, x1, y0, y1, z0, z1
SWITCH_HOLE_FILL = (-3.91, -2.41, 26.20, 31.85, 45.20, 51.30)
# corner boss trims (case coordinates): bosses reach x 4.6 / 58.8 (top) and
# 4.1 / 59.3 (bottom); the CYD's long edges are at x 31.7 -/+ 27.5
BOSS_CLEARANCE = 0.5
BOSS_TRIM_Y = (28.0, 33.27)          # behind the board's front; the flange (y >= 33.27) is untouched
BOSS_TRIM_Z = ((-2.5, 10.5), (85.3, 94.2))


def ring_v2():
    ring = cq.importers.importStep(CASE).val()
    block = box(*SWITCH_BLOCK)
    removed = ring.intersect(block).Volume()
    ring = ring.cut(block)
    before = ring.Volume()
    ring = ring.fuse(box(*SWITCH_HOLE_FILL))
    filled = ring.Volume() - before
    n = USB_NOTCH
    ring = ring.cut(box(n["cx"] - n["w"] / 2, n["cx"] + n["w"] / 2, n["y0"], n["y1"], n["z0"], n["z1"]))
    f = FLANGE_USB_RELIEF
    ring = ring.cut(box(n["cx"] - n["w"] / 2, n["cx"] + n["w"] / 2, f["y0"], f["y1"], f["z0"], f["z1"]))
    edge_l, edge_r = 31.7 - CYD_W / 2 - BOSS_CLEARANCE, 31.7 + CYD_W / 2 + BOSS_CLEARANCE
    for z0, z1 in BOSS_TRIM_Z:
        ring = ring.cut(box(edge_l, edge_l + 1.5, *BOSS_TRIM_Y, z0, z1))
        ring = ring.cut(box(edge_r - 1.5, edge_r, *BOSS_TRIM_Y, z0, z1))
    return ring.clean().fix(), removed, filled


def _rrect_wire(cx, cz, w, l, r, y):
    """Rounded rectangle in the plane y = const (XZ plane: local x = X, local y = Z)."""
    wire = cq.Workplane("XZ", origin=(0, y, 0)).center(cx, cz).rect(w, l).val()
    return wire.fillet2D(r, wire.Vertices())


def window_cutter(cx, cz, w, l):
    """Straight r1 opening at the back plus a 45 deg front chamfer, like the v1 window."""
    yc = BEZEL_FRONT_Y + WINDOW_CHAMFER          # where the chamfer meets the straight wall
    straight = cq.Solid.makeLoft([_rrect_wire(cx, cz, w, l, WINDOW_CORNER_R, yc - 0.01),
                                  _rrect_wire(cx, cz, w, l, WINDOW_CORNER_R, BEZEL_BACK_Y + 0.3)])
    c = WINDOW_CHAMFER
    chamfer = cq.Solid.makeLoft([_rrect_wire(cx, cz, w + 2 * c + 0.02, l + 2 * c + 0.02,
                                             WINDOW_CORNER_R + c, BEZEL_FRONT_Y - 0.01),
                                 _rrect_wire(cx, cz, w, l, WINDOW_CORNER_R, yc)])
    return straight.fuse(chamfer)


def bezel_v2():
    bez = cq.importers.importStep(BEZEL).val()
    x0, x1, z0, z1 = OLD_WINDOW_FRONT
    bez = bez.fuse(box(x0 - 0.3, x1 + 0.3, BEZEL_FRONT_Y, BEZEL_BACK_Y, z0 - 0.3, z1 + 0.3))
    ww, wl = ACTIVE[0] + 2 * WINDOW_MARGIN, ACTIVE[1] + 2 * WINDOW_MARGIN
    acx, acz = CYD_CX, CYD_CZ + CYD_ACTIVE_DZ
    bez = bez.cut(window_cutter(acx, acz, ww, wl))
    for sx in (-1, 1):
        for sz in (-1, 1):
            hx, hz = CYD_CX + sx * CYD_HOLES[0] / 2, CYD_CZ + sz * CYD_HOLES[1] / 2
            post = cq.Solid.makeCylinder(STANDOFF_D / 2, CYD_STACK, cq.Vector(hx, BEZEL_BACK_Y, hz),
                                         cq.Vector(0, 1, 0))
            pilot = cq.Solid.makeCylinder(STANDOFF_PILOT_D / 2, CYD_STACK + 0.01,
                                          cq.Vector(hx, BEZEL_BACK_Y, hz), cq.Vector(0, 1, 0))
            bez = bez.fuse(post).cut(pilot)
    return bez.clean().fix(), (acx, acz, ww, wl)


def cyd_standin():
    """PCB + back parts, and the glass block in front (bezel coordinates)."""
    pcb_front = BEZEL_BACK_Y + CYD_STACK
    pcb = box(CYD_CX - CYD_W / 2, CYD_CX + CYD_W / 2, pcb_front, pcb_front + CYD_PCB_T + CYD_BACK_DEPTH,
              CYD_CZ - CYD_L / 2, CYD_CZ + CYD_L / 2)
    gx, gz = CYD_GLASS   # the glass is centred on the board; only the active area inside it is offset
    glass = box(CYD_CX - gx / 2, CYD_CX + gx / 2, BEZEL_BACK_Y + 0.01, pcb_front,
                CYD_CZ - gz / 2, CYD_CZ + gz / 2)
    return pcb, glass


def usb_plug_case():
    """USB-C plug overmold stand-in (case coordinates), from the receptacle mouth outward."""
    dx, dy, dz = BEZEL_TO_CASE
    pcb_back_y = BEZEL_BACK_Y + CYD_STACK + CYD_PCB_T + dy          # case y
    cy = pcb_back_y + USB_CENTRE_BEHIND_PCB
    mouth_z = CYD_CZ + dz + cyd_model.PCB_W / 2 + cyd_model.USB_C[3]
    w, h = USB_PLUG
    return box(USB_NOTCH["cx"] - w / 2, USB_NOTCH["cx"] + w / 2, cy - h / 2, cy + h / 2, mouth_z, mouth_z + 30)


def cyd_in_bezel():
    """cyd_model parts placed in bezel coordinates: model +X (USB-C) -> +z (ring's
    notch end), model +Z (out of the screen) -> -y (toward the bezel front), and
    the glass front on the bezel's back face."""
    t = (CYD_CX, BEZEL_BACK_Y + CYD_STACK + CYD_PCB_T, CYD_CZ)
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf
    trsf = gp_Trsf()   # rows: x_b = -Y + tx, y_b = -Z + ty, z_b = X + tz (a proper rotation, det +1)
    trsf.SetValues(0, -1, 0, t[0], 0, 0, -1, t[1], 1, 0, 0, t[2])
    return {name: cq.Shape.cast(BRepBuilderAPI_Transform(solid.wrapped, trsf, True).Shape())
            for name, solid in cyd_model.board_parts().items()}


def main():
    bez, (acx, acz, ww, wl) = bezel_v2()
    print("bezel v2 valid=%s; window %.1f x %.1f centred x %.2f z %.2f (old centre z %.2f)" % (
        bez.isValid(), ww, wl, acx, acz, (OLD_WINDOW[2] + OLD_WINDOW[3]) / 2))
    cq.exporters.export(cq.Workplane().add(bez), os.path.join(HERE, "Display_Cover_v2.step"))

    ring, removed, filled = ring_v2()
    print("ring v2 valid=%s: switch housing removed (%.1f mm^3), wall hole filled (+%.1f mm^3), "
          "USB-C notch %.0f mm wide at the z+ end" % (ring.isValid(), removed, filled, USB_NOTCH["w"]))
    cq.exporters.export(cq.Workplane().add(ring), os.path.join(HERE, "WQCS_Display_Case_v2.step"))
    dx, dy, dz = BEZEL_TO_CASE
    case_in_bezel = ring.translate(cq.Vector(-dx, -dy, -dz))
    cyd = cyd_in_bezel()
    a = cyd["active_area"].BoundingBox()
    print("CYD model active area centre x %.2f z %.2f vs window centre x %.2f z %.2f; glass front y %.2f (bezel back %.2f)" % (
        a.center.x, a.center.z, acx, acz, cyd["glass"].BoundingBox().ymin, BEZEL_BACK_Y))
    print("fit (mm^3 of overlap) per CYD part:")
    for name, solid in cyd.items():
        print("  %-20s vs ring %6.2f, vs bezel %6.2f" % (
            name, solid.intersect(case_in_bezel).Volume(), solid.intersect(bez).Volume()))
    print("  bezel vs ring %.2f (the original pair has the same 0.47: lip fit)" % bez.intersect(case_in_bezel).Volume())
    plug = usb_plug_case()
    pb = plug.BoundingBox()
    e0 = case_to_enclosure(pb.xmax, pb.ymax, pb.zmin)
    e1 = case_to_enclosure(pb.xmin, pb.ymin, pb.zmax)
    print("  USB-C plug vs ring %.2f; plug in enclosure coords x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f" % (
        plug.intersect(ring).Volume(), e0[0], e1[0], e0[1], e1[1], e0[2], e1[2]))
    asm = cq.Assembly()
    asm.add(case_in_bezel, name="ring_v2", color=cq.Color(0.6, 0.7, 0.9))
    asm.add(bez, name="bezel_v2", color=cq.Color(0.95, 0.7, 0.4))
    for name, solid in cyd.items():
        asm.add(solid, name="cyd_" + name, color=cq.Color(*cyd_model.COLORS[name]))
    asm.export(os.path.join(HERE, "Display_v2_fit_check.step"))
    print("wrote Display_Cover_v2.step, WQCS_Display_Case_v2.step, Display_v2_fit_check.step")


if __name__ == "__main__":
    main()
