import os
import glob
import struct
import importlib.util

import bpy
import numpy as np

# Imports a directory of uncompressed Houdini BGEO (v5) point-cache files as
# ONE animated point-cloud object: each file becomes one animation frame
# (sorted by filename), animated via Blender shape keys (see
# _frame_stack_animation.build_animated_point_object).
#
# The binary parsing below (bgeo_header, read_struct_format, dtype_map,
# read_attribute_header, read_particles) is ported essentially as-is from
# blendyt's read_load_bgeo.py - a from-scratch, already-correct reader for
# this format: a fixed header, then a table of per-point-attribute headers
# (name/size/type), then the raw point data as one big big-endian structured
# array. Every point always carries particle_position_x/y/z plus a 4th
# "unknown" float (Houdini's homogeneous w component) and whatever custom
# per-point attributes that file's header declares.
#
# Only position is animated across frames (that's what shape keys carry
# here); any other per-point attributes found in the first frame are stored
# as static POINT attributes - see the note printed at the end of a run
# that finds any.

PARAMS = {
    "directory_path": {
        "type": "DIR_PATH",
        "default": "",
        "name": "Directory",
        "description": "Directory containing one or more .bgeo files - each file becomes one animation frame, sorted by filename",
    },
    "file_pattern": {
        "type": "STRING",
        "default": "*.bgeo",
        "name": "File Pattern",
        "description": "Glob pattern (relative to Directory) matching the per-frame .bgeo files",
    },
    "object_name": {
        "type": "STRING",
        "default": "BGEO_Particles",
        "name": "Object Name",
        "description": "Name for the created point-cloud object and data-block",
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection to link the new object into (defaults to scene collection)",
    },
}


def _load_sibling(module_name):
    """Load a module from scripts/startup/ (one directory up from
    user_scripts/) by file path - user_scripts/ files are loaded standalone
    by dynamic_script_runner.py (no parent package context), so a package-
    relative import doesn't work here. Same pattern as
    constant_mass_emission_times.py's _load_sibling.
    """
    path = os.path.join(os.path.dirname(__file__), "..", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_frame_stack_animation = _load_sibling("_frame_stack_animation")


# ── BGEO (v5, uncompressed) parsing - ported from read_load_bgeo.py ────────

bgeo_header = (
    ("version", "i"),
    ("npoints", "i"),
    ("nprims", "i"),
    ("npointgroups", "i"),
    ("nprimgroups", "i"),
    ("npointattrib", "i"),
    ("nvertexattrib", "i"),
    ("nprimattrib", "i"),
    ("nattrib", "i"),
)


def read_struct_format(f, fmt):
    fmt = f">{fmt}"  # Ensure big-endian format
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise ValueError("Unexpected end of file while reading struct")
    return struct.unpack(fmt, data)


dtype_map = {0: "float32", 1: "int32", 3: "3*float32"}


def read_attribute_header(f):
    name_length = read_struct_format(f, "h")[0]
    name = f.read(name_length).decode("ascii")
    size = read_struct_format(f, "h")[0]
    attr_type = read_struct_format(f, "i")[0]
    f.read(4 * size)  # Skip default values
    return name, dtype_map[attr_type]


def read_particles(fn: str):
    header = {}
    with open(fn, "rb") as f:
        magic_format = "5c"
        data = f.read(struct.calcsize(magic_format))
        magic = struct.unpack(magic_format, data)
        assert magic == (b"B", b"g", b"e", b"o", b"V"), "Not a valid BGEO file"
        attributes = []
        for name, dtype in bgeo_header:
            (header[name],) = read_struct_format(f, dtype)
        for i in range(header["npointattrib"]):
            attributes.append(read_attribute_header(f))
        new_dtype = np.dtype(
            [
                ("particle_position_x", "f4"),
                ("particle_position_y", "f4"),
                ("particle_position_z", "f4"),
                ("unknown", "f4"),
            ]
            + attributes
        )
        points = np.fromfile(f, dtype=new_dtype, count=header["npoints"]).byteswap()
    return points


# Fields present on every frame that aren't a "real" custom per-point
# attribute - position is handled/animated separately, and "unknown" is
# Houdini's homogeneous w filler value, not user data.
_NON_ATTRIBUTE_FIELDS = (
    "particle_position_x",
    "particle_position_y",
    "particle_position_z",
    "unknown",
)


def execute(context, params):
    directory_path = bpy.path.abspath(params["directory_path"])
    file_pattern = params["file_pattern"]
    object_name = params["object_name"]
    target_collection = params["target_collection"] or context.scene.collection

    pattern_path = os.path.join(directory_path, file_pattern)
    filenames = sorted(glob.glob(pattern_path))
    if not filenames:
        raise ValueError(f"No files matching '{pattern_path}' found")

    # Simple periodic progress feedback - parsing can run over many files
    # with no other output until the final summary print, so report every
    # ~5% (or every file, if there are fewer than 20).
    n_files = len(filenames)
    progress_step = max(1, n_files // 20)

    frames = []
    n_points = None
    extra_attr_names = []
    first_frame_extra_attrs = {}

    for i, fn in enumerate(filenames):
        points = read_particles(fn)
        n = points.shape[0]

        if n_points is None:
            n_points = n
            extra_attr_names = [
                field for field in points.dtype.names if field not in _NON_ATTRIBUTE_FIELDS
            ]
            for attr_name in extra_attr_names:
                first_frame_extra_attrs[attr_name] = np.asarray(points[attr_name])
        elif n != n_points:
            raise ValueError(
                f"'{fn}' has {n} points, but the first frame ('{filenames[0]}') "
                f"has {n_points} - every frame must have the same point count "
                "to animate via shape keys"
            )

        positions = np.stack(
            [
                points["particle_position_x"],
                points["particle_position_y"],
                points["particle_position_z"],
            ],
            axis=-1,
        ).astype(np.float32)
        frames.append(positions)

        if (i + 1) % progress_step == 0 or (i + 1) == n_files:
            print(f"Parsed {i + 1}/{n_files} BGEO files ({100 * (i + 1) / n_files:.0f}%)")

    if extra_attr_names:
        print(
            f"Note: point attribute(s) {extra_attr_names} are only kept from "
            f"the first frame ('{filenames[0]}') and stored as static "
            "(non-animated) attributes - only position is currently animated "
            "across frames"
        )

    obj = _frame_stack_animation.build_animated_point_object(
        object_name,
        frames,
        target_collection,
        static_point_attrs=first_frame_extra_attrs or None,
    )

    print(
        f"Built '{obj.name}': {n_files} frames, {n_points} points, "
        f"attributes={extra_attr_names}"
    )
    return {"FINISHED"}
