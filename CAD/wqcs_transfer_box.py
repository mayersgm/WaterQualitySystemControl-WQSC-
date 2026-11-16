"""WQCS transfer box: the lower part of enclosure v2 (pressure-switch housing down
to the solenoid's end wall) as its own enclosure + lid, for the collector ->
reservoir transfer hardware (user, 2026-11-15): the booster pump's pressure
switch and the 12 V transfer solenoid, plumbed like the refill pair in the main
enclosure.

Method (inputs are the finished v2 parts, so run wqcs_case_v2.py first):
  * Box = WQCS_Enclosure_v2.step from the bottom end (y -197) up to y CUT_Y,
    plus a new top end: the existing bottom end slab (y -197..-197+END_SLAB),
    mirrored, so it has the same 4 mm end wall, corner posts and snap bead.
    The mirrored copy's solenoid screw holes and floor slot are filled.
  * Lid = WQCS_Encl_lid_v2.step treated the same way, so the new end gets the
    same snap tab as the bottom end. The side tabs are shortened by the cut.
  * Kept from v2: pressure-switch housing, solenoid end wall screw holes, IN
    bulkhead (left, on the switch axis) and OUT bulkhead (right).
  * Changes (user, 2026-11-15):
    - Keyholes: the box hangs bottom end down with its back (z min, "floor"
      in these coordinates) on the wall. KEYHOLES through the back near the
      top end: head hole below, slot above (the box drops onto the screws),
      each on a PAD inside so the head bears on PAD_T + 2 mm, not the 2 mm back.
    - Drain: the bottom end wall's cable slot is filled and a DRAIN_D hole
      drilled whose edge is flush with the back's inner face, where leaking
      water runs down to.
    - Solenoid power connector: a CONN_D hole in the left wall, in line
      below the IN bulkhead (same z) at the solenoid's mid-length, with a
      CONN_CB_D x CONN_CB_DEPTH counterbore so the shallow connector's nut seats.

Where to cut: the new end wall's inner face is at INNER_Y (default -84, the
old ball-valve shelf's underside). The tube fittings that joined the switch to
the ball valve and the solenoid reach ~y -89, so the existing routing still
fits with a straight tube where the ball valve was (fit test below).

Outputs (next to this script): WQCS_Transfer_Box.step/.stl,
WQCS_Transfer_Lid.step/.stl, WQCS_Transfer_fit_test.step (review only).
Run:  ~/venvs/cad/bin/python CAD/wqcs_transfer_box.py
"""
import os

import cadquery as cq

import wqcs_case_v2 as case
import wqcs_fit_test as ft

HERE = os.path.dirname(os.path.abspath(__file__))
ENCLOSURE = os.path.join(HERE, "WQCS_Enclosure_v2.step")
LID = os.path.join(HERE, "WQCS_Encl_lid_v2.step")

BOTTOM_Y = -197.0          # outer face of the bottom end wall
END_SLAB = 9.0             # bottom end slab mirrored for the new end (wall 4 + posts/bead/lid tab)
WALL_T = 4.0
INNER_Y = -84.0            # new end wall inner face
OUTER_Y = INNER_Y + WALL_T
CUT_Y = OUTER_Y - END_SLAB # the v2 parts are kept below this (plain wall band: y -105..-85)
OVERLAP = 0.1
BACK_IN_Z = -41.5          # inner face of the back (2 mm thick, outer z -43.5)
BACK_OUT_Z = -43.5
# keyholes (M4 / #8 pan or round head): head hole centre (x, y); the slot runs +y
KEYHOLES = ((-60.0, -102.0), (20.0, -102.0))
KEY_HEAD_D = 9.0
KEY_SLOT_W = 4.5
KEY_TRAVEL = 9.0           # head hole centre -> slot end centre
PAD = (18.0, 26.0)         # x, y size of the pad around each keyhole (inside)
PAD_T = 3.0
# drain in the bottom end wall: fill the v2 slot (x -74..-51, z -42..-29), drill DRAIN_D
BOTTOM_SLOT = (-74.0, -51.0, -42.0, -29.0)
DRAIN_D = 6.0
DRAIN_X = -62.5
# solenoid power connector (panel mount, 8.3 mm hole) in the left wall
CONN_D = 8.3
CONN_Y = -162.75           # solenoid body (y -192.75..-132.75 in v2) mid-length
CONN_Z = case.BULKHEADS[0][3]   # in line with the IN bulkhead (z 13.4)
# flat-bottom counterbore around it (user, 2026-11-15): thins the 4 mm wall to
# 2.5 mm so the shallow connector's thread reaches through far enough for its nut
CONN_CB_D = 13.0
CONN_CB_DEPTH = 1.5
CONN_CB_SIDE = "outside"   # "outside" (flange recessed) or "inside" (nut recessed)
LEFT_WALL_X = (-82.51, -78.51)

V = cq.Vector


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cut_and_close(shape):
    """Keep shape below CUT_Y and add the mirrored bottom-end slab as the new top end."""
    big = 500.0
    keep = shape.intersect(_box(-big, big, -big, CUT_Y + OVERLAP, -big, big))
    slab = shape.intersect(_box(-big, big, BOTTOM_Y, BOTTOM_Y + END_SLAB, -big, big))
    mid = (BOTTOM_Y + OUTER_Y) / 2
    end = slab.mirror("XZ", V(0, mid, 0))
    return keep.fuse(end).clean().fix()


def keyholes(b):
    """Pads inside the back, then the keyhole (head hole + slot) through pad and back."""
    z0, z1 = BACK_OUT_Z - 1, BACK_IN_Z + PAD_T + 1
    for x, y in KEYHOLES:
        b = b.fuse(_box(x - PAD[0] / 2, x + PAD[0] / 2, y - PAD[1] / 2 + KEY_TRAVEL / 2,
                        y + PAD[1] / 2 + KEY_TRAVEL / 2, BACK_IN_Z - 0.1, BACK_IN_Z + PAD_T))
    for x, y in KEYHOLES:
        cut = cq.Solid.makeCylinder(KEY_HEAD_D / 2, z1 - z0, V(x, y, z0))
        cut = cut.fuse(cq.Solid.makeCylinder(KEY_SLOT_W / 2, z1 - z0, V(x, y + KEY_TRAVEL, z0)))
        cut = cut.fuse(_box(x - KEY_SLOT_W / 2, x + KEY_SLOT_W / 2, y, y + KEY_TRAVEL, z0, z1))
        b = b.cut(cut)
    return b.clean().fix()


def drain(b):
    x0, x1, z0, z1 = BOTTOM_SLOT
    b = b.fuse(_box(x0, x1, BOTTOM_Y, BOTTOM_Y + WALL_T, BACK_OUT_Z, z1)).clean()
    z = BACK_IN_Z + DRAIN_D / 2
    return b.cut(cq.Solid.makeCylinder(DRAIN_D / 2, WALL_T + 2, V(DRAIN_X, BOTTOM_Y - 1, z),
                                       V(0, 1, 0))).clean().fix()


def connector_hole(b):
    x0, x1 = LEFT_WALL_X
    b = b.cut(cq.Solid.makeCylinder(CONN_D / 2, x1 - x0 + 2, V(x0 - 1, CONN_Y, CONN_Z), V(1, 0, 0)))
    start = x0 - 1 if CONN_CB_SIDE == "outside" else x1 - CONN_CB_DEPTH
    cb = cq.Solid.makeCylinder(CONN_CB_D / 2, CONN_CB_DEPTH + 1, V(start, CONN_Y, CONN_Z), V(1, 0, 0))
    return b.cut(cb).clean().fix()


def box():
    v2 = cq.importers.importStep(ENCLOSURE).val()
    bb = v2.BoundingBox()
    b = cut_and_close(v2)
    # fill the mirrored solenoid screw holes and floor slot (the new end stays solid)
    b = b.fuse(_box(bb.xmin, bb.xmax, INNER_Y, OUTER_Y, bb.zmin, bb.zmax)).clean()
    return connector_hole(drain(keyholes(b)))


def lid():
    return cut_and_close(cq.importers.importStep(LID).val())


def fit_parts():
    """The fit test's switch, solenoid, bulkheads and fittings, with a straight
    tube in place of the motorized ball valve, plus connector and screw-head
    envelopes. (The switch wires' old route up to the shelf slot is dropped.)"""
    parts, fit, tubes, _ = ft.build()
    del parts["motorized_valve"], fit["adapter_valve_R"], fit["adapter_valve_L"]
    by, bz = ft.BV_AXIS
    xe = ft.BV_X[1] + ft.ADAPTER_L + ft.STEM_BODY            # E2 centre x
    x3 = ft.BV_X[0] - ft.ADAPTER_L - ft.STEM_BODY            # E3 centre x
    tubes["tube_E2_E3 (was ball valve)"] = ft.tube([(xe - ft.STEM_BODY, by, bz), (x3 + ft.STEM_BODY, by, bz)])
    del tubes["wire_1_run"], tubes["wire_2_run"]
    # the pump line arrives from the left (user, 2026-11-15): straight into the IN
    # bulkhead, no elbow turning down outside
    del fit["elbow_IN_outside"], tubes["tube_IN_supply"]
    wl_in, wl_out = -78.511667, -78.511667 - 2.0 - case.WALL_ADD
    _, _, ly, lz = case.BULKHEADS[0]
    _, _, (ox, _, _) = ft.bulkhead(wl_in, wl_out, ly, lz)
    tubes["tube_IN_from_pump"] = ft.tube([(ox + 2, ly, lz), (ox - ft.STUB, ly, lz)])
    x0, x1 = LEFT_WALL_X
    fit["connector_inside (12x25)"] = ft.cyl(12.0, (x1, CONN_Y, CONN_Z), (x1 + 25.0, CONN_Y, CONN_Z))
    fit["connector_plug_outside (12x35)"] = ft.cyl(12.0, (x0, CONN_Y, CONN_Z), (x0 - 35.0, CONN_Y, CONN_Z))
    for i, (x, y) in enumerate(KEYHOLES, 1):   # screw head hung at the slot end, 3 mm tall
        top = BACK_IN_Z + PAD_T
        fit["screw_head_%d" % i] = ft.cyl(8.0, (x, y + KEY_TRAVEL, top), (x, y + KEY_TRAVEL, top + 3.0))
    return parts, fit, tubes


def main():
    b = box()
    l = lid()
    for name, s in (("box", b), ("lid", l)):
        bb = s.BoundingBox()
        print("%s: %.1f x %.1f x %.1f mm (y %.2f..%.2f), %.1f cm^3, valid=%s, solids=%d" % (
            name, bb.xlen, bb.ylen, bb.zlen, bb.ymin, bb.ymax, s.Volume() / 1000, s.isValid(), len(s.Solids())))
    print("inside length y %.1f..%.1f = %.1f mm" % (BOTTOM_Y + WALL_T, INNER_Y, INNER_Y - BOTTOM_Y - WALL_T))
    lid_on = l.translate(V(0, 0, case.LIFT))
    print("lid vs box %.2f mm^3 (snap tabs against the rim beads; the v2 pair shows the same)" %
          lid_on.intersect(b).Volume())

    parts, fit, tubes = fit_parts()
    print("fit test, overlap with the box / lid (mm^3):")
    everything = {**parts, **fit, **tubes}
    for name, s in everything.items():
        ov, ol = s.intersect(b).Volume(), s.intersect(lid_on).Volume()
        flag = "" if (ov < 1 or name.startswith(("bulkhead", "connector"))) and ol < 0.5 else "  <-- CLASH"
        print("  %-30s box %8.2f  lid %6.2f%s" % (name, ov, ol, flag))
    plug = fit["connector_plug_outside (12x35)"].fuse(fit["connector_inside (12x25)"])
    for name, s in everything.items():
        if not name.startswith(("connector", "bulkhead")) and s.intersect(plug).Volume() > 0.5:
            print("  connector vs %s: %.1f mm^3  <-- CLASH" % (name, s.intersect(plug).Volume()))
    top = max(s.BoundingBox().ymax for n, s in everything.items() if not n.startswith("wire"))
    print("highest fitting/tube y %.2f -> %.2f mm below the new end wall" % (top, INNER_Y - top))

    cq.exporters.export(cq.Workplane().add(b), os.path.join(HERE, "WQCS_Transfer_Box.step"))
    cq.exporters.export(cq.Workplane().add(b), os.path.join(HERE, "WQCS_Transfer_Box.stl"),
                        tolerance=0.05, angularTolerance=0.1)
    cq.exporters.export(cq.Workplane().add(l), os.path.join(HERE, "WQCS_Transfer_Lid.step"))
    cq.exporters.export(cq.Workplane().add(l), os.path.join(HERE, "WQCS_Transfer_Lid.stl"),
                        tolerance=0.05, angularTolerance=0.1)
    asm = cq.Assembly()
    asm.add(b, name="transfer_box", color=cq.Color(0.75, 0.75, 0.78, 0.6))
    asm.add(lid_on, name="transfer_lid", color=cq.Color(0.6, 0.65, 0.75, 0.5))
    colors = {"pressure_switch": (0.1, 0.1, 0.1), "solenoid_valve": (0.85, 0.75, 0.5)}
    for name, s in parts.items():
        asm.add(s, name=name, color=cq.Color(*colors[name]))
    for name, s in {**fit, **tubes}.items():
        asm.add(s, name=name.split(" ")[0], color=cq.Color(0.95, 0.95, 0.92))
    asm.export(os.path.join(HERE, "WQCS_Transfer_fit_test.step"))
    print("wrote WQCS_Transfer_Box.step/.stl, WQCS_Transfer_Lid.step/.stl, WQCS_Transfer_fit_test.step")


if __name__ == "__main__":
    main()
