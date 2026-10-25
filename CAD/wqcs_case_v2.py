"""WQCS enclosure v2 + display cover for the ESP32-2432S032C (3.2" CYD).

Rebuilds from the Fusion export WQCS_Enclosure_v1.step (no feature history):
  1. Enclosure v2: the mechanical (main body) section, y -190..-20, grows LIFT
     mm taller (user request 2026-10-19). It's split at SPLIT_Z inside a plain
     band of wall (z -0.5..6.0: constant cross-section, above the internal
     component holder, below the side cable glands), the top part is raised
     LIFT, and the gap is filled with that same profile. Walls, cross wall and
     corner posts get longer; rim and lid snap-fit move up together, so the v1
     lid still fits. The dia-16 tube bulkhead holes are put back at their v1
     positions (user, 2026-10-25: the internal holders don't move, so
     the tube runs must line up). The front (display / main-PCB) section is untouched.
  1c. Outer walls 2 -> 4 mm (user, 2026-10-25: forcing the tubing into place
     flexed the 2 mm walls). Every outer side and end wall of both sections
     grows WALL_ADD outward, so nothing inside moves. Each opening through a
     straight wall is carried straight on through the new skin, so no hole
     moves either. The step face where the mechanical section rises above the
     display rim isn't an outer wall and stays 2 mm. The lid gets the same
     border: WQCS_Encl_lid_v2 = v1 + WALL_ADD on its three outer edges.
  1e. Bottom end and pressure switch (user, 2026-10-25). "Down" is -y, because
     the unit hangs with the display section on top. The bottom end (the end
     wall the refill solenoid screws to) drops BOTTOM_DROP: the mechanical
     section is stretched at BOTTOM_SPLIT_Y, inside a plain band of wall, and
     the lid gets the same stretch. The pressure-switch housing (the sleeve the
     pressure switch's lower body drops into) is rebuilt with PSW_WALL walls instead of
     1.0 mm, grown outward so the pocket is unchanged, and drops PSW_DROP into
     the room this makes. The bulkhead holes are above the split, so they stay put.
  1a. Display/PCB section +FRONT_LIFT (2026-10-21, user: 48 -> ~58 mm inside):
     same method, split at FRONT_SPLIT_Z inside that section's plain wall band
     (z -15..-2). Rim, cover pads and their pilots, and corner-post tops move
     up together. The old left-wall TDS-1 rails are removed before the lifts
     so they aren't stretched.
  1b. TDS board mounts (2026-10-21): both EK2169 TDS boards sit in the
     display section, away from the water valves in case of a leak. The left
     wall's original TDS-1 rails are removed (the MOSFETs, screw terminals
     and their wiring need that side). Each board lies along a wall (42 mm in
     x, 32 mm in z) on rails like the old ones (3.5 wide x 3 mm, dia 1.5
     pilots, 35 x 25 mm pattern):
       TDS-1 on the top wall (inner face y 64): the old wire bundle there is
         gone in the new setup.
       TDS-2 on the bottom wall (inner face y -16, shared with the mechanical
         section), clear of the harness slot in its lower-left corner.
     Both sit above the main PCB's edge parts (<= 3.8 mm within reach).
  1b2. Harness under the main PCB (2026-10-21): 5 cables dia 4 (2x TDS, 3x
     scales) + 8 wires 18-20 AWG (4 pairs: boiler sw, refill valve, main
     valve, transfer valve) = ~96 mm^2. The four floor standoffs grow
     PCB_RAISE (6 -> 10 mm), leaving ~8 mm under the board after ~2 mm of
     solder leads: the cables lie flat with the wires on top (~6.3 mm). A
     floor-level slot (HARNESS_SLOT, ~253 mm^2, < 40 % fill so plugs pull
     through) goes through the wall shared with the mechanical section,
     centred under the board. The old high slot on the left stays as a spare.
  1d. Speaker (2026-10-22, 20 x 5 mm): press-fit housing on the display
     section's upper left wall, above the main PCB: a short cylinder on the
     inner wall face, split into SPK_FINGERS flexible fingers, each with an
     inward lip (entry chamfered) that holds the speaker's back edge, and
     sound slits through the wall behind the cone.
  1e. Speaker test coupon: a 35 x 35 mm square of the left wall cut from the
     finished enclosure, with the housing and grille, to test the press fit
     without printing the whole box (Speaker_Test_Coupon.step / .stl; print it
     wall-down, cup up).
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
# dia-16 bulkhead holes above SPLIT_Z, kept at their v1 positions:
# (wall x0, x1, hole centre y, centre z in v1); plain 2 mm wall around both
BULKHEAD_D = 16.0
BULKHEADS = ((-80.511667, -78.511667, -117.0, 14.5), (37.488333, 39.488333, -145.0, 14.5))
WALL_ADD = 2.0       # outer walls 2 -> 4 mm, grown outward
WALL_PROBE = 0.3     # depth inside each outer face searched for openings
LID_SRC = os.path.join(HERE, "WQCS_Encl_lid_v1.step")
LID_PLATE_T = 3.0    # lid plate z 32.5..35.5 (v1 coordinates)
# internal holders (below SPLIT_Z except the shelf's right half, which the lift stretched)
BOTTOM_SPLIT_Y = -170.0    # band [split, split + BOTTOM_DROP] lies in a plain stretch (y -180..-156)
BOTTOM_DROP = 5.0
PSW_ZONE = (-45.6, 18.0, -126.0, -107.5, -41.5, -3.4)   # v1 housing, incl. its base fillets
PSW_POCKET = (-43.31, 15.69, -123.65, -109.85)           # x0, x1, y0, y1 (unchanged)
PSW_POCKET_R = 3.5         # pocket corners at the right end
PSW_TOP = -3.5
PSW_SLOT = (-119.19, -112.31, -30.6)                     # left end wall: y0, y1, from z up
PSW_WALL = 3.0             # v1: 1.0
PSW_DROP = 5.0
FRONT_Y0 = -20.0     # display/PCB section: y -20 and beyond
FRONT_SPLIT_Z = -3.0 # band [FRONT_SPLIT_Z - FRONT_LIFT, FRONT_SPLIT_Z] lies in its plain band z -15..-2
FRONT_LIFT = 10.0    # inside height 48 -> 58 mm
BUILD_COVER = False

# ---- TDS boards (EK2169, 42 x 32 x 1.6 mm, holes 35 x 25, M2 into dia 1.5 pilots)
TDS_RAIL_W, TDS_RAIL_D, TDS_PILOT_D = 3.5, 3.0, 1.5   # as on the original TDS-1 rails
TDS_HOLES = (35.0, 25.0)
TDS_BOARD = (42.0, 32.0)
TDS_PART_H = 6.0           # ** measure **: tallest part on the TDS board's front
# original TDS-1 rails on the left wall (removed): exactly 2 solids in this box
OLD_TDS1_RAILS = ((-75.5, -72.40), (-8.0, 22.5), (-41.45, 1.5))   # x, y, z ranges
# (name, wall inner face y, direction into the section, board centre x, centre z)
TDS_MOUNTS = (
    ("TDS-1", 64.0, -1, -24.0, -2.5),    # top wall, centred
    ("TDS-2", -16.0, +1, -24.0, -2.5),   # bottom wall, above the harness slot
)   # z -18.5..13.5: >= 7 mm above every main-PCB edge part, below the cover pads (z 14 after FRONT_LIFT)

# ---- speaker housing (left wall of the display section; wall x -77.5..-75.5) ----
SPK_WALL_X = -75.45        # inner face of the left wall (measured; not -75.5)
SPK_CY, SPK_CZ = 40.0, -3.0  # upper left, above the main PCB, below the display (z >= 13.5)
SPK_D, SPK_H = 20.0, 5.0     # measured speaker
SPK_FIT = 0.4                # ID = SPK_D + SPK_FIT (0.2 printed too tight, 2026-10-22)
SPK_WALL = 1.0               # finger thickness (1.2 too stiff)
SPK_EMBED = 0.3
SPK_LIP = 0.45               # inward lip at the open end (radial; 0.7 wouldn't pass)
SPK_LIP_T = 1.0              # lip thickness (along x); entry chamfer over 80 %
SPK_FINGERS, SPK_SLOT_W, SPK_SLOT_DEPTH = 6, 1.5, 5.5   # longer slits = more flexible fingers
SPK_GRILLE_R, SPK_GRILLE_W, SPK_GRILLE_PITCH = 8.0, 1.6, 3.2   # slits through the wall
COUPON = 35.0                # test coupon side (mm)

# ---- USB-C access for the display (2026-10-22) -------------------------------
# A standard USB-C plug into the CYD passes over the display section's right wall
# top (rim z 16.5) with its underside at z ~15.64 (wqcs_display_v2.py prints the
# plug position), so the rim gets a notch there.
USB_RIM_NOTCH = (34.3, 40.0, 24.2 - 7.2, 24.2 + 7.2, 15.0, 16.6)   # x0, x1, y0, y1, z0, z1
USB_PLUG_ENCL = (27.75, 60.0, 17.99, 30.39, 16.24, 22.74)          # from wqcs_display_v2.py (stack 4.3)
WALL_OUTER_X = -77.5 - WALL_ADD   # display section left wall outer face

# ---- main PCB (CAD/wqcs_pcb.step), as installed (photo IMG_6380) -------------
PCB_STEP = os.path.join(HERE, "wqcs_pcb.step")
PCB_HOLE_TO_STANDOFF = ((3.17, -20.98), (-61.7, -7.8))   # model hole -> enclosure standoff, no rotation
PCB_RAISE = 6.0           # standoffs 6 -> 12 mm: ~10 mm under the board for the harness
STANDOFFS = [(-61.7, -7.8), (-61.7, 55.8), (20.8, -7.8), (20.8, 55.8)]
STANDOFF_OD, STANDOFF_PILOT = 8.0, 2.8
PCB_STANDOFF_TOP = -35.5 + PCB_RAISE
# floor-level harness slot through the shared wall (y -22..-16), rounded ends
HARNESS_SLOT = dict(cx=-20.5, w=30.0, z0=-41.0, h=11.0, wall_y=(-22.5, -15.5))   # ~304 mm^2
PCB_T = 1.6                # the model's board body is only 0.34 mm; real boards are 1.6
PCB_MODEL_TOP = 0.33       # model z where parts start

# ---- front-section opening (measured from v1) -------------------------------
OPEN_X0, OPEN_X1 = -75.5, 34.5     # 110 mm
OPEN_Y0, OPEN_Y1 = -16.0, 64.0     # 80 mm
OPEN_CORNER_R = 2.0
RIM_Z_V1 = 6.5                     # front rim top in v1 (v2: + FRONT_LIFT); corner pads 2.5 mm below it
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


def lift_region(s, y0, y1, split_z, amount):
    """Raise everything in y0..y1 above split_z by amount, filling the gap with
    the wall profile just below the split (must be a plain, prismatic band)."""
    big = 400.0

    def box(ya, yb, za, zb):
        return cq.Solid.makeBox(big, yb - ya, zb - za, cq.Vector(-big / 2, ya, za))

    upper = s.intersect(box(y0, y1, split_z, 200))
    band = s.intersect(box(y0, y1, split_z - amount, split_z))
    rest = s.cut(box(y0, y1, split_z, 200))
    out = rest.fuse(band.translate(cq.Vector(0, 0, amount))).fuse(upper.translate(cq.Vector(0, 0, amount)))
    return out.clean().fix(), band   # fix(): boolean seams can leave tolerance flags


def restore_bulkheads(s):
    """Fill the lifted bulkhead holes (z + LIFT) and cut them again at the v1 z."""
    pad = 1.0
    for x0, x1, y, z in BULKHEADS:
        r = BULKHEAD_D / 2
        s = s.fuse(cq.Solid.makeBox(x1 - x0, BULKHEAD_D + 2 * pad, BULKHEAD_D + 2 * pad,
                                    cq.Vector(x0, y - r - pad, z + LIFT - r - pad)))
        s = s.cut(cq.Solid.makeCylinder(r, x1 - x0 + 2, cq.Vector(x0 - 1, y, z), cq.Vector(1, 0, 0)))
    return s.clean().fix()


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def stretch_bottom(s):
    """Move everything below BOTTOM_SPLIT_Y down BOTTOM_DROP and fill the gap with
    the plain cross-section just above the split."""
    big, y0, d = 400.0, BOTTOM_SPLIT_Y, BOTTOM_DROP
    lower = s.intersect(_box(-big, big, y0 - big, y0, -big, big))
    band = s.intersect(_box(-big, big, y0, y0 + d, -big, big))
    rest = s.cut(_box(-big, big, y0 - big, y0, -big, big))
    out = rest.fuse(band.translate(cq.Vector(0, -d, 0))).fuse(lower.translate(cq.Vector(0, -d, 0)))
    return out.clean().fix()


def pressure_switch_housing():
    """The pressure switch's sleeve: v1 pocket and left-end slot, PSW_WALL walls, sunk 0.1 into the floor."""
    x0, x1, y0, y1 = PSW_POCKET
    w, r, zf = PSW_WALL, PSW_POCKET_R, PSW_ZONE[4]
    outer = _box(x0 - w, x1 + w, y0 - w, y1 + w, zf - 0.1, PSW_TOP)
    pocket = _box(x0, x1 - r, y0, y1, zf, PSW_TOP + 1).fuse(_box(x1 - r, x1, y0 + r, y1 - r, zf, PSW_TOP + 1))
    for yc in (y0 + r, y1 - r):
        pocket = pocket.fuse(cq.Solid.makeCylinder(r, PSW_TOP + 1 - zf, cq.Vector(x1 - r, yc, zf)))
    sy0, sy1, sz = PSW_SLOT
    return outer.cut(pocket).cut(_box(x0 - w - 1, x0 + 0.1, sy0, sy1, sz, PSW_TOP + 1))


def _plane_faces(s, normal, at, axis):
    """Planar faces of s with the given normal lying in the plane axis == at."""
    return [f for f in s.Faces() if f.geomType() == "PLANE" and f.normalAt().dot(normal) > 0.99
            and abs(getattr(f.Center(), axis) - at) < 1e-3]


def thicken_walls(s):
    """Grow every outer side/end wall WALL_ADD outward, up to each section's rim,
    and carry each opening through a straight wall on through the new skin."""
    bb = s.BoundingBox()
    floor = max(_plane_faces(s, cq.Vector(0, 0, -1), bb.zmin, "z"), key=lambda f: f.Area())
    outline = floor.outerWire()
    inner = cq.Face.makeFromWires(outline)
    grown = cq.Face.makeFromWires(outline.offset2D(WALL_ADD, "intersection")[0])
    up = cq.Vector(0, 0, bb.zlen)
    skin = cq.Solid.extrudeLinear(grown, up).cut(cq.Solid.extrudeLinear(inner, up))
    # the display section's walls stop at its rim; the mechanical section's run full height
    mech_end = max(f.BoundingBox().ymax for f in _plane_faces(s, cq.Vector(-1, 0, 0), bb.xmin, "x"))
    front_rim = RIM_Z_V1 + FRONT_LIFT
    skin = skin.cut(cq.Solid.makeBox(400, 400, 100, cq.Vector(-200, mech_end, front_rim)))
    slab = cq.Solid.extrudeLinear(inner, cq.Vector(0, 0, 1))
    holes = 0
    for e in outline.Edges():
        if e.geomType() != "LINE":
            continue
        p0, p1 = e.startPoint(), e.endPoint()
        d = (p1 - p0).normalized()
        n = cq.Vector(d.y, -d.x, 0)
        if slab.isInside(e.Center() + n * 0.5 + cq.Vector(0, 0, 0.5)):
            n = -n                       # outward
        assert abs(n.x) > 0.999 or abs(n.y) > 0.999, "outer walls are axis-aligned"
        axis = "x" if abs(n.x) > 0.5 else "y"
        face_at = getattr(e.Center(), axis)
        probe_at = face_at - WALL_PROBE * (n.x if axis == "x" else n.y)
        lo, hi = sorted((face_at, probe_at))
        if axis == "x":
            probe = cq.Solid.makeBox(hi - lo, abs(p1.y - p0.y), bb.zlen + 1, cq.Vector(lo, min(p0.y, p1.y), bb.zmin))
        else:
            probe = cq.Solid.makeBox(abs(p1.x - p0.x), hi - lo, bb.zlen + 1, cq.Vector(min(p0.x, p1.x), lo, bb.zmin))
        void = probe.cut(s)
        for f in _plane_faces(void, -n, probe_at, axis):
            skin = skin.cut(cq.Solid.extrudeLinear(f, n * (WALL_PROBE + WALL_ADD + 0.2)))
            holes += 1
    return s.fuse(skin).clean().fix(), skin.Volume(), holes


def lid_v2():
    """The v1 lid with a WALL_ADD border on its three outer edges (not the y -20 edge
    toward the display section), flush with the thickened walls."""
    lid = stretch_bottom(cq.importers.importStep(LID_SRC).val())
    bb = lid.BoundingBox()
    top = max(_plane_faces(lid, cq.Vector(0, 0, 1), bb.zmax, "z"), key=lambda f: f.Area())
    grown = cq.Face.makeFromWires(top.outerWire().offset2D(WALL_ADD, "intersection")[0])
    border = cq.Solid.extrudeLinear(grown, cq.Vector(0, 0, -LID_PLATE_T))
    border = border.cut(cq.Solid.makeBox(400, 50, 50, cq.Vector(-200, bb.ymax, bb.zmin - 10)))
    return lid.fuse(border).clean().fix()


def raise_standoffs(enclosure):
    """Extend the four floor standoffs by PCB_RAISE, pilot holes continued."""
    out = enclosure
    for x, y in STANDOFFS:
        ext = (cq.Workplane("XY").workplane(offset=-35.5).center(x, y)
               .circle(STANDOFF_OD / 2).circle(STANDOFF_PILOT / 2).extrude(PCB_RAISE)).val()
        out = out.fuse(ext)
    return out.clean().fix()


def cut_harness_slot(enclosure):
    hs = HARNESS_SLOT
    y0, y1 = hs["wall_y"]
    slot = (cq.Workplane("XZ", origin=(0, y1, 0))
            .center(hs["cx"], hs["z0"] + hs["h"] / 2).slot2D(hs["w"], hs["h"]).extrude(y1 - y0)).val()
    removed = enclosure.intersect(slot).Volume()
    return enclosure.cut(slot).clean().fix(), removed, slot.Volume()


def remove_old_tds1_rails(enclosure):
    (x0, x1), (y0, y1), (z0, z1) = OLD_TDS1_RAILS
    region = cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
    # count from just off the wall: a region flush with it joins the rails through a sliver
    probe = cq.Solid.makeBox(x1 - x0 - 0.05, y1 - y0, z1 - z0, cq.Vector(x0 + 0.05, y0, z0))
    rails = enclosure.intersect(probe)
    if len(rails.Solids()) != 2:
        raise RuntimeError("expected the 2 old TDS-1 rails, found %d solids" % len(rails.Solids()))
    return enclosure.cut(region).clean().fix(), rails.Volume()


def speaker_housing():
    """Cup on the wall with snap fingers; returns (housing, grille_cutter)."""
    import math
    rid = (SPK_D + SPK_FIT) / 2
    x_open = SPK_WALL_X + SPK_H + SPK_LIP_T
    centre = cq.Vector(SPK_WALL_X, SPK_CY, SPK_CZ)
    xdir = cq.Vector(1, 0, 0)
    # tube base sunk SPK_EMBED into the wall so it fuses (flush faces only touch)
    base = cq.Vector(SPK_WALL_X - SPK_EMBED, SPK_CY, SPK_CZ)
    tube = (cq.Solid.makeCylinder(rid + SPK_WALL, SPK_H + SPK_LIP_T + SPK_EMBED, base, xdir)
            .cut(cq.Solid.makeCylinder(rid, SPK_H + SPK_LIP_T + SPK_EMBED + 0.01, base, xdir)))
    lip_at = cq.Vector(SPK_WALL_X + SPK_H, SPK_CY, SPK_CZ)
    lip = (cq.Solid.makeCylinder(rid + 0.01, SPK_LIP_T, lip_at, xdir)
           .cut(cq.Solid.makeCylinder(rid - SPK_LIP, SPK_LIP_T + 0.01, lip_at, xdir)))
    # entry chamfer: cone from the full bore at the open end down to the lip bore
    lip = lip.cut(cq.Solid.makeCone(rid + 0.01, rid - SPK_LIP, SPK_LIP_T * 0.8,
                                    cq.Vector(x_open, SPK_CY, SPK_CZ), cq.Vector(-1, 0, 0)))
    housing = tube.fuse(lip)
    for i in range(SPK_FINGERS):
        a = 360.0 * i / SPK_FINGERS
        slot = cq.Solid.makeBox(SPK_SLOT_DEPTH + 1, SPK_WALL + 2, SPK_SLOT_W,
                                cq.Vector(x_open - SPK_SLOT_DEPTH, SPK_CY + rid - SPK_LIP - 0.5,
                                          SPK_CZ - SPK_SLOT_W / 2))
        housing = housing.cut(slot.rotate(centre, centre + xdir, a))
    grille = None
    n = int(SPK_GRILLE_R // SPK_GRILLE_PITCH)
    for k in range(-n, n + 1):
        dz = k * SPK_GRILLE_PITCH
        half = math.sqrt(max(SPK_GRILLE_R ** 2 - dz ** 2, 0))
        if half < 2:
            continue
        slit = cq.Solid.makeBox(SPK_WALL_X - WALL_OUTER_X + 1.0, 2 * half, SPK_GRILLE_W,
                                cq.Vector(WALL_OUTER_X - 0.5, SPK_CY - half, SPK_CZ + dz - SPK_GRILLE_W / 2))
        grille = slit if grille is None else grille.fuse(slit)
    return housing.clean(), grille


def tds_rails(wall_y, inward, cx, cz):
    """Two vertical rails standing TDS_RAIL_D off a wall, one per pair of holes."""
    hz = (cz - TDS_HOLES[1] / 2, cz + TDS_HOLES[1] / 2)
    z0, z1 = hz[0] - TDS_RAIL_W / 2 - 1.0, hz[1] + TDS_RAIL_W / 2 + 1.0
    y0 = wall_y if inward > 0 else wall_y - TDS_RAIL_D
    out = []
    for hx in (cx - TDS_HOLES[0] / 2, cx + TDS_HOLES[0] / 2):
        rail = cq.Solid.makeBox(TDS_RAIL_W, TDS_RAIL_D, z1 - z0, cq.Vector(hx - TDS_RAIL_W / 2, y0, z0))
        for z in hz:
            rail = rail.cut(cq.Solid.makeCylinder(TDS_PILOT_D / 2, TDS_RAIL_D + 0.2,
                                                  cq.Vector(hx, y0 - 0.1, z), cq.Vector(0, 1, 0)))
        out.append(rail)
    return out


def tds_standins():
    """Each board (1.6 mm) plus its TDS_PART_H part zone, on its rails (review only)."""
    w, h = TDS_BOARD
    depth = 1.6 + TDS_PART_H
    out = []
    for _name, wall_y, inward, cx, cz in TDS_MOUNTS:
        face = wall_y + inward * TDS_RAIL_D
        y0 = face if inward > 0 else face - depth
        out.append(cq.Solid.makeBox(w, depth, h, cq.Vector(cx - w / 2, y0, cz - h / 2)))
    return out


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
    top = RIM_Z_V1 + FRONT_LIFT
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
    v1 = cq.importers.importStep(SRC).val()
    v2, removed = remove_old_tds1_rails(v1)
    print("removed the old left-wall TDS-1 rails (%.1f mm^3)" % removed)
    v2, band = lift_region(v2, LIFT_Y0, LIFT_Y1, SPLIT_Z, LIFT)
    print("mechanical section +%.0f mm (band %.2f cm^3)" % (LIFT, band.Volume() / 1000))
    before = v2.Volume()
    v2 = restore_bulkheads(v2)
    print("bulkhead holes back at v1 z (%+.1f mm^3, expect 0), valid=%s, solids=%d" % (
        v2.Volume() - before, v2.isValid(), len(v2.Solids())))
    v2, band = lift_region(v2, FRONT_Y0, 200.0, FRONT_SPLIT_Z, FRONT_LIFT)
    print("display/PCB section +%.0f mm (band %.2f cm^3), inside height %.0f mm" % (
        FRONT_LIFT, band.Volume() / 1000, 48 + FRONT_LIFT))
    print("enclosure v1 %.1f cm^3 -> v2 %.1f cm^3  valid=%s solids=%d" % (
        v1.Volume() / 1000, v2.Volume() / 1000, v2.isValid(), len(v2.Solids())))
    bb = v2.BoundingBox()
    print("enclosure v2 bbox: %.1f x %.1f x %.1f mm (z %.2f..%.2f)" % (
        bb.xlen, bb.ylen, bb.zlen, bb.zmin, bb.zmax))
    v2 = stretch_bottom(v2)
    print("bottom end down %.0f mm (split y %.0f), valid=%s, solids=%d" % (
        BOTTOM_DROP, BOTTOM_SPLIT_Y, v2.isValid(), len(v2.Solids())))
    psw = pressure_switch_housing().translate(cq.Vector(0, -PSW_DROP, 0))
    v2 = v2.cut(_box(*PSW_ZONE)).fuse(psw).clean().fix()
    pb = psw.BoundingBox()
    print("pressure-switch housing: %.0f mm walls, down %.0f mm, outside x %.2f..%.2f y %.2f..%.2f, valid=%s, solids=%d" % (
        PSW_WALL, PSW_DROP, pb.xmin, pb.xmax, pb.ymin, pb.ymax, v2.isValid(), len(v2.Solids())))
    v2, skin, holes = thicken_walls(v2)
    bb = v2.BoundingBox()
    print("outer walls +%.0f mm outward (skin %.1f cm^3, %d openings carried through): %.1f x %.1f mm, valid=%s, solids=%d" % (
        WALL_ADD, skin / 1000, holes, bb.xlen, bb.ylen, v2.isValid(), len(v2.Solids())))
    lid = lid_v2()
    lb = lid.BoundingBox()
    print("lid v2: %.1f x %.1f mm, valid=%s, solids=%d" % (lb.xlen, lb.ylen, lid.isValid(), len(lid.Solids())))
    cq.exporters.export(cq.Workplane().add(lid), os.path.join(HERE, "WQCS_Encl_lid_v2.step"))
    cq.exporters.export(cq.Workplane().add(lid), os.path.join(HERE, "WQCS_Encl_lid_v2.stl"),
                        tolerance=0.05, angularTolerance=0.1)
    if PCB_RAISE:
        before = v2.Volume()
        v2 = raise_standoffs(v2)
        print("standoffs +%.1f mm (+%.1f mm^3), valid=%s" % (PCB_RAISE, v2.Volume() - before, v2.isValid()))
    v2, cut, slot_vol = cut_harness_slot(v2)
    hs = HARNESS_SLOT
    area = hs["w"] * hs["h"] - (4 - 3.14159) * (hs["h"] / 2) ** 2
    print("harness slot %.0f x %.0f mm (%.0f mm^2) at x %.1f, z %.1f..%.1f: removed %.1f mm^3, valid=%s" % (
        hs["w"], hs["h"], area, hs["cx"], hs["z0"], hs["z0"] + hs["h"], cut, v2.isValid()))
    for name, wall_y, inward, cx, cz in TDS_MOUNTS:
        before = v2.Volume()
        for rail in tds_rails(wall_y, inward, cx, cz):
            v2 = v2.fuse(rail)
        v2 = v2.clean().fix()
        print("added %s rails on the wall at y %.0f (+%.1f mm^3), valid=%s, solids=%d" % (
            name, wall_y, v2.Volume() - before, v2.isValid(), len(v2.Solids())))
    x0, x1, y0, y1, z0, z1 = USB_RIM_NOTCH
    v2 = v2.cut(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))).clean().fix()
    x0, x1, y0, y1, z0, z1 = USB_PLUG_ENCL
    plug = cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
    print("USB-C rim notch: plug vs enclosure %.2f mm^3, valid=%s, solids=%d" % (
        plug.intersect(v2).Volume(), v2.isValid(), len(v2.Solids())))
    housing, grille = speaker_housing()
    before = v2.Volume()
    v2 = v2.fuse(housing).cut(grille).clean().fix()
    print("speaker housing at y %.0f z %.0f on the left wall (+%.1f mm^3 net), valid=%s, solids=%d" % (
        SPK_CY, SPK_CZ, v2.Volume() - before, v2.isValid(), len(v2.Solids())))
    # speaker test coupon: the same geometry, cut out of the finished enclosure
    h = COUPON / 2
    coupon = v2.intersect(cq.Solid.makeBox(SPK_WALL_X + SPK_H + SPK_LIP_T + 1 - WALL_OUTER_X, COUPON, COUPON,
                                           cq.Vector(WALL_OUTER_X, SPK_CY - h, SPK_CZ - h))).clean()
    cb = coupon.BoundingBox()
    print("speaker coupon: %d solid, %.1f x %.1f x %.1f mm, %.1f cm^3, valid=%s" % (
        len(coupon.Solids()), cb.ylen, cb.zlen, cb.xlen, coupon.Volume() / 1000, coupon.isValid()))
    cq.exporters.export(cq.Workplane().add(coupon), os.path.join(HERE, "Speaker_Test_Coupon.step"))
    cq.exporters.export(cq.Workplane().add(coupon), os.path.join(HERE, "Speaker_Test_Coupon.stl"),
                        tolerance=0.02, angularTolerance=0.1)
    boards = tds_standins()
    board, parts = main_pcb()
    print("fit check (mm^3 of overlap; TDS boxes include a %.0f mm part zone):" % TDS_PART_H)
    for (name, *_), b in zip(TDS_MOUNTS, boards):
        bb = b.BoundingBox()
        print("  %s (x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f) vs enclosure %.2f, vs main PCB parts %.2f, vs board %.2f" % (
            name, bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax,
            b.intersect(v2).Volume(), b.intersect(parts).Volume(), b.intersect(board).Volume()))
    print("  main PCB parts vs enclosure %.2f, board vs enclosure %.2f" % (
        parts.intersect(v2).Volume(), board.intersect(v2).Volume()))
    spk = cq.Solid.makeCylinder(SPK_D / 2, SPK_H, cq.Vector(SPK_WALL_X, SPK_CY, SPK_CZ), cq.Vector(1, 0, 0))
    print("  speaker (in place) vs enclosure %.2f, vs PCB parts %.2f, vs TDS %s" % (
        spk.intersect(v2).Volume(), spk.intersect(parts).Volume(),
        ["%.2f" % spk.intersect(b).Volume() for b in boards]))
    fit = cq.Assembly()
    fit.add(v2, name="enclosure_v2", color=cq.Color(0.6, 0.7, 0.9))
    fit.add(board, name="main_pcb", color=cq.Color(0.8, 0.2, 0.2))
    fit.add(parts, name="main_pcb_parts", color=cq.Color(0.2, 0.2, 0.2))
    for (name, *_), b in zip(TDS_MOUNTS, boards):
        fit.add(b, name=name.lower().replace("-", "") + "_standin", color=cq.Color(0.3, 0.6, 0.3))
    fit.add(spk, name="speaker_standin", color=cq.Color(0.9, 0.3, 0.3))
    fit.export(os.path.join(HERE, "WQCS_v2_fit_check.step"))
    cq.exporters.export(cq.Workplane().add(v2), os.path.join(HERE, "WQCS_Enclosure_v2.step"))
    cq.exporters.export(cq.Workplane().add(v2), os.path.join(HERE, "WQCS_Enclosure_v2.stl"),
                        tolerance=0.05, angularTolerance=0.1)
    print("wrote WQCS_Enclosure_v2.step/.stl")
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
