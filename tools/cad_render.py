"""Render a STEP file to PNG views (shaded, matplotlib) for quick visual checks.

Usage:  ~/venvs/cad/bin/python tools/cad_render.py CAD/<file>.step out.png [--views iso,top,front,right,back,iso2]
"""
import argparse

import cadquery as cq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

VIEWS = {  # (elevation, azimuth)
    "iso": (30, -60), "iso2": (30, 120), "top": (90, -90), "bottom": (-90, -90),
    "front": (0, -90), "back": (0, 90), "right": (0, 0), "left": (0, 180),
}


def mesh(shape, tol=0.2):
    verts, tris = shape.tessellate(tol, 0.3)
    v = np.array([(p.x, p.y, p.z) for p in verts])
    return v, np.array(tris)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+", help="STEP files, last argument is the output PNG")
    ap.add_argument("--views", default="iso,iso2,top,front")
    args = ap.parse_args()
    *steps, out = args.steps
    shapes = [cq.importers.importStep(s).val() for s in steps]
    meshes = [mesh(s) for s in shapes]
    allv = np.vstack([m[0] for m in meshes])
    lo, hi = allv.min(0), allv.max(0)
    span = (hi - lo).max() / 2
    mid = (hi + lo) / 2
    views = args.views.split(",")
    fig = plt.figure(figsize=(7 * len(views), 7))
    light = np.array([0.4, -0.5, 0.8])
    light /= np.linalg.norm(light)
    colors = [(0.55, 0.7, 0.9), (0.95, 0.7, 0.4), (0.6, 0.85, 0.6)]
    for i, name in enumerate(views):
        ax = fig.add_subplot(1, len(views), i + 1, projection="3d")
        for k, (v, t) in enumerate(meshes):
            tri = v[t]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            shade = 0.35 + 0.65 * np.clip(np.abs(n @ light), 0, 1)
            base = np.array(colors[k % len(colors)])
            pc = Poly3DCollection(tri, facecolors=shade[:, None] * base, edgecolor="none")
            ax.add_collection3d(pc)
        ax.set_xlim(mid[0] - span, mid[0] + span)
        ax.set_ylim(mid[1] - span, mid[1] + span)
        ax.set_zlim(mid[2] - span, mid[2] + span)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(*VIEWS[name])
        ax.set_title(name)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
    plt.tight_layout()
    plt.savefig(out, dpi=90)
    print("wrote", out)


if __name__ == "__main__":
    main()
