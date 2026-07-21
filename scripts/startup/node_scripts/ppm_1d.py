NAME = "PPM 1D Interpolation"


def build(tree, params):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Curve")
    attr_name = tree.inputs.string("Attribute Name", "value")
    n_samples = tree.inputs.integer("Samples Per Step", 12, min_value=3)

    original_count = g.DomainSize(geometry, component="CURVE").o.point_count
    total_count = original_count * n_samples

    resampled = g.ResampleCurve(geometry, mode="Count", count=total_count)

    global_idx = g.Index()
    parent_idx = global_idx // n_samples
    sub_idx = global_idx % n_samples

    def clamp(idx):
        return g.Math.maximum(0, g.Math.minimum(idx, original_count - 1))

    i_m2 = clamp(parent_idx - 2)
    i_m1 = clamp(parent_idx - 1)
    i_c = parent_idx
    i_p1 = clamp(parent_idx + 1)
    i_p2 = clamp(parent_idx + 2)

    a_m2 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_m2)
    a_m1 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_m1)
    a_c = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_c)
    a_p1 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_p1)
    a_p2 = g.SampleIndex.point.float(geometry, g.NamedAttribute(attr_name), i_p2)

    a_l = (7.0 / 12.0) * (a_m1 + a_c) - (1.0 / 12.0) * (a_m2 + a_p1)
    a_r = (7.0 / 12.0) * (a_c + a_p1) - (1.0 / 12.0) * (a_m1 + a_p2)

    da = a_r - a_l
    a6 = 6.0 * a_c - 3.0 * (a_l + a_r)

    xi = (sub_idx + 0.5) / n_samples
    ppm_val = a_l + xi * (da + a6 * (1.0 - xi))

    (
        resampled
        >> g.StoreNamedAttribute.point.float(name="ppm_value", value=ppm_val)
        >> tree.outputs.geometry("Output")
    )
