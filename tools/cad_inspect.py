"""Summarize a STEP file's geometry: solids, overall size, holes/bosses and
large flat faces. For planning edits to the enclosure without opening Fusion.

Usage:  ~/venvs/cad/bin/python tools/cad_inspect.py CAD/<file>.step [--min-area 100]
(CadQuery lives in its own venv: python3 -m venv ~/venvs/cad && ~/venvs/cad/bin/pip install cadquery)
"""
import argparse
from collections import defaultdict

import cadquery as cq


def fmt(v):
    return "(%7.2f, %7.2f, %7.2f)" % (v.x, v.y, v.z)


def bbox(shape):
    b = shape.BoundingBox()
    return b, "x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f  (size %.2f x %.2f x %.2f mm)" % (
        b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax, b.xlen, b.ylen, b.zlen)


def cylinders(solid):
    """Group cylindrical faces by (diameter, axis direction, axis position)."""
    groups = defaultdict(list)
    for f in solid.Faces():
        if f.geomType() != "CYLINDER":
            continue
        surf = f._geomAdaptor().Cylinder()
        r = surf.Radius()
        ax = surf.Axis()
        d, p = ax.Direction(), ax.Location()
        direction = tuple(round(abs(c), 2) for c in (d.X(), d.Y(), d.Z()))
        fb = f.BoundingBox()
        # axis position projected: report the face's centre, which sits on the axis for full holes
        key = (round(2 * r, 2), direction)
        groups[key].append((fb.center, fb, f.Area()))
    return groups


def planes(solid, min_area):
    out = []
    for f in solid.Faces():
        if f.geomType() != "PLANE" or f.Area() < min_area:
            continue
        n = f.normalAt()
        out.append((f.Area(), n, f.BoundingBox()))
    return sorted(out, key=lambda t: -t[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("--min-area", type=float, default=100.0, help="flat faces smaller than this (mm^2) are skipped")
    args = ap.parse_args()

    shape = cq.importers.importStep(args.step)
    solids = shape.solids().vals()
    print("FILE", args.step)
    print("solids:", len(solids))
    _, all_box = bbox(shape.val() if len(solids) == 1 else cq.Compound.makeCompound(solids))
    print("overall:", all_box)
    for i, s in enumerate(solids):
        _, sb = bbox(s)
        print("\n=== solid %d: volume %.1f cm^3, %d faces" % (i, s.Volume() / 1000, len(s.Faces())))
        print("  bbox:", sb)
        print("  cylinders (holes/bosses), grouped by diameter + axis direction:")
        for (dia, direction), items in sorted(cylinders(s).items()):
            print("    d=%6.2f axis %-17s x%-3d" % (dia, direction, len(items)), end="")
            centres = sorted(set((round(c.x, 1), round(c.y, 1), round(c.z, 1)) for c, _, _ in items))
            print(" at", centres[:12], "..." if len(centres) > 12 else "")
        print("  flat faces >= %.0f mm^2 (area, normal, extent):" % args.min_area)
        for area, n, fb in planes(s, args.min_area)[:25]:
            print("    %8.1f  n%s  x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (
                area, fmt(n), fb.xmin, fb.xmax, fb.ymin, fb.ymax, fb.zmin, fb.zmax))


if __name__ == "__main__":
    main()
