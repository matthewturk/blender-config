import os
import csv

import bpy
import numpy as np
import databpy as db

# Exports every point-domain attribute of a single-spline Curves object to a
# CSV: one row per point ("element"), one column per attribute
# (multi-component attributes like a FLOAT_VECTOR position get split into
# "name_0"/"name_1"/... columns so the output stays a flat table).
#
# Reads the object's *evaluated* geometry via databpy.GeometrySet, not its
# base obj.data - so this works both for a plain Curves object (built by e.g.
# hdf5_to_curves.py) AND for something like a Mesh/Cube object whose
# Geometry Nodes modifier converts it to a curve (e.g. via a Mesh to Curve
# node). obj.data (even evaluated via obj.evaluated_get(depsgraph).data)
# stays locked to the object's base type - Geometry Nodes can output several
# components at once (mesh, curves, points, instances) side by side, and
# they're only reachable through evaluated_object.evaluated_geometry(),
# which is what GeometrySet wraps.
#
# Restricted to single-spline curves on purpose: with more than one spline,
# "one row per point" stops being an unambiguous table (which curve does a
# row belong to?), and legacy bpy.types.Curve output isn't supported at all -
# only the new Curves type has the generic per-point attribute system this
# reads through.
#
# STRING attributes are read by hand (per-item .value, decoded), not through
# databpy - the installed databpy version isn't consistent about STRING
# attribute support across versions (see hdf5_to_curves.py for the same
# issue on the write side).

PARAMS = {
    "source_object": {
        "type": "OBJECT",
        "default": None,
        "name": "Source Object",
        "description": "Object whose evaluated (post-modifier) geometry is a single-spline Curves - e.g. a plain Curves object, or a mesh with a Geometry Nodes modifier that converts it to a curve",
    },
    "csv_path": {
        "type": "FILE_PATH",
        "default": "//curve_export.csv",
        "name": "CSV File",
        "description": "Where to write the CSV",
    },
    "attributes": {
        "type": "STRING",
        "default": "",
        "name": "Attributes",
        "description": "Comma-separated attribute names to export. Leave blank to export every non-hidden point attribute",
    },
}


def _evaluated_geometry_set(obj, context):
    """The evaluated bpy.types.GeometrySet for `obj` (mesh/curves/pointcloud/
    instances components, side by side) - core Blender API, called directly
    rather than through databpy.GeometrySet, since that wrapper doesn't exist
    in every installed databpy version (0.6.2, seen elsewhere in this Blender
    install, predates it - it has no geometry.py at all).
    """
    depsgraph = context.evaluated_depsgraph_get()
    evaluated_object = depsgraph.id_eval_get(obj)
    return evaluated_object.evaluated_geometry()


def _present_components(geometry_set):
    present = []
    if geometry_set.mesh is not None:
        present.append("MESH")
    if geometry_set.curves is not None:
        present.append("CURVES")
    if geometry_set.pointcloud is not None:
        present.append("POINTCLOUD")
    return present


def _read_column(attr):
    """Read one point-domain attribute as a numpy array (1D or 2D)."""
    if attr.data_type == "STRING":
        return np.array([
            item.value.decode("utf-8") if isinstance(item.value, bytes) else str(item.value)
            for item in attr.data
        ])
    return db.Attribute(attr).as_array()


def execute(context, params):
    obj = params["source_object"]
    csv_path = bpy.path.abspath(params["csv_path"])
    attributes_spec = params["attributes"].strip()

    if obj is None:
        raise ValueError("No source object given")

    geometry_set = _evaluated_geometry_set(obj, context)
    data = geometry_set.curves

    if data is None:
        present = _present_components(geometry_set)
        raise TypeError(
            f"'{obj.name}'s evaluated geometry has no Curves component "
            f"(components present: {present or 'none'}). If this is meant to "
            "become a curve via Geometry Nodes (e.g. a Mesh to Curve node), "
            "double check the modifier's final output actually includes curve "
            "geometry - legacy bpy.types.Curve output isn't supported either, "
            "only the new Curves type."
        )

    if len(data.curves) != 1:
        raise ValueError(
            f"'{obj.name}' has {len(data.curves)} splines; this only works on "
            "single-spline curves"
        )

    all_names = sorted(name for name in data.attributes.keys() if not name.startswith("."))
    attr_names = all_names
    if attributes_spec:
        requested = [a.strip() for a in attributes_spec.split(",") if a.strip()]
        missing = [a for a in requested if a not in all_names]
        if missing:
            raise ValueError(f"Requested attribute(s) not found: {missing}. Available: {all_names}")
        attr_names = requested

    point_attrs = {
        name: data.attributes[name]
        for name in attr_names
        if data.attributes[name].domain == "POINT"
    }
    if not point_attrs:
        raise ValueError("No POINT-domain attributes found to export")

    columns = {}
    for name, attr in point_attrs.items():
        arr = _read_column(attr)
        if arr.ndim == 1:
            columns[name] = arr
        else:
            for i in range(arr.shape[1]):
                columns[f"{name}_{i}"] = arr[:, i]

    n_points = len(next(iter(columns.values())))

    dirname = os.path.dirname(csv_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(list(columns.keys()))
        for i in range(n_points):
            writer.writerow([columns[col][i] for col in columns])

    print(f"Wrote {n_points} rows, {len(columns)} columns to '{csv_path}' from '{obj.name}'")
    return {"FINISHED"}
