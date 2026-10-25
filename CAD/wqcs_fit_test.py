"""WQCS mechanical-section fit test: enclosure v2 + the three water components +
1/4" tubing, push-fit fittings and the IN/OUT bulkheads.

Inputs (CAD/, the user's Fusion models, already in enclosure v1 coordinates):
  Elec Water Valve.step  -- refill solenoid (body + two port collars)
  Pressure_switch.step   -- pressure switch (lower body + clamp/tee, one part; its
                            two pins wire to the main PCB), motorized ball valve (and a
                            copy of the solenoid, ignored); MotorizeValve.step
                            is an empty export, so the valve comes from here
  WQCS_Enclosure_v2.step -- from wqcs_case_v2.py (run that first)
The pressure switch follows its housing down PSW_DROP and the solenoid follows
the bottom end wall down BOTTOM_DROP (from wqcs_case_v2.py); the motorized
valve stays on its shelf.

Water path, traced from photo IMG_6381 (x right, y up as the unit hangs, z toward
the lid):
  IN  left bulkhead -> straight tube through the pressure switch -> elbow E1 ->
      elbow E2 -> ball valve right port
      ball valve left port -> elbow E3 (down) -> tube -> solenoid left port
      solenoid right port -> elbow E5 (toward the lid) -> elbow E6 (left) ->
  OUT U-loop in front of the solenoid -> right bulkhead
Push-fit elbows swivel, so E1/E2 are turned to whatever direction joins the two
ports. Fittings are envelopes from typical John Guest 1/4" sizes (** not
measured **); tubes are 1/4" (6.35 mm) OD.

Output: WQCS_fit_test.step (assembly, review only). Overlaps per part are printed.
Run:  ~/venvs/cad/bin/python CAD/wqcs_fit_test.py
"""
import os

import cadquery as cq

import wqcs_case_v2 as case

HERE = os.path.dirname(os.path.abspath(__file__))
ENCLOSURE = os.path.join(HERE, "WQCS_Enclosure_v2.step")
SOLENOID = os.path.join(HERE, "Elec Water Valve.step")
SWITCH_SET = os.path.join(HERE, "Pressure_switch.step")   # solids: 0+1 pressure switch (lower body, clamp/tee), 2 motorized valve

# ---- 1/4" push-fit parts (John Guest-style; ** typical, not measured **) ----
TUBE_OD = 6.35
FIT_D = 13.5            # collet / body diameter
ELBOW_ARM = 19.0        # centre to collet face
STEM_BODY = 10.0        # stem elbow: centre to the shoulder that seats on a collet face
STEM_IN = 16.0          # stem pushed into a collet / push-fit port
ADAPTER_L = 14.0        # threaded adapter in the ball valve, outside length (estimated from IMG_6381)
BH_NUT_D, BH_NUT_T = 24.0, 6.0
BH_BODY_D = 15.9
BH_IN_BODY, BH_OUT_BODY = 14.0, 6.0   # thread showing beyond each nut
BH_COLLET = 8.0
STUB = 40.0             # outside supply/outlet tube shown

# ---- pressure switch pins + wires (** pin size and wire OD estimated **) ----
# Both pins face the housing's left-end slot and both wires leave through it, then
# run along the left side through the 10 x 19 cable slot in the shelf (y -81) and the
# shared wall (y -19) into the display section.
PIN_D, PIN_L = 1.5, 6.0
WIRE_OD = 2.0
PIN1 = (-42.75, None, -9.6)       # left end face of the lower body; y = slot centre (set in build)
PIN2 = (-29.8, -116.74, -25.6)    # face of the step under the lower body, centred (v1 y)
CABLE_SLOT = (-66.95, -28.0)      # x, z: slot x -71.95..-61.95, z -37..-18
WIRE_END_Y = -14.0                # just past the shared wall (main-PCB standoff at y -11.8)

# ---- component ports (v1 coordinates, from the models) ----
SW_AXIS = (-116.7, 13.4)          # switch bore along x: y, z
SW_X = (-22.75, 9.25)
BV_AXIS = (-95.9, -14.0)          # ball valve body along x
BV_X = (-40.42, 5.58)
SOL_AXIS = (-175.8, -18.0)        # solenoid ports along x
SOL_X = (-48.25, 11.25)

V = cq.Vector


def cyl(d, p0, p1):
    p0, p1 = V(*p0), V(*p1)
    return cq.Solid.makeCylinder(d / 2, (p1 - p0).Length, p0, (p1 - p0).normalized())


def elbow(c, a, b, stem=False):
    """Elbow centred at c with arms toward directions a and b. With stem, arm a is a
    plug-in stem (shoulder STEM_BODY from c, then a tube-sized stem STEM_IN long)."""
    c = V(*c)
    body = cq.Solid.makeSphere(FIT_D / 2, c, angleDegrees1=-90, angleDegrees2=90)
    a, b = V(*a).normalized(), V(*b).normalized()
    if stem:
        body = body.fuse(cyl(FIT_D, c, c + a * STEM_BODY)).fuse(
            cyl(TUBE_OD, c + a * STEM_BODY, c + a * (STEM_BODY + STEM_IN)))
    else:
        body = body.fuse(cyl(FIT_D, c, c + a * ELBOW_ARM))
    return body.fuse(cyl(FIT_D, c, c + b * ELBOW_ARM)).clean()


def tube(points, t0=None, t1=None, d=TUBE_OD):
    """Round section (1/4" tube by default) swept along a spline through points
    (end tangents optional)."""
    pts = [V(*p) for p in points]
    if len(pts) == 2 and t0 is None:
        edge = cq.Edge.makeLine(*pts)
        t0 = pts[1] - pts[0]
    else:
        edge = cq.Edge.makeSpline(pts, tangents=[V(*t0), V(*t1)] if t0 else None)
        t0 = t0 or edge.tangentAt(0)
    plane = cq.Plane(origin=pts[0], normal=V(*t0).normalized())
    return cq.Workplane(plane).circle(d / 2).sweep(cq.Workplane().add(cq.Wire.assembleEdges([edge]))).val()


def bulkhead(wall_in_x, wall_out_x, y, z):
    """Bulkhead union through a wall: nut + thread + collet on each side.
    Returns (solid, inner collet face point, outer collet face point)."""
    s = 1 if wall_out_x > wall_in_x else -1     # outward along x
    xi, xo = wall_in_x, wall_out_x
    parts = [cyl(BH_BODY_D, (xi, y, z), (xo, y, z))]
    x = xi
    for d, l in ((BH_NUT_D, BH_NUT_T), (BH_BODY_D, BH_IN_BODY), (FIT_D, BH_COLLET)):
        parts.append(cyl(d, (x, y, z), (x - s * l, y, z)))
        x -= s * l
    inner = (x, y, z)
    x = xo
    for d, l in ((BH_NUT_D, BH_NUT_T), (BH_BODY_D, BH_OUT_BODY), (FIT_D, BH_COLLET)):
        parts.append(cyl(d, (x, y, z), (x + s * l, y, z)))
        x += s * l
    body = parts[0]
    for p in parts[1:]:
        body = body.fuse(p)
    return body.clean(), inner, (x, y, z)


def build():
    sw_dy, bv_dy, sol_dy = -case.PSW_DROP, 0.0, -case.BOTTOM_DROP
    src = cq.importers.importStep(SWITCH_SET).solids().vals()
    parts = {
        "pressure_switch": src[0].fuse(src[1]).clean().translate(V(0, sw_dy, 0)),
        "motorized_valve": src[2].translate(V(0, bv_dy, 0)),
    }
    sol = cq.importers.importStep(SOLENOID).solids().vals()
    s = sol[0]
    for p in sol[1:]:
        s = s.fuse(p)
    parts["solenoid_valve"] = s.clean().translate(V(0, sol_dy, 0))

    fit, tubes = {}, {}
    wl_in, wl_out = -78.511667, -78.511667 - 2.0 - case.WALL_ADD      # left wall faces (v2)
    wr_in, wr_out = 37.488333, 37.488333 + 2.0 + case.WALL_ADD       # right wall faces (v2)
    (_, _, lz), (_, _, rz) = [(x0, y, z) for x0, x1, y, z in case.BULKHEADS]
    ly, ry = case.BULKHEADS[0][2], case.BULKHEADS[1][2]

    # IN: left bulkhead, outside elbow turning down to the supply
    fit["bulkhead_IN"], in_in, in_out = bulkhead(wl_in, wl_out, ly, lz)
    e_in = (in_out[0] - STEM_BODY, ly, lz)
    fit["elbow_IN_outside"] = elbow(e_in, (1, 0, 0), (0, -1, 0), stem=True)
    tubes["tube_IN_supply"] = tube([(e_in[0], ly - ELBOW_ARM + 2, lz), (e_in[0], ly - ELBOW_ARM - STUB, lz)])

    # bulkhead -> through the switch -> E1
    sy, sz = SW_AXIS[0] + sw_dy, SW_AXIS[1]
    by, bz = BV_AXIS[0] + bv_dy, BV_AXIS[1]
    xe = BV_X[1] + ADAPTER_L + STEM_BODY                             # E1/E2 centre x
    tubes["tube_IN_to_switch"] = tube([(in_in[0] - 2, ly, lz), (SW_X[0], sy, sz)], (1, 0, 0), (1, 0, 0))
    tubes["tube_through_switch"] = tube([(SW_X[0], sy, sz), (xe - ELBOW_ARM + STEM_IN, sy, sz)])
    # E2 plugs into the ball valve's right adapter; E1 takes the switch tube. Both swivel
    # toward each other (collet arm to collet arm, joined by tube if there is room).
    # E1 (switch side) and E2 (stem into the ball valve's right adapter), swivelled toward each other
    c1, c2 = V(xe, sy, sz), V(xe, by, bz)
    d12 = (c2 - c1).normalized()
    fit["elbow_E1"] = elbow(c1.toTuple(), (-1, 0, 0), d12.toTuple())
    fit["elbow_E2"] = elbow(c2.toTuple(), (-1, 0, 0), (-d12).toTuple(), stem=True)
    gap = (c2 - c1).Length - 2 * ELBOW_ARM
    if gap > 0:
        tubes["tube_E1_E2"] = tube([(c1 + d12 * (ELBOW_ARM - 2)).toTuple(), (c2 - d12 * (ELBOW_ARM - 2)).toTuple()])
    fit["adapter_valve_R"] = cyl(FIT_D, (BV_X[1], by, bz), (BV_X[1] + ADAPTER_L, by, bz))
    fit["adapter_valve_L"] = cyl(FIT_D, (BV_X[0], by, bz), (BV_X[0] - ADAPTER_L, by, bz))

    # ball valve left -> E3 (down) -> solenoid left port
    c3 = (BV_X[0] - ADAPTER_L - STEM_BODY, by, bz)
    fit["elbow_E3"] = elbow(c3, (1, 0, 0), (0, -1, 0), stem=True)
    oy, oz = SOL_AXIS[0] + sol_dy, SOL_AXIS[1]
    tubes["tube_valve_to_solenoid"] = tube(
        [(c3[0], by - ELBOW_ARM + 2, bz), (c3[0], oy + 22, (bz + oz) / 2), (SOL_X[0] + 4, oy, oz)],
        (0, -1, 0), (1, 0, 0))   # into the solenoid's push-fit port

    # solenoid right -> E5 (toward the lid) -> E6 (left) -> U-loop in front of the solenoid -> OUT
    c5 = (SOL_X[1] + STEM_BODY, oy, oz)                  # stem into the solenoid's right port
    c6 = (c5[0], oy, oz + ELBOW_ARM + STEM_BODY)         # stem into E5's collet
    fit["elbow_E5"] = elbow(c5, (-1, 0, 0), (0, 0, 1), stem=True)
    fit["elbow_E6"] = elbow(c6, (0, 0, -1), (-1, 0, 0), stem=True)
    fit["bulkhead_OUT"], out_in, out_out = bulkhead(wr_in, wr_out, ry, rz)
    x6 = c6[0] - ELBOW_ARM + 2
    tubes["tube_solenoid_to_OUT"] = tube(
        [(x6, oy, c6[2]), (x6 - 22, oy + 2, c6[2] + 2), (x6 - 34, (oy + ry) / 2, (c6[2] + rz) / 2),
         (x6 - 20, ry, rz), (out_in[0] + 2, ry, rz)],
        (-1, 0, 0), (1, 0, 0))
    tubes["tube_OUT_boiler"] = tube([(out_out[0] - 2, ry, rz), (out_out[0] + STUB, ry, rz)])

    # pressure switch pins -> slot -> cable holes -> display section
    slot_y = (case.PSW_SLOT[0] + case.PSW_SLOT[1]) / 2 - case.PSW_DROP
    hx, hz = CABLE_SLOT
    pins = [(PIN1[0], slot_y, PIN1[2]), (PIN2[0], PIN2[1] + sw_dy, PIN2[2])]
    for i, ((px, py, pz), dx) in enumerate(zip(pins, (-2.0, 2.0)), 1):
        tip = px - PIN_L
        fit["switch_pin_%d" % i] = cyl(PIN_D, (px + 0.5, py, pz), (tip, py, pz))
        # straight out through the slot, down to the cable-slot height before the
        # valve-to-solenoid tube (x ~ -64, z ~ -15), then along the left side
        lead = [(tip + 0.5, py, pz), (min(tip, -48.0) - 2, py, pz),
                (-55.0, py + 2, hz + 2), (hx + dx, py + 12, hz)]
        tubes["wire_%d" % i] = tube(lead + [(hx + dx, -95.0, hz)], (-1, 0, 0), (0, 1, 0), d=WIRE_OD)
        tubes["wire_%d_run" % i] = tube([(hx + dx, -95.0, hz), (hx + dx, WIRE_END_Y, hz)], d=WIRE_OD)
    return parts, fit, tubes, gap


def main():
    enclosure = cq.importers.importStep(ENCLOSURE).val()
    parts, fit, tubes, gap = build()
    everything = {**parts, **fit, **tubes}
    print("E1-E2 centre distance leaves %.1f mm of tube between the elbows%s" % (
        gap, "" if gap > 0 else " (overlap: E1 and E2 can't both be collet elbows here)"))
    print("overlap with the enclosure (mm^3):")
    for name, solid in everything.items():
        ov = solid.intersect(enclosure).Volume()
        print("  %-24s %8.2f%s" % (name, ov, "" if ov < 1 or name.startswith("bulkhead") else "  <-- CLASH"))
    print("overlaps with the components (mm^3), expected joints excluded:")
    expected = {("switch_pin_1", "pressure_switch"), ("switch_pin_2", "pressure_switch"),
                ("elbow_E5", "solenoid_valve"), ("elbow_E2", "motorized_valve"), ("elbow_E3", "motorized_valve"), ("tube_valve_to_solenoid", "solenoid_valve"),
                ("tube_IN_to_switch", "pressure_switch"), ("tube_through_switch", "pressure_switch")}
    for name, solid in everything.items():
        for comp in parts:
            if name == comp or (name, comp) in expected or (name in parts and list(parts).index(name) > list(parts).index(comp)):
                continue
            ov = solid.intersect(parts[comp]).Volume()
            if ov > 0.5:
                print("  %-24s x %-18s %8.2f  <-- CLASH" % (name, comp, ov))
    asm = cq.Assembly()
    asm.add(enclosure, name="enclosure_v2", color=cq.Color(0.75, 0.75, 0.78, 0.6))
    colors = {"pressure_switch": (0.1, 0.1, 0.1),
              "motorized_valve": (0.1, 0.3, 0.85), "solenoid_valve": (0.85, 0.75, 0.5)}
    for name, solid in parts.items():
        asm.add(solid, name=name, color=cq.Color(*colors[name]))
    for name, solid in fit.items():
        asm.add(solid, name=name, color=cq.Color(0.95, 0.95, 0.92))
    for name, solid in tubes.items():
        asm.add(solid, name=name, color=cq.Color(0.9, 0.9, 1.0))
    asm.export(os.path.join(HERE, "WQCS_fit_test.step"))
    print("wrote WQCS_fit_test.step")


if __name__ == "__main__":
    main()
