NAME = "Attribute Curve Map"

PARAMS = {
    "source_object": {
        "type": "OBJECT",
        "default": None,
        "name": "Source Curve",
        "description": "Curve object to sample at build time",
    },
    "attr_name": {
        "type": "STRING",
        "default": "",
        "name": "Attribute Name",
        "description": "Point attribute to read values from (leave empty for Y coordinates)",
    },
}


def build(tree, params):
    from nodebpy import geometry as g
    import bpy
    import numpy as np

    geometry = tree.inputs.geometry("Geometry")

    source_obj = params.get("source_object")
    attr_name = params.get("attr_name", "")

    values = []
    if source_obj is not None and source_obj.type == "CURVE":
        depgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = source_obj.evaluated_get(depgraph)
        curve_data = evaluated.data

        # Read from curve_data (the evaluated, post-modifier data), not
        # source_obj.data (pre-modifier) - matching the fallback branch
        # below, which already samples curve_data.splines.
        if attr_name and curve_data.attributes.get(attr_name):
            attr = curve_data.attributes[attr_name]
            if attr.domain == "POINT":
                values = [attr.data[i].value for i in range(len(attr.data))]
            else:
                print(
                    f"[attribute_curve_map] Attribute '{attr_name}' on "
                    f"'{source_obj.name}' is domain {attr.domain}, not POINT - "
                    f"ignoring it (no values will be sampled from it)"
                )
        else:
            if attr_name:
                print(
                    f"[attribute_curve_map] Attribute '{attr_name}' not found on "
                    f"'{source_obj.name}' (evaluated) - falling back to Y coordinates"
                )
            for spline in curve_data.splines:
                if spline.type == "BEZIER":
                    for pt in spline.bezier_points:
                        values.append(pt.co.y)
                elif spline.type in {"POLY", "NURBS"}:
                    for pt in spline.points:
                        values.append(pt.co.y)

    if not values:
        tree.outputs.geometry("Output") >> geometry
        return

    values_arr = np.asarray(values, dtype=float)
    n = len(values_arr)

    xs = np.linspace(0.0, 1.0, n)
    v_min = float(values_arr.min())
    v_max = float(values_arr.max())
    v_range = v_max - v_min if v_max != v_min else 1.0

    float_curve = tree.nodes.new("ShaderNodeFloatCurve")
    float_curve.label = attr_name or "Curve"

    mapping = float_curve.mapping
    curve = mapping.curves[0]
    points = curve.points

    while len(points) > 2:
        points.remove(points[0])
    points[0].location = (-10.0, -10.0)
    points[1].location = (-20.0, -20.0)

    for x, v in zip(xs, values_arr):
        norm_y = (v - v_min) / v_range
        pt = points.new(float(x), float(norm_y))
        pt.handle_type = "AUTO"

    points.remove(points[0])
    points.remove(points[0])
    mapping.update()

    # Geometry itself has no "value" to remap through a Float Curve - only
    # per-point/attribute VALUES do, and this node group's only runtime data
    # channel is Geometry (there's no separate scalar in/out socket to carry
    # a remapped value). So Geometry passes straight through unchanged, same
    # as the no-data fallback above; `float_curve` is built purely as a
    # standalone, visually-editable LUT baked from source_obj's sampled
    # values (Y coordinates, or `attr_name`'s POINT values), left unconnected
    # for you to wire by hand to whatever scalar you actually want remapped
    # (e.g. a Sample Curve factor, a Map Range, ...) in the node editor.
    tree.outputs.geometry("Output") >> geometry
