"""WQCS enclosure v2 + display cover for the ESP32-2432S032C (3.2" CYD).

Rebuilds from the Fusion export WQCS_Enclosure_v1.step (no feature history):
  1. Enclosure v2: the mechanical (main body) section, y -190..-20, grows LIFT
     mm taller (user request 2026-10-19). It's split at SPLIT_Z inside a plain
     band of wall (z -0.5..6.0: constant cross-section, above the internal
     component holder, below the side cable glands), the top part is raised
     LIFT, and the gap is filled with that same profile. Walls, cross wall and
     corner posts get longer; glands, rim and lid snap-fit move up together, so
     the v1 lid still fits. The front (display / main-PCB) section is untouched.
  1b. Second TDS board mount (2026-10-21): both EK2169 TDS boards must sit in
     the display section, away from the water valves in case of a leak. TDS-1
     stays on its existing rails on the left inner wall (3.5 wide x 3 mm, dia
     1.5 pilots, 25 x 35 mm pattern). The photos show no room there for a
     second (MOSFETs, screw terminals and wiring), so TDS-2 gets matching
     rails on the bottom wall (inner face y -16, shared with the mechanical
     section). It lies along the wall (42 mm in x, 32 mm in z), above the main
     PCB's bottom-edge parts (<= 3.8 mm), clear of the harness slot in that
     wall's lower-left corner.
  1c. Fit check (review only): enclosure + the real main PCB (wqcs_pcb.step,
     placed on its floor standoffs as installed) + TDS stand-in boards, with
     clash volumes printed.
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

# ---- TDS boards (EK2169, 42 x 32 x 1.6 mm, holes 35 x 25, M2 into dia 1.5 pilots)
ADD_TDS2 = True
TDS_RAIL_W, TDS_RAIL_D, TDS_PILOT_D = 3.5, 3.0, 1.5   # as on the existing TDS-1 rails
TDS_HOLES = (35.0, 25.0)
TDS_BOARD = (42.0, 32.0)
TDS_PART_H = 6.0           # ** measure **: tallest part on the TDS board's front
TDS1_HOLES_Y, TDS1_HOLES_Z = (-5.5, 19.5), (-36.0, -1.0)   # existing, left wall x -75.5
BOTTOM_WALL_Y = -16.0      # inner face of the wall shared with the mechanical section
TDS2_CX = -24.0            # board x -45..-3: clear of the harness slot (x -70.5..-63.5)
TDS2_CZ = -12.5            # board z -28.5..3.5: above the PCB's edge parts, below the cover pads (z 4)

# ---- main PCB (CAD/wqcs_pcb.step), as installed (photo IMG_6380) -------------
PCB_STEP = os.path.join(HERE, "wqcs_pcb.step")
PCB_HOLE_TO_STANDOFF = ((3.17, -20.98), (-61.7, -7.8))   # model hole -> enclosure standoff, no rotation
PCB_STANDOFF_TOP = -35.5
PCB_T = 1.6                # the model's board body is only 0.34 mm; real boards are 1.6
PCB_MODEL_TOP = 0.33       # model z where parts start

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


def lift_main_body(src):
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
    """Two vertical rails on the bottom wall, one under each pair of holes."""
    hz = (TDS2_CZ - TDS_HOLES[1] / 2, TDS2_CZ + TDS_HOLES[1] / 2)
    z0, z1 = hz[0] - TDS_RAIL_W / 2 - 1.0, hz[1] + TDS_RAIL_W / 2 + 1.0
    out = enclosure
    for hx in (TDS2_CX - TDS_HOLES[0] / 2, TDS2_CX + TDS_HOLES[0] / 2):
        rail = cq.Solid.makeBox(TDS_RAIL_W, TDS_RAIL_D, z1 - z0,
                                cq.Vector(hx - TDS_RAIL_W / 2, BOTTOM_WALL_Y, z0))
        for z in hz:
            rail = rail.cut(cq.Solid.makeCylinder(TDS_PILOT_D / 2, TDS_RAIL_D + 0.2,
                                                  cq.Vector(hx, BOTTOM_WALL_Y - 0.1, z), cq.Vector(0, 1, 0)))
        out = out.fuse(rail)
    return out.clean().fix()


def tds_standins():
    """Each board (1.6 mm) plus its TDS_PART_H part zone, on its rails (review only)."""
    w, h = TDS_BOARD
    depth = 1.6 + TDS_PART_H
    x_face = -75.5 + TDS_RAIL_D     # TDS-1 back face on its rails
    y1c, z1c = sum(TDS1_HOLES_Y) / 2, sum(TDS1_HOLES_Z) / 2
    tds1 = cq.Solid.makeBox(depth, h, w, cq.Vector(x_face, y1c - h / 2, z1c - w / 2))
    y_face = BOTTOM_WALL_Y + TDS_RAIL_D
    tds2 = cq.Solid.makeBox(w, depth, h, cq.Vector(TDS2_CX - w / 2, y_face, TDS2_CZ - h / 2))
    return [tds1, tds2]


def main_pcb():
    """The installed main PCB: model hole -> enclosure standoff, parts lifted for a 1.6 mm board."""
    (hx, hy), (sx, sy) = PCB_HOLE_TO_STANDOFF
    dz = PCB_STANDOFF_TOP + PCB_T - PCB_MODEL_TOP
    sols = cq.importers.importStep(PCB_STEP).solids().vals()
    parts = [p.translate(cq.Vector(sx - hx, sy - hy, dz)) for p in sols if p.BoundingBox().xlen < 80]
    bb = sols[0].BoundingBox()
    board = cq.Solid.makeBox(bb.xlen, bb.ylen, PCB_T,
                             cq.Vector(bb.xmin + sx - hx, bb.ymin + sy - hy, PCB_STANDOFF_TOP))
    return board, cq.Compound.makeCompound(parts)


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
    v1, v2, band = lift_main_body(SRC)
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
        print("added TDS-2 rails on the bottom wall (+%.1f mm^3), valid=%s" % (v2.Volume() - before, v2.isValid()))
    boards = tds_standins()
    board, parts = main_pcb()
    print("fit check (mm^3 of overlap; TDS boxes include a %.0f mm part zone):" % TDS_PART_H)
    for i, b in enumerate(boards):
        print("  TDS-%d vs enclosure %.2f, vs main PCB parts %.2f, vs main PCB board %.2f" % (
            i + 1, b.intersect(v2).Volume(), b.intersect(parts).Volume(), b.intersect(board).Volume()))
    print("  main PCB parts vs enclosure %.2f, board vs enclosure %.2f" % (
        parts.intersect(v2).Volume(), board.intersect(v2).Volume()))
    fit = cq.Assembly()
    fit.add(v2, name="enclosure_v2", color=cq.Color(0.6, 0.7, 0.9))
    fit.add(board, name="main_pcb", color=cq.Color(0.8, 0.2, 0.2))
    fit.add(parts, name="main_pcb_parts", color=cq.Color(0.2, 0.2, 0.2))
    for i, b in enumerate(boards):
        fit.add(b, name="tds%d_standin" % (i + 1), color=cq.Color(0.3, 0.6, 0.3))
    fit.export(os.path.join(HERE, "WQCS_v2_fit_check.step"))
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
    asm.export(os.path.join(HERE, "WQCS_v2_cover_fit_check.step"))
    print("wrote WQCS_Display_Cover_v1.step, WQCS_v2_cover_fit_check.step")


if __name__ == "__main__":
    main()
