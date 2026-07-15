"""
PPM 1D Interpolation — nodebpy geometry node group

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

from nodebpy import geometry as g
from nodebpy.builder import CustomGeometryGroup
from nodebpy.types import InputGeometry, InputInteger, InputString


# ---------------------------------------------------------------------------
# Reusable custom node group
# ---------------------------------------------------------------------------

class PPM1D(CustomGeometryGroup):
    """1-D Piecewise Parabolic Method interpolation on a curve attribute.

    For each original control point *i* the algorithm builds a parabola from
    the left and right interface values (cubic PPM reconstruction, monotonicity
    limiters disabled) and then samples it at *N* evenly-spaced sub-interval
    midpoints.  The output curve has *N × len(curve)* points, each carrying
    a ``ppm_value`` attribute.
    """

    _name = "PPM 1D"
    _color_tag = "CONVERTER"

    def __init__(
        self,
        geometry: InputGeometry = ...,
        attribute_name: InputString = "value",
        samples_per_step: InputInteger = 12,
    ):
        super().__init__(
            **{
                "Geometry": geometry,
                "Attribute Name": attribute_name,
                "Samples Per Step": samples_per_step,
            }
        )

    def _build_group(self, tree):
        # ── inputs ──────────────────────────────────────────────────────
        geometry   = tree.inputs.geometry("Geometry")
        attr_name  = tree.inputs.string("Attribute Name", "value")
        n_samples  = tree.inputs.integer("Samples Per Step", 12, min_value=3)

        # ── bookkeeping ─────────────────────────────────────────────────
        original_count = g.DomainSize(geometry, component="CURVE").o.point_count
        total_count    = original_count * n_samples

        # Resample the input curve so we get N× more points
        resampled = g.ResampleCurve(geometry, mode="COUNT", count=total_count)

        # ── per-output-point indexing ────────────────────────────────────
        # global_idx  = index of the resampled point  (0 … total-1)
        # parent_idx  = which original cell it belongs to
        # sub_idx     = position inside that cell     (0 … N-1)
        global_idx = g.Index()

        parent_idx = global_idx // n_samples   # IntegerMath.divide_floor
        sub_idx    = global_idx % n_samples    # IntegerMath.modulo

        # ── edge-padded neighbour access ─────────────────────────────────
        # Clamp helper: index clamped to [0, original_count − 1]
        def clamp(idx):
            return g.Math.maximum(0, g.Math.minimum(idx, original_count - 1))

        i_m2 = clamp(parent_idx - 2)
        i_m1 = clamp(parent_idx - 1)
        i_c  = parent_idx
        i_p1 = clamp(parent_idx + 1)
        i_p2 = clamp(parent_idx + 2)

        # ── sample the named attribute from the *original* curve ─────────
        attr = g.NamedAttribute(attr_name, data_type="FLOAT")

        a_m2 = g.SampleIndex.point.float(geometry, attr, i_m2)
        a_m1 = g.SampleIndex.point.float(geometry, attr, i_m1)
        a_c  = g.SampleIndex.point.float(geometry, attr, i_c)
        a_p1 = g.SampleIndex.point.float(geometry, attr, i_p1)
        a_p2 = g.SampleIndex.point.float(geometry, attr, i_p2)

        # ── PPM cubic interface values (no monotonicity limiters) ────────
        #  a_l =  7/12 (a_{i-1} + a_i)  − 1/12 (a_{i-2} + a_{i+1})
        #  a_r =  7/12 (a_i + a_{i+1})  − 1/12 (a_{i-1} + a_{i+2})
        a_l = (7.0 / 12.0) * (a_m1 + a_c) - (1.0 / 12.0) * (a_m2 + a_p1)
        a_r = (7.0 / 12.0) * (a_c + a_p1) - (1.0 / 12.0) * (a_m1 + a_p2)

        # ── shape coefficients ───────────────────────────────────────────
        da  = a_r - a_l
        a6  = 6.0 * a_c - 3.0 * (a_l + a_r)

        # ── evaluate parabola at sub-interval mid-point ──────────────────
        #  ξ = (sub_idx + 0.5) / N
        #  value = a_l + ξ · (da + a6 · (1 − ξ))
        xi       = (sub_idx + 0.5) / n_samples
        ppm_val  = a_l + xi * (da + a6 * (1.0 - xi))

        # ── store and output ─────────────────────────────────────────────
        result = g.StoreNamedAttribute.point.float(
            resampled, True, "ppm_value", ppm_val
        )
        result >> tree.outputs.geometry("Geometry")


# ---------------------------------------------------------------------------
# Convenience: build a one-off tree with the PPM node wired in
# ---------------------------------------------------------------------------

def build_ppm_tree(
    name: str = "PPM 1D Interpolation",
    *,
    default_attr: str = "value",
    default_n: int = 12,
) -> g.tree:
    """Return a TreeBuilder whose outputs carry the PPM-resampled curve."""
    with g.tree(name) as tree:
        geom     = tree.inputs.geometry("Curve")
        attr     = tree.inputs.string("Attribute Name", default_attr)
        n        = tree.inputs.integer("Samples Per Step", default_n, min_value=3)
        ppm_out  = PPM1D(geometry=geom, attribute_name=attr, samples_per_step=n)
        ppm_out >> tree.outputs.geometry("Output")
    return tree


# ---------------------------------------------------------------------------
# Standalone demo — creates a test tree when executed inside Blender
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_ppm_tree()
