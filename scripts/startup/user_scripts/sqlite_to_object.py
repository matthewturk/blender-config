import sqlite3

import bpy
import numpy as np
import pandas as pd
import databpy as db

# Runs a SQL query against a SQLite database and loads the result into a
# Blender object: one point per row, every point at (0,0,0) (position isn't
# meaningful here - this is a plain attribute table, not spatial data), and
# one point-domain attribute per result column, typed from pandas' own dtype
# inference (int/float/bool columns via databpy; string/object columns
# written by hand - see _write_string_attribute).
#
# Output is either a Mesh (one vertex per row) or a single-spline Curves
# object (one point per row, matching the convention curve_to_csv.py/
# hdf5_to_curves.py already use elsewhere in this toolchain) - your choice.

PARAMS = {
    "db_path": {
        "type": "FILE_PATH",
        "default": "//data.sqlite",
        "name": "SQLite Database",
        "description": "Path to the SQLite database file",
    },
    "query": {
        "type": "STRING",
        "default": "",
        "name": "SQL Query",
        "description": "SQL query to run; every result column becomes a point attribute",
    },
    "object_name": {
        "type": "STRING",
        "default": "SQL_Result",
        "name": "Object Name",
        "description": "Name for the created object and data-block",
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection to link the new object into (defaults to scene collection)",
    },
    "output_type": {
        "type": "ENUM",
        "default": "MESH",
        "items": [
            ("MESH", "Mesh", "Create a Mesh object, one vertex per row"),
            ("CURVES", "Curves", "Create a single-spline Curves object, one point per row"),
        ],
        "name": "Output Type",
        "description": "Which kind of object to build",
    },
}


def _write_string_attribute(obj_data, name, values, domain):
    """Write a STRING attribute by hand through bpy's attributes API.

    databpy's store_named_attribute isn't consistent about STRING support
    across installed versions (see hdf5_to_curves.py for the same issue).
    """
    attr = obj_data.attributes.get(name)
    if attr is None or attr.data_type != "STRING" or attr.domain != domain:
        if attr is not None:
            obj_data.attributes.remove(attr)
        attr = obj_data.attributes.new(name=name, type="STRING", domain=domain)
    for item, value in zip(attr.data, values):
        item.value = str(value).encode("utf-8")


def _store_column(obj, obj_data, name, series):
    if pd.api.types.is_bool_dtype(series):
        arr = series.to_numpy(dtype=bool)
        db.store_named_attribute(obj, arr, name, atype=db.AttributeTypes.BOOLEAN, domain=db.AttributeDomains.POINT)
    elif pd.api.types.is_integer_dtype(series):
        arr = series.to_numpy(dtype=np.int32)
        db.store_named_attribute(obj, arr, name, atype=db.AttributeTypes.INT, domain=db.AttributeDomains.POINT)
    elif pd.api.types.is_float_dtype(series):
        arr = series.to_numpy(dtype=np.float32)
        db.store_named_attribute(obj, arr, name, atype=db.AttributeTypes.FLOAT, domain=db.AttributeDomains.POINT)
    else:
        arr = series.astype(str).to_numpy()
        _write_string_attribute(obj_data, name, arr, domain="POINT")


def execute(context, params):
    db_path = bpy.path.abspath(params["db_path"])
    query = params["query"].strip()
    object_name = params["object_name"]
    target_collection = params["target_collection"] or context.scene.collection
    output_type = params["output_type"]

    if not query:
        raise ValueError("No SQL query given")

    conn = sqlite3.connect(db_path)
    try:
        result = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    n_rows = len(result)
    if n_rows == 0:
        raise ValueError("Query returned no rows")

    zeros = np.zeros((n_rows, 3), dtype=np.float32)

    if output_type == "MESH":
        existing_data = bpy.data.meshes.get(object_name)
        if existing_data is not None:
            bpy.data.meshes.remove(existing_data)
        obj_data = bpy.data.meshes.new(name=object_name)
        obj_data.from_pydata(zeros.tolist(), [], [])
        obj_data.update()
    else:
        existing_data = bpy.data.hair_curves.get(object_name)
        if existing_data is not None:
            bpy.data.hair_curves.remove(existing_data)
        obj_data = bpy.data.hair_curves.new(name=object_name)
        obj_data.add_curves([n_rows])

    obj = bpy.data.objects.get(object_name)
    if obj is None:
        obj = bpy.data.objects.new(object_name, obj_data)
        target_collection.objects.link(obj)
    elif obj.data != obj_data:
        obj.data = obj_data

    if output_type == "CURVES":
        db.store_named_attribute(
            obj, zeros, "position", atype=db.AttributeTypes.FLOAT_VECTOR, domain=db.AttributeDomains.POINT
        )

    for column in result.columns:
        _store_column(obj, obj_data, column, result[column])

    print(
        f"Built '{object_name}' ({output_type}): {n_rows} rows, "
        f"columns={list(result.columns)}"
    )
    return {"FINISHED"}
