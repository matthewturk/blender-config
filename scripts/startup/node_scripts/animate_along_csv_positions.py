NAME = "Animate Along CSV Positions"

# Ported from /tmp/blendyt_review/grid_creator.py's `positions_from_csv` +
# `animated_orbit` (blendyt's `nodetree_script` DSL), combined into ONE
# nodebpy tree matching `animated_orbit`'s end-to-end behaviour: read
# per-point x/y/z attributes off the input geometry (e.g. a mesh built by
# this repo's CSV-to-attribute pipeline - see csv_menu_select.py /
# assign_csv_country_attributes.py), turn them into points, string those
# points into one curve (preserving the input mesh's existing point order as
# the curve's along-length order - this is not re-sorted, same as the
# original), and sample a position along that curve driven by the current
# frame, then move a marker sphere to that position each frame.


def build(tree, params):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Geometry")
    animation_scale = tree.inputs.float(
        "Animation Scale",
        default_value=10.0,  # matches the original's hardcoded `animation_scale=10.0`
        description="Number of frames the full CSV position history spans",
    )
    # UVSphere's own bare-call default radius is 1.0 (nodebpy/nodes/geometry/
    # geometry.py UVSphere.__init__ radius: InputFloat = 1.0), matching the
    # original's `gs.uv_sphere().mesh` bare call.
    instance_radius = tree.inputs.float(
        "Instance Radius",
        default_value=1.0,
        description="Radius of the sphere marking the sampled position",
    )

    x = g.NamedAttribute(name="x").o.attribute
    y = g.NamedAttribute(name="y").o.attribute
    z = g.NamedAttribute(name="z").o.attribute
    combined = g.CombineXYZ(x=x, y=y, z=z)

    points = g.SetPosition(
        geometry=g.MeshToPoints(mesh=geometry),
        position=combined.o.vector,
    )
    curves = g.PointsToCurves(points=points.o.geometry)

    # The original used `gs.scene_time().seconds`, not `.frame` - kept as-is
    # (SceneTime exposes both `o.seconds` and `o.frame`; no reason found to
    # prefer frame over the original's choice of seconds).
    mapped = g.MapRange(
        value=g.SceneTime().o.seconds,
        from_min=0.0,
        from_max=animation_scale,
        to_min=0.0,
        to_max=1.0,
        # Judgment call: nodebpy's own MapRange default is clamp=False, but
        # Sample Curve's Factor is meant to stay within [0, 1] - without
        # clamping, seconds elapsed beyond `animation_scale` would push the
        # factor past 1.0 (or negative before the animation starts). Clamping
        # holds the marker at the curve's start/end instead of extrapolating,
        # which matches the intent of "spans `animation_scale` frames".
        clamp=True,
    )

    sampled = g.SampleCurve(curves=curves.o.curves, factor=mapped.o.result)

    sphere = g.UVSphere(radius=instance_radius)
    transformed = g.TransformGeometry(
        geometry=sphere.o.mesh, translation=sampled.o.position
    )

    tree.outputs.geometry("Output") >> transformed.o.geometry

    # Addition beyond the original: the raw sampled position, so a user can
    # wire something other than the hardcoded marker sphere to the same
    # animated position (e.g. InstanceOnPoints with their own instance
    # geometry) without editing this tree.
    tree.outputs.vector("Sampled Position") >> sampled.o.position
