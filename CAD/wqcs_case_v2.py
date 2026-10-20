"""WQCS enclosure v2 + display cover for the ESP32-2432S032C (3.2" CYD).

Rebuilds from the Fusion export WQCS_Enclosure_v1.step (no feature history):
  1. Enclosure v2: the mechanical (main body) section, y -190..-20, grows LIFT
     mm taller (user request 2026-10-19). It's split at SPLIT_Z inside a plain
     band of wall (z -0.5..6.0: constant cross-section, above the internal
     component holder, below the side cable glands), the top part is raised
     LIFT, and the gap is filled with that same profile. Walls, cross wall and
     corner posts get longer; glands, rim and lid snap-fit move up together, so
     the v1 lid still fits. The front (display / main-PCB) section is untouched.
  1b. Second TDS board mount (2026-10-19): the display section's left inner
     wall carries the EK2169 TDS board on two vertical rails (3.5 wide x 3 mm,
     dia 1.5 pilots on a 25 x 35 mm pattern). Both TDS boards must sit there, away from the
     water valves in case of a leak, so the rails are copied TDS2_DY along
     the wall for the second board.
  2. Display cover (BUILD_COVER, off until the display section is decided): a
     flush inset plate for the front section's top opening (replaces the old
     PyPortal cover), sitting on the four corner pads, with a window over the
     display's active area and M3 standoffs underneath that hold the CYD
     face-up just below the plate.

All sizes are parameters below -- edit and rerun:
  ~/venvs/cad/bin/python CAD/wqcs_case_v2.py
Outputs (next to this script): WQCS_Enclosure_v2.step; with BUILD_COVER also
WQCS_Display_Cover_v1.step and WQCS_v2_fit_check.step (enclosure + cover + a CYD
stand-in block, for review only).

Coordinates are the Fusion export's: x across, y along the box (front section
y -20..66), z up with the display facing up (+z).
"""
import os

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- enclosure v2 ----------------------------------------------------------
SRC = os.path.join(HERE, "WQCS_Enclosure_v1.step")
LIFT_Y0, LIFT_Y1 = -200.0, -20.0   # main body; the front section starts at y -20
SPLIT_Z = 5.5        # band [SPLIT_Z - LIFT, SPLIT_Z] lies in the plain wall band z -0.5..6.0
LIFT = 4.0           # +4 mm, lying horizontally with the display facing up
BUILD_COVER = False

# ---- second TDS board (EK2169, 42 x 32 mm, holes 35 x 25) -------------------
ADD_TDS2 = True
# two vertical rails (3.5 wide x 3 deep, floor to z 0.75), dia 1.5 pilot near each end
TDS_BOSS_REGION = ((-75.45, -72.40), (-8.0, 22.5), (-41.45, 1.5))   # x, y, z ranges
TDS1_HOLES_Y = (-5.5, 19.5)
TDS_HOLES_Z = (-36.0, -1.0)
TDS_BOARD = (42.0, 32.0)    # tall (z) x wide (y)
TDS2_DY = 34.0              # board 2 at y 25..57: ~2 mm to board 1 and to the corner post (y 58.8)

# ---- front-section opening (measured from v1) -------------------------------
OPEN_X0, OPEN_X1 = -75.5, 34.5     # 110 mm
OPEN_Y0, OPEN_Y1 = -16.0, 64.0     # 80 mm
OPEN_CORNER_R = 2.0
RIM_Z_V1 = 6.5                     # front rim top (unchanged in v2); corner pads 2.5 mm below it
PAD_DEPTH = 2.5
COVER_PILOTS = [(-72.7, -13.2), (-72.7, 61.2), (31.8, -13.2), (31.8, 61.2)]  # dia 2.0 pilots in the pads

# ---- display cover ---------------------------------------------------------
CLEARANCE = 0.2            # per side, plate to opening
COVER_T = PAD_DEPTH        # flush with the rim
SCREW_CLEAR_D = 2.9        # M2.5 self-tapper into the 2.0 pilots
SCREW_HEAD_D = 5.0         # countersink top diameter (90 deg)

# ESP32-2432S032 (Mischianti / Sunton drawing). ** verify with calipers **
CYD_W, CYD_H = 93.7, 55.0          # PCB
CYD_HOLES_W, CYD_HOLES_H = 86.7, 48.0
CYD_PCB_T = 1.6
CYD_FACE_ABOVE_PCB = 4.0   # ** measure **: PCB top surface to glass front
CYD_BACK_DEPTH = 6.0       # ** measure **: PCB bottom to tallest part on the back
ACTIVE_W, ACTIVE_H = 64.8, 48.6
ACTIVE_DX = 2.6            # active-area centre right of PCB centre (toward the RGB LED end)
ACTIVE_DY = 0.0
WINDOW_MARGIN = 0.5        # window larger than the active area, per side
WINDOW_CHAMFER = 0.8       # top-edge bevel
CYD_CX, CYD_CY = None, None  # board centre in plate coords; None = centred in the opening
STANDOFF_D = 6.0
STANDOFF_PILOT_D = 2.5     # M3 self-tapper (use 4.0 for an M3 heat-set insert)


def lift_front_section(src):
    s = cq.importers.importStep(src).val()
    big = 400.0

    def box(y0, y1, z0, z1):
        return cq.Solid.makeBox(big, y1 - y0, z1 - z0, cq.Vector(-big / 2, y0, z0))

    upper = s.intersect(box(LIFT_Y0, LIFT_Y1, SPLIT_Z, 200))
    band = s.intersect(box(LIFT_Y0, LIFT_Y1, SPLIT_Z - LIFT, SPLIT_Z))
    rest = s.cut(box(LIFT_Y0, LIFT_Y1, SPLIT_Z, 200))
    out = rest.fuse(band.translate(cq.Vector(0, 0, LIFT))).fuse(upper.translate(cq.Vector(0, 0, LIFT)))
    out = out.clean().fix()   # boolean seams can leave tolerance flags; fix() clears them
    return s, out, band


def add_tds2(enclosure):
    (x0, x1), (y0, y1), (z0, z1) = TDS_BOSS_REGION
    bosses = enclosure.intersect(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))
    n = len(bosses.Solids())
    if n != 2:
        raise RuntimeError("expected the 2 TDS rails in TDS_BOSS_REGION, found %d solids" % n)
    return enclosure.fuse(bosses.translate(cq.Vector(0, TDS2_DY, 0))).clean().fix()


def tds_standins():
    """42 x 32 x 1.6 boards on the bosses (review only), plus a 10 mm component zone."""
    out = []
    cz = sum(TDS_HOLES_Z) / 2
    for dy in (0.0, TDS2_DY):
        cy = sum(TDS1_HOLES_Y) / 2 + dy
        out.append(cq.Solid.makeBox(1.6 + 10.0, TDS_BOARD[1], TDS_BOARD[0],
                                    cq.Vector(-72.45, cy - TDS_BOARD[1] / 2, cz - TDS_BOARD[0] / 2)))
    return out


def display_cover():
    w = (OPEN_X1 - OPEN_X0) - 2 * CLEARANCE
    h = (OPEN_Y1 - OPEN_Y0) - 2 * CLEARANCE
    cx, cy = (OPEN_X0 + OPEN_X1) / 2, (OPEN_Y0 + OPEN_Y1) / 2
    bx = cx if CYD_CX is None else CYD_CX
    by = cy if CYD_CY is None else CYD_CY
    top = RIM_Z_V1
    plate = (cq.Workplane("XY").workplane(offset=top - COVER_T)
             .center(cx, cy).rect(w, h).extrude(COVER_T)
             .edges("|Z").fillet(OPEN_CORNER_R))
    # countersunk screw holes over the corner pads
    plate = (plate.faces(">Z").workplane(centerOption="ProjectedOrigin", origin=(0, 0, top))
             .pushPoints(COVER_PILOTS).cskHole(SCREW_CLEAR_D, SCREW_HEAD_D, 90))
    # window over the active area
    ww, wh = ACTIVE_W + 2 * WINDOW_MARGIN, ACTIVE_H + 2 * WINDOW_MARGIN
    window = (cq.Workplane("XY").workplane(offset=top - COVER_T - 1)
              .center(bx + ACTIVE_DX, by + ACTIVE_DY).rect(ww, wh).extrude(COVER_T + 2))
    plate = plate.cut(window)
    if WINDOW_CHAMFER:
        plate = plate.faces(">Z").edges(cq.selectors.BoxSelector(
            (bx + ACTIVE_DX - ww / 2 - 0.1, by - wh / 2 - 0.1, top - 0.1),
            (bx + ACTIVE_DX + ww / 2 + 0.1, by + wh / 2 + 0.1, top + 0.1))).chamfer(WINDOW_CHAMFER)
    # standoffs down to the CYD PCB's top surface (the glass then touches the plate)
    standoff_len = CYD_FACE_ABOVE_PCB
    pts = [(bx + sx * CYD_HOLES_W / 2, by + sy * CYD_HOLES_H / 2) for sx in (-1, 1) for sy in (-1, 1)]
    posts = (cq.Workplane("XY").workplane(offset=top - COVER_T - standoff_len)
             .pushPoints(pts).circle(STANDOFF_D / 2).circle(STANDOFF_PILOT_D / 2)
             .extrude(standoff_len))
    plate = plate.union(posts)
    # stand-in for the CYD (review only): PCB + display module + back parts
    pcb_top = top - COVER_T - standoff_len
    cyd = (cq.Workplane("XY").workplane(offset=pcb_top - CYD_PCB_T - CYD_BACK_DEPTH)
           .center(bx, by).rect(CYD_W, CYD_H).extrude(CYD_PCB_T + CYD_BACK_DEPTH)
           .union(cq.Workplane("XY").workplane(offset=pcb_top).center(bx + ACTIVE_DX - 3.0, by)
                  .rect(77.0, 54.0).extrude(CYD_FACE_ABOVE_PCB - 0.05)))
    return plate, cyd, pcb_top - CYD_PCB_T - CYD_BACK_DEPTH


def main():
    v1, v2, band = lift_front_section(SRC)
    dv = v2.Volume() - v1.Volume()
    print("enclosure v1 %.1f cm^3 -> v2 %.1f cm^3 (+%.2f, band %.2f)  valid=%s solids=%d" % (
        v1.Volume() / 1000, v2.Volume() / 1000, dv / 1000, band.Volume() / 1000,
        v2.isValid(), len(v2.Solids())))
    bb = v2.BoundingBox()
    print("enclosure v2 bbox: %.1f x %.1f x %.1f mm (z %.2f..%.2f)" % (
        bb.xlen, bb.ylen, bb.zlen, bb.zmin, bb.zmax))
    if ADD_TDS2:
        before = v2.Volume()
        v2 = add_tds2(v2)
        print("added TDS-2 bosses (+%.1f mm^3), valid=%s" % (v2.Volume() - before, v2.isValid()))
        boards = tds_standins()
        for i, b in enumerate(boards):
            print("  TDS board %d stand-in: overlap with enclosure %.2f mm^3, y %.1f..%.1f" % (
                i + 1, b.intersect(v2).Volume(), b.BoundingBox().ymin, b.BoundingBox().ymax))
        print("  boards overlap each other: %.2f mm^3" % boards[0].intersect(boards[1]).Volume())
        fit = cq.Assembly()
        fit.add(v2, name="enclosure_v2", color=cq.Color(0.6, 0.7, 0.9))
        for i, b in enumerate(boards):
            fit.add(b, name="tds%d_standin" % (i + 1), color=cq.Color(0.3, 0.6, 0.3))
        fit.export(os.path.join(HERE, "WQCS_v2_tds_fit_check.step"))
    cq.exporters.export(cq.Workplane().add(v2), os.path.join(HERE, "WQCS_Enclosure_v2.step"))
    print("wrote WQCS_Enclosure_v2.step")
    if not BUILD_COVER:
        return

    cover, cyd, cyd_bottom = display_cover()
    print("cover valid=%s, volume %.1f cm^3" % (cover.val().isValid(), cover.val().Volume() / 1000))
    board_top_z = -35.5 + 1.6   # main PCB on the 6 mm floor standoffs (z -35.5), 1.6 mm thick
    print("CYD lowest point z %.1f; main PCB top z %.1f -> %.1f mm left for main-board parts" % (
        cyd_bottom, board_top_z, cyd_bottom - board_top_z))

    cq.exporters.export(cover, os.path.join(HERE, "WQCS_Display_Cover_v1.step"))
    asm = cq.Assembly()
    asm.add(v2, name="enclosure_v2", color=cq.Color(0.6, 0.7, 0.9))
    asm.add(cover, name="display_cover", color=cq.Color(0.95, 0.7, 0.4))
    asm.add(cyd, name="cyd_standin", color=cq.Color(0.3, 0.6, 0.3))
    asm.save(os.path.join(HERE, "WQCS_v2_fit_check.step"))
    print("wrote WQCS_Display_Cover_v1.step, WQCS_v2_fit_check.step")


if __name__ == "__main__":
    main()
