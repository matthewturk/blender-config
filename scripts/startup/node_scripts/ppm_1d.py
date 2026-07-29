NAME = "PPM 1D Interpolation"

# Non-uniform-grid PPM (Colella & Woodward 1984), with the x-axis carried
# explicitly and an optional (runtime-toggleable) monotonicity limiter.
#
# The reconstruction math is verified independently in
# tests/ppm_reference_test.py - both the hierarchical slope/interface
# formulas below (checked against the classic uniform-grid 7/12, -1/12
# reduction, and against exact reconstruction of a cubic polynomial's cell
# averages on a genuinely non-uniform grid) and the monotonicity limiter
# (checked for exact flattening of a true local-extremum cell, and for
# substantially - not perfectly, see _apply_limiter's docstring - reducing
# overshoot elsewhere) - before being translated into this node graph.
#
# Density is "Samples Per Unit" (of x), not a fixed count per original
# point, combined with explicit "X Min"/"X Max" bounds: total output count
# is round(samples_per_unit * (X Max - X Min)), fixed regardless of the
# actual data's own x-range, so different inputs (e.g. different country
# pairs with different year coverage) always produce the same number of
# outputs. The output points are generated directly, evenly spaced across
# [X Min, X Max] (via a Curve Line + Resample by Count) - NOT derived from
# resampling the data itself. An internal, x-positioned linear (POLY) proxy
# curve of the original data is then queried at each output point's factor
# via Sample Curve, which interpolates "which original interval, how far
# into it" at any arbitrary position, regardless of the data's own point
# count or how many output samples were requested. If X Min/X Max extend
# past the data's actual range, the factor is clamped to [0, 1] by hand
# (Sample Curve doesn't clamp automatically - confirmed against nodebpy's
# source, unlike Sample Index which has an explicit clamp option), which
# extrapolates using the boundary's own value - the same "flat" treatment
# already used for boundary cells below.
#
# Rebuilding this group (rerunning this script) still clears and recreates
# its whole interface, same as it always has - nodebpy's tree-builder
# socket-creation calls aren't idempotent against an already-built tree, so
# there isn't a clean way to preserve outer-tree links across a rebuild
# here the way csv_menu_select.py does (that script uses raw bpy interface
# calls throughout instead of nodebpy's tree builder, which is what makes
# its reuse-safety possible). Reconnect anything linked to this group's
# sockets after a rebuild.


def _generalized_slope(a_jm1, a_j, a_jp1, h_jm1, h_j, h_jp1):
    """Non-uniform-grid "average slope" in cell j (Colella & Woodward 1984)."""
    term1 = (2.0 * h_jm1 + h_j) / (h_jp1 + h_j) * (a_jp1 - a_j)
    term2 = (h_j + 2.0 * h_jp1) / (h_jm1 + h_j) * (a_j - a_jm1)
    return (h_j / (h_jm1 + h_j + h_jp1)) * (term1 + term2)


def _interface_value(a_jm1, a_j, a_jp1, a_jp2, h_jm1, h_j, h_jp1, h_jp2):
    """a_{j+1/2}: the face value between cell j and cell j+1, for cells of
    arbitrary (non-uniform) width. Reduces exactly to the familiar uniform-
    grid 7/12, -1/12 combination when all four widths are equal.
    """
    delta_j = _generalized_slope(a_jm1, a_j, a_jp1, h_jm1, h_j, h_jp1)
    delta_jp1 = _generalized_slope(a_j, a_jp1, a_jp2, h_j, h_jp1, h_jp2)

    base = a_j + (h_j / (h_j + h_jp1)) * (a_jp1 - a_j)

    denom = h_jm1 + h_j + h_jp1 + h_jp2
    bracket = (
        (2.0 * h_jp1 * h_j / (h_j + h_jp1))
        * ((h_jm1 + h_j) / (2.0 * h_j + h_jp1) - (h_jp2 + h_jp1) / (2.0 * h_jp1 + h_j))
        * (a_jp1 - a_j)
        - h_j * (h_jm1 + h_j) / (2.0 * h_j + h_jp1) * delta_jp1
        + h_jp1 * (h_jp1 + h_jp2) / (2.0 * h_jp1 + h_j) * delta_j
    )
    return base + bracket / denom


def _apply_limiter(a_c, a_l, a_r):
    """Colella & Woodward (1984) eq. 1.10 monotonicity limiter.

    Flattens a_l/a_r to a_c exactly when a_c is itself a local extremum
    relative to them; otherwise nudges whichever face value would let the
    parabola overshoot past a_c. Substantially reduces, but - for an
    isolated single-point spike specifically - does not perfectly
    eliminate, overshoot in the cells flanking the extremum; that residual
    is a documented property of this (the original, simplest) limiter, not
    a bug. See tests/ppm_reference_test.py.
    """
    is_extremum = (a_r - a_c) * (a_c - a_l) <= 0.0

    da = a_r - a_l
    mid_offset = a_c - 0.5 * (a_l + a_r)
    overshoots_left = da * mid_offset > (da * da) / 6.0
    overshoots_right = -(da * da) / 6.0 > da * mid_offset

    a_l_nudged = overshoots_left.switch.float(a_l, 3.0 * a_c - 2.0 * a_r)
    a_r_nudged = overshoots_right.switch.float(a_r, 3.0 * a_c - 2.0 * a_l)

    final_l = is_extremum.switch.float(a_l_nudged, a_c)
    final_r = is_extremum.switch.float(a_r_nudged, a_c)
    return final_l, final_r


def build(tree, params):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Curve")
    attr_name = tree.inputs.string("Attribute Name", "value")
    x_attr_name = tree.inputs.string("X Attribute Name", "x")
    samples_per_unit = tree.inputs.float("Samples Per Unit", 4.0, min_value=0.01)
    x_min = tree.inputs.float("X Min", 0.0)
    x_max = tree.inputs.float("X Max", 1.0)
    use_limiter = tree.inputs.boolean("Use Limiter", True)

    original_count = g.DomainSize(geometry, component="CURVE").o.point_count

    # ── auxiliary linear (POLY) curve positioned by x - an internal
    # scaffold only, never part of the output, and never resampled itself:
    # Sample Curve (below) interpolates its "_orig_index" attribute at any
    # arbitrary factor regardless of how many points this curve has. Arc
    # length between its points equals the true x spacing exactly (POLY =
    # straight segments), so a factor of 0..1 along it maps linearly onto
    # the data's own x range. ──
    aux = g.SetSplineType(geometry, spline_type="POLY")
    aux = g.SetPosition(
        aux, position=g.CombineXYZ(x=g.NamedAttribute.float(x_attr_name), y=0.0, z=0.0)
    )
    aux = g.StoreNamedAttribute.point.float(aux, name="_orig_index", value=g.Index())

    x_stats = g.AttributeStatistic.point.float(
        geometry, attribute=g.NamedAttribute.float(x_attr_name)
    )
    data_x_min = x_stats.o.min
    data_x_max = x_stats.o.max
    # Guards against a degenerate 0-width data range (e.g. a single point)
    # producing a 0/0 factor below.
    data_x_span = g.Math.maximum(data_x_max - data_x_min, 1e-8)

    # ── output points: generated directly, evenly spaced across the
    # explicit [X Min, X Max] bounds - independent of the data's own range,
    # so the output count is always exactly this, regardless of input. ──
    total_samples = g.Math.maximum(1, g.Math.round(samples_per_unit * (x_max - x_min)))
    output_line = g.CurveLine.points(
        start=g.CombineXYZ(x=x_min, y=0.0, z=0.0),
        end=g.CombineXYZ(x=x_max, y=0.0, z=0.0),
    )
    output_points = g.ResampleCurve(output_line, mode="Count", count=total_samples)

    sample_x = g.SeparateXYZ(g.Position()).o.x  # evaluated on `output_points`
    factor_raw = (sample_x - data_x_min) / data_x_span
    factor = g.Math.maximum(0.0, g.Math.minimum(factor_raw, 1.0))

    continuous_idx = g.SampleCurve.factor.float(
        curves=aux, value=g.NamedAttribute.float("_orig_index"), factor=factor
    ).o.value
    xi = g.Math.fraction(continuous_idx)
    parent_idx = g.Math.floor(continuous_idx)

    def clamp(idx):
        return g.Math.maximum(0, g.Math.minimum(idx, original_count - 1))

    i_m2 = clamp(parent_idx - 2)
    i_m1 = clamp(parent_idx - 1)
    i_c = clamp(parent_idx)
    i_p1 = clamp(parent_idx + 1)
    i_p2 = clamp(parent_idx + 2)
    i_p3 = clamp(parent_idx + 3)

    a_m2 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(attr_name), i_m2)
    a_m1 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(attr_name), i_m1)
    a_c = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(attr_name), i_c)
    a_p1 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(attr_name), i_p1)
    a_p2 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(attr_name), i_p2)

    x_m2 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_m2)
    x_m1 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_m1)
    x_c = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_c)
    x_p1 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_p1)
    x_p2 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_p2)
    x_p3 = g.SampleIndex.point.float(geometry, g.NamedAttribute.float(x_attr_name), i_p3)

    h_im2 = x_m1 - x_m2
    h_im1 = x_c - x_m1
    h_i = x_p1 - x_c
    h_ip1 = x_p2 - x_p1
    h_ip2 = x_p3 - x_p2

    # The non-uniform interface formula divides by cell widths; near either
    # end of the curve, index-clamping makes two neighboring x-samples
    # collide, so a width can be exactly zero there - a genuine division by
    # zero (verified against the pure-Python reference: it raises
    # ZeroDivisionError for the boundary cells specifically). Geometry Nodes
    # won't crash on that - it just produces NaN/Inf - so cells within reach
    # of the boundary fall back to the plain uniform-grid formula instead
    # (7/12, -1/12 - a fixed combination that never divides by a width at
    # all, so it's immune to this). "Within reach" means the full 6-point
    # x stencil (offsets -2..+3 from parent_idx) stays entirely in range;
    # verified numerically to produce only finite values everywhere,
    # including on curves too short for the safe range to exist at all.
    is_safe = (parent_idx >= 2) & (parent_idx <= original_count - 4)

    a_l_uniform = (7.0 / 12.0) * (a_m1 + a_c) - (1.0 / 12.0) * (a_m2 + a_p1)
    a_r_uniform = (7.0 / 12.0) * (a_c + a_p1) - (1.0 / 12.0) * (a_m1 + a_p2)

    a_l_nonuniform = _interface_value(a_m2, a_m1, a_c, a_p1, h_im2, h_im1, h_i, h_ip1)
    a_r_nonuniform = _interface_value(a_m1, a_c, a_p1, a_p2, h_im1, h_i, h_ip1, h_ip2)

    a_l_raw = is_safe.switch.float(a_l_uniform, a_l_nonuniform)
    a_r_raw = is_safe.switch.float(a_r_uniform, a_r_nonuniform)

    a_l_limited, a_r_limited = _apply_limiter(a_c, a_l_raw, a_r_raw)
    a_l = use_limiter.switch.float(a_l_raw, a_l_limited)
    a_r = use_limiter.switch.float(a_r_raw, a_r_limited)

    da = a_r - a_l
    a6 = 6.0 * a_c - 3.0 * (a_l + a_r)
    ppm_val = a_l + xi * (da + a6 * (1.0 - xi))

    # sample_x is already output_points' own position.x by construction
    # (evenly spaced across [X Min, X Max]) - no need to re-derive it.
    result = g.StoreNamedAttribute.point.float(output_points, name="ppm_value", value=ppm_val)
    result = g.StoreNamedAttribute.point.float(result, name="x", value=sample_x)

    result >> tree.outputs.geometry("Output")
