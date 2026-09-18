import os
import csv
import glob
import importlib.util

import bpy
import numpy as np

# Imports a directory of per-frame CSVs as ONE animated point-cloud object:
# each file becomes one animation frame (sorted by filename), animated via
# Blender shape keys - see _frame_stack_animation.build_animated_point_object.
#
# Generalizes blendyt's halo_importer.py, which did exactly this for a
# hardcoded directory of halo-particle CSVs with fixed
# particle_position_x/y/z + particle_index columns. Here the position and
# sort columns are parameters instead.
#
# CRITICAL: point N in the resulting animation must refer to the SAME
# physical particle in every frame - a shape key's "co" array is just a flat
# list of positions with no identity of its own, so if a CSV's row order
# for the "same" particle isn't consistent across files, the animation will
# silently move the wrong particles to each other's positions. sort_column
# (e.g. a stable "particle_index" column) makes each frame's row order
# consistent before use; halo_importer.py always sorted by particle_index
# for exactly this reason.

PARAMS = {
    "directory_path": {
        "type": "DIR_PATH",
        "default": "",
        "name": "Directory",
        "description": "Directory containing one or more CSV files - each file becomes one animation frame, sorted by filename",
    },
    "file_pattern": {
        "type": "STRING",
        "default": "*.csv",
        "name": "File Pattern",
        "description": "Glob pattern (relative to Directory) matching the per-frame CSV files",
    },
    "position_columns": {
        "type": "STRING",
        "default": "x,y,z",
        "name": "Position Columns",
        "description": "Comma-separated names of the 3 columns providing point x,y,z positions, resolved within each frame's CSV",
    },
    "sort_column": {
        "type": "STRING",
        "default": "",
        "name": "Sort Column",
        "description": (
            "Column to sort each frame's rows by before use, so point N means "
            "the same particle in every frame - e.g. 'particle_index'. "
            "Required for correct animation if row order isn't already "
            "guaranteed consistent across files"
        ),
    },
    "object_name": {
        "type": "STRING",
        "default": "Frame_Stack_Particles",
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


def _sort_key(raw):
    """Numeric-first sort key: numeric-looking values sort as numbers, other
    values fall back to string order - tagged as (0, ...)/(1, ...) so the two
    kinds never get compared to each other directly (which would raise a
    TypeError). Same tagging trick as _collection_to_lists_shared.natural_
    sort_key, adapted for a whole-value (not chunked) sort key.
    """
    try:
        return (0, float(raw))
    except ValueError:
        return (1, raw)


def _resolve_positions(rows, names, fn):
    """Build an (len(rows), 3) position array from `rows` (a CSV file's
    parsed DictReader rows) - mirrors hdf5_to_curves.py's _resolve_positions,
    adapted from HDF5-dataset-lookup to CSV-column-lookup: `names` must name
    exactly the 3 scalar columns holding x, y, z (unlike the HDF5 case, a
    single CSV column can't hold a ready-made (N, 3) vector, so there's no
    single-name form here).
    """
    for name in names:
        if name not in rows[0]:
            raise ValueError(
                f"Position column '{name}' not found in '{fn}'. Available: {list(rows[0].keys())}"
            )
    return np.array([[float(row[n]) for n in names] for row in rows], dtype=np.float32)


def execute(context, params):
    directory_path = bpy.path.abspath(params["directory_path"])
    file_pattern = params["file_pattern"]
    position_columns = params["position_columns"]
    sort_column = params["sort_column"].strip()
    object_name = params["object_name"]
    target_collection = params["target_collection"] or context.scene.collection

    names = [c.strip() for c in position_columns.split(",") if c.strip()]
    if len(names) != 3:
        raise ValueError(
            f"position_columns must name exactly 3 columns (x, y, z), got "
            f"{len(names)}: {position_columns!r}"
        )

    pattern_path = os.path.join(directory_path, file_pattern)
    filenames = sorted(glob.glob(pattern_path))
    if not filenames:
        raise ValueError(f"No files matching '{pattern_path}' found")

    if not sort_column:
        print(
            "Warning: no sort_column given - each frame's CSV rows are used "
            "in file order as-is. Point N in the resulting animation must be "
            "the SAME physical particle in every frame; if the CSVs' row "
            "order isn't already guaranteed identical across files, the "
            "shape-key animation will silently move the wrong particles to "
            "each other's positions. Set sort_column (e.g. 'particle_index') "
            "to make this safe."
        )

    # Simple periodic progress feedback - parsing can run over many files
    # with no other output until the final summary print, so report every
    # ~5% (or every file, if there are fewer than 20).
    n_files = len(filenames)
    progress_step = max(1, n_files // 20)

    frames = []
    n_points = None

    for i, fn in enumerate(filenames):
        with open(fn, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise ValueError(f"No rows found in '{fn}'")

        if sort_column:
            if sort_column not in rows[0]:
                raise ValueError(
                    f"sort_column '{sort_column}' not found in '{fn}'. "
                    f"Available: {list(rows[0].keys())}"
                )
            rows.sort(key=lambda row: _sort_key(row[sort_column]))

        positions = _resolve_positions(rows, names, fn)

        if n_points is None:
            n_points = positions.shape[0]
        elif positions.shape[0] != n_points:
            raise ValueError(
                f"'{fn}' has {positions.shape[0]} rows, but the first frame "
                f"('{filenames[0]}') has {n_points} - every frame must have "
                "the same point count to animate via shape keys"
            )

        frames.append(positions)

        if (i + 1) % progress_step == 0 or (i + 1) == n_files:
            print(f"Parsed {i + 1}/{n_files} CSV files ({100 * (i + 1) / n_files:.0f}%)")

    obj = _frame_stack_animation.build_animated_point_object(
        object_name, frames, target_collection
    )

    print(f"Built '{obj.name}': {n_files} frames, {n_points} points")
    return {"FINISHED"}
