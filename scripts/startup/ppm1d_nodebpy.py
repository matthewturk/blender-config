"""
PPM 1D Interpolation — nodebpy geometry node tree

Implements the Piecewise Parabolic Method (PPM) sub-grid reconstruction
from ppm_1d.py entirely inside Blender geometry nodes.

Usage in Blender:
    import bpy
    # Either run this file directly, or import and call build_ppm_tree()

Inputs:
    Geometry       – a poly curve whose points carry the cell-average values
    Attribute Name – name of the float attribute to interpolate
    Samples Per Step – number of sub-grid samples per original cell (default 12)

Output:
    A resampled curve with N× original point count.  Each point carries a
    float attribute "ppm_value" with the PPM-interpolated value at the
    sub-grid midpoint.
"""

import bpy
from nodebpy import geometry as g


def build_ppm_tree(name: str = "PPM 1D Interpolation"):
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        existing.interface.clear()
        existing.nodes.clear()

    with g.tree(existing or name) as tree:
        geometry  = tree.inputs.geometry("Curve")
        attr_name = tree.inputs.string("Attribute Name", "value")
        n_samples = tree.inputs.integer("Samples Per Step", 12, min_value=3)

        # ── how many original points? ───────────────────────────────────
        original_count = g.DomainSize(geometry, component="CURVE").o.point_count

        # total output points
        total_count = original_count * n_samples

        # ── resample to N× more points ──────────────────────────────────
        resampled = g.ResampleCurve(geometry, mode="COUNT", count=total_count)

        # ── per-point indexing ───────────────────────────────────────────
        global_idx = g.Index()
        parent_idx = global_idx // n_samples   # IntegerMath.divide_floor
        sub_idx    = global_idx % n_samples    # IntegerMath.modulo

        # ── edge-clamped neighbour indices ───────────────────────────────
        def clamp(idx):
            return g.Math.maximum(0, g.Math.minimum(idx, original_count - 1))

        i_m2 = clamp(parent_idx - 2)
        i_m1 = clamp(parent_idx - 1)
        i_c  = parent_idx
        i_p1 = clamp(parent_idx + 1)
        i_p2 = clamp(parent_idx + 2)

        # ── read the named attribute from the *original* curve ──────────
        a_m2 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_m2)
        a_m1 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_m1)
        a_c  = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_c)
        a_p1 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_p1)
        a_p2 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_p2)

        # ── PPM interface values (cubic interpolation, no limiters) ─────
        a_l = (7.0 / 12.0) * (a_m1 + a_c) - (1.0 / 12.0) * (a_m2 + a_p1)
        a_r = (7.0 / 12.0) * (a_c + a_p1) - (1.0 / 12.0) * (a_m1 + a_p2)

        # ── shape coefficients ───────────────────────────────────────────
        da = a_r - a_l
        a6 = 6.0 * a_c - 3.0 * (a_l + a_r)

        # ── evaluate parabola at sub-interval mid-point ──────────────────
        xi      = (sub_idx + 0.5) / n_samples
        ppm_val = a_l + xi * (da + a6 * (1.0 - xi))

        # ── store and output ─────────────────────────────────────────────
        (
            resampled
            >> g.StoreNamedAttribute.point.float(name="ppm_value", value=ppm_val)
            >> tree.outputs.geometry("Output")
        )

    return tree


if __name__ == "__main__":
    build_ppm_tree()
