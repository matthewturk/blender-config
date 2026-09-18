#!/usr/bin/env python3
"""Command-line GeoJSON -> mesh-file exporter, using this repo's own
"Import GeoJSON Wireframes" operator (scripts/startup/country_wireframes.py)
- the exact same mechanism the "Import > GeoJSON Wireframes" panel button
runs, just driven headlessly instead of through the UI.

Run with this repo's own `uv`-managed environment (bpy is a real project
dependency here - `uv add bpy` was run directly against this repo, and the
combination of bpy + every other dependency this repo already has was
verified to resolve and import cleanly together, no splitting into
separate environments needed):

    uv run python cli/geojson_export.py

This can also be run under a full Blender install's own bundled Python or
via `blender --background -P cli/geojson_export.py` if you'd rather use a
real Blender application than the standalone pip `bpy` - see
cli/HEADLESS.md for the tradeoffs (mainly: version match against your
real Blender install, and whether `bmesh` is available - not needed by
anything in this repo's scripts as of this fix, so it no longer matters
either way).

Configuration - there is no command-line interface
----------------------------------------------------
This deliberately takes NO command-line arguments. `blender --background
-P script.py <args>` does not pass `<args>` through to the script the way
you'd expect - Blender's own argument parser consumes plain positional
arguments as its own (e.g. as a .blend file to open, or in this case
choked on `-P` itself when this script tried to argparse Blender's full
original argv). Getting this right needs Blender's own `--` convention
(`-P script.py -- <args>`) every single time, which is exactly the kind of
friction this tool exists to remove - so instead, everything is read from
a config file.

Looks for `geojson_export.json` in the CURRENT WORKING DIRECTORY (wherever
you launched Blender/python from - not this script's own directory). If
it doesn't exist, one is written with placeholder values and the script
exits so you can fill it in - re-run the exact same command once it's
edited.

Config fields
-------------
inputs        (required) A path, or list of paths, to .geojson files.
output        Exact output file path - only valid with exactly one entry
              in `inputs`. Leave null to use output_dir instead.
output_dir    Directory to write outputs into. Leave null to write each
              output alongside its input file.
format        "abc" (Alembic) or "stl".
output_mode   "curve" (default) or "mesh" - see below, "mesh" is kept
              available but doesn't actually preserve border-line
              connectivity through either export format.
bevel_depth   Only applied when output_mode is "curve" - tube radius in
              scene units. 0 (default) means no thickness.

Why "curve" is the default, and "mesh" is basically a trap - VERIFIED,
not guessed, by round-tripping real exports back into bpy
-------------------------------------------------------------------------
The panel's own default (output_mode CURVE, no bevel) and this tool's
first version (output_mode MESH, matching an early, uncertain guess at
this project's actual manual habit) were both re-examined directly:

- output_mode "mesh" + format "abc": exported, then re-imported via
  `bpy.ops.wm.alembic_import` - the result had the right POINT COUNT but
  ZERO edges. Alembic's PolyMesh schema doesn't have a generic "bare
  edges, no faces" concept, and Blender's exporter silently drops straight
  to a point cloud for one. The border-line SHAPE is gone, not just its
  thickness - country_wireframes.py's grouping into distinct connected
  border lines doesn't survive at all.
- output_mode "curve" + format "abc", bevel_depth 0 (no thickness): round
  -tripped back in as a real CURVES object with the correct point-per-
  curve grouping intact (verified: 1 line feature in -> 1 curve, 4 points,
  out). Alembic has an actual Curves schema, and it works exactly as
  you'd hope - with NO thickness needed at all.
- output_mode "curve" + format "stl", bevel_depth > 0: verified separately
  - re-imported via `bpy.ops.wm.stl_import`, produced real triangulated
  tube geometry (nonzero face count). STL is a pure triangle-surface
  format and always needs a genuine bevel_depth > 0 to have anything to
  write - "mesh" mode (no faces at all) or bevel_depth 0 both produce an
  empty/near-empty .stl either way. This tool prints a warning if you set
  format "stl" with bevel_depth 0.

So: use "curve" for both formats. Only reach for "mesh" if you have some
other, non-Blender downstream consumer that's confirmed to handle bare
edge data from one of these formats - as far as this repo's own testing
goes, it doesn't buy you anything.
"""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _startup_loader  # noqa: E402

CONFIG_FILENAME = "geojson_export.json"

# Config file keys and their defaults - kept in one place so the template,
# the loader, and _resolve_output_path's assumptions can never drift apart.
_CONFIG_DEFAULTS = {
    "inputs": [],
    "output": None,
    "output_dir": None,
    "format": "abc",
    "output_mode": "curve",
    "bevel_depth": 0.0,
}


def _iter_objects(collection):
    """Every object in `collection`, recursing into child collections -
    needed because geojson_split_collections defaults to True, which nests
    imported features one collection deeper per feature type (Buildings,
    Ways, GeoJSON_unknown, ...) under "GeoJSON Imports"."""
    for obj in collection.objects:
        yield obj
    for child in collection.children:
        yield from _iter_objects(child)


def _run_import(bpy, input_path, output_mode):
    """Runs object.import_geojson_wireframes exactly as the panel button
    would, overriding only geojson_output_mode, and returns the list of
    objects it created (everything now under Geo Wireframes/GeoJSON
    Imports) - or raises RuntimeError with the operator's own report."""
    settings = bpy.context.scene.country_wireframe_settings
    settings.geojson_output_mode = output_mode.upper()

    result = bpy.ops.object.import_geojson_wireframes(filepath=str(input_path))
    if "FINISHED" not in result:
        raise RuntimeError(
            f"object.import_geojson_wireframes did not finish for "
            f"'{input_path}' (result={result}) - see the console output "
            f"above for the operator's own error report."
        )

    root = bpy.data.collections.get("Geo Wireframes")
    imports_coll = root.children.get("GeoJSON Imports") if root else None
    if imports_coll is None:
        raise RuntimeError(
            "Import reported success but the 'Geo Wireframes' > 'GeoJSON "
            "Imports' collection doesn't exist - has country_wireframes.py "
            "changed its collection naming since this script was written?"
        )
    return list(_iter_objects(imports_coll))


def _apply_bevel(objects, bevel_depth):
    if bevel_depth <= 0:
        return
    n = 0
    for obj in objects:
        if obj.type == "CURVE":
            obj.data.bevel_depth = bevel_depth
            n += 1
    if n == 0:
        print(
            "[geojson_export] bevel_depth was given but no CURVE objects "
            "were created to apply it to (did you mean output_mode "
            "'curve'?)"
        )


_HOUDINI_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _houdini_safe_name(name):
    """Houdini (and Alembic-consuming DCCs generally) require object/node
    path components to be valid identifiers: ASCII letters, digits, and
    underscore only, never starting with a digit.

    Blender's own object names allow far more, and its Alembic exporter
    only partially sanitizes on write - verified directly: spaces and
    periods become underscores, but commas, dashes, apostrophes, and
    non-ASCII characters are all written through as-is (e.g.
    "GeoJSON_Baldwin County, AL" -> "GeoJSON_Baldwin_County,_AL" in the
    actual exported file - the comma survives). GeoJSON feature names
    (place names in particular) routinely contain exactly these
    characters, so this can't be left to the exporter alone.
    """
    safe = _HOUDINI_UNSAFE_CHARS.sub("_", name)
    if not safe or safe[0].isdigit():
        safe = "_" + safe
    return safe


def _rename_unique(base, current, existing_lookup, used):
    """One namespace's worth of the collision-avoidance logic shared by
    _make_houdini_safe_unique below - factored out since it's needed
    twice (Object names and mesh/curve data-block names are two SEPARATE
    Blender namespaces, both of which end up as distinct nodes in an
    exported Alembic hierarchy - a transform node named after the object,
    and a child shape/data node named after its data-block)."""
    candidate = base
    n = 1
    while candidate in used or (
        candidate in existing_lookup and existing_lookup[candidate] is not current
    ):
        n += 1
        candidate = f"{base}_{n}"
    used.add(candidate)
    return candidate


def _data_collection_for(bpy, data_block):
    """The bpy.data.<collection> that actually owns `data_block` (e.g.
    bpy.data.meshes for a Mesh, bpy.data.curves for a legacy Curve) -
    found via a membership check against every bpy.data collection,
    rather than guessing a pluralized collection name from the type
    (gets irregular plurals wrong - Mesh -> "meshes", not "meshs") or
    hardcoding a type->collection map that would need updating for every
    new data type this pipeline might ever produce. A handful of extra
    collection scans per exported object is negligible.
    """
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION":
            continue
        collection = getattr(bpy.data, prop.identifier, None)
        if collection is None:
            continue
        try:
            existing = collection.get(data_block.name)
        except (AttributeError, TypeError):
            continue
        if existing is data_block:
            return collection
    return {}


def _make_houdini_safe_unique(bpy, objects):
    """Rename `objects` AND their data-blocks in place to Houdini-safe,
    collision-free names - verified necessary: the exported Alembic
    hierarchy has a separate node per data-block (e.g. a curve object's
    underlying Curve data becomes its own "..._Curve"-suffixed node,
    country_wireframes.py's own naming convention), not just one per
    object, and that data-block name carries the same unsafe characters
    the object name does unless sanitized separately here too.

    Two distinct original names can sanitize to the same result (e.g.
    "St. Louis" and "St-Louis" both -> "St__Louis" or similar) - handled
    with a counted suffix, rather than left to Blender's own same-name
    handling: Blender auto-disambiguates with a "name.001"-style dot
    suffix, which would silently reintroduce exactly the character class
    this function exists to remove. Also checked against every OTHER
    existing name in the same namespace (not just names assigned this
    pass), so a renamed object/data-block can never collide with some
    unrelated, unexported one already in the scene (e.g. the default
    Camera/Light, or country_wireframes.py's GeoJSONPointPrototype mesh)
    and get dot-suffixed that way instead.
    """
    used_obj_names = set()
    used_data_names = set()
    for obj in objects:
        obj.name = _rename_unique(
            _houdini_safe_name(obj.name), obj, bpy.data.objects, used_obj_names
        )
        if obj.data is not None:
            obj.data.name = _rename_unique(
                _houdini_safe_name(obj.data.name),
                obj.data,
                _data_collection_for(bpy, obj.data),
                used_data_names,
            )


def _export(bpy, objects, output_path, fmt):
    if fmt == "abc":
        # Only Alembic's consumers (Houdini foremost) impose this - STL
        # has no comparable per-object naming/hierarchy concept.
        _make_houdini_safe_unique(bpy, objects)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "stl":
        if hasattr(bpy.ops.wm, "stl_export"):
            bpy.ops.wm.stl_export(
                filepath=str(output_path), export_selected_objects=True
            )
        else:
            # Pre-4.x fallback: the old io_mesh_stl add-on's operator.
            bpy.ops.export_mesh.stl(filepath=str(output_path), use_selection=True)
    elif fmt == "abc":
        bpy.ops.wm.alembic_export(filepath=str(output_path), selected=True)
    else:
        raise ValueError(f"Unknown format: {fmt!r}")


def _resolve_output_path(input_path, output_arg, output_dir_arg, fmt, single_input):
    if single_input and output_arg:
        return Path(output_arg)
    out_dir = Path(output_dir_arg) if output_dir_arg else input_path.parent
    return out_dir / (input_path.stem + f".{fmt}")


def _write_config_template(path):
    template = dict(_CONFIG_DEFAULTS)
    template["inputs"] = ["/path/to/your/first.geojson"]
    template["_readme"] = (
        "Fill in 'inputs' (a path, or a list of paths, to .geojson files) "
        "and re-run the same command. "
        "output: exact output file path, only valid with exactly one "
        "input - leave null to use output_dir instead. "
        "output_dir: directory to write outputs into - leave null to "
        "write each output alongside its input. "
        "format: 'abc' (Alembic) or 'stl'. "
        "output_mode: 'curve' (default - verified to preserve border-line "
        "connectivity through both export formats) or 'mesh' (verified "
        "NOT to - see this script's module docstring before using it). "
        "bevel_depth: only applied when output_mode is 'curve' - tube "
        "radius in scene units. 0 (default) means no thickness, which is "
        "fine for format 'abc' but produces an empty/near-empty file for "
        "format 'stl' (a pure surface format - it needs the bevel to have "
        "any geometry to write at all). "
        "Delete this '_readme' key or not, either way it's ignored."
    )
    path.write_text(json.dumps(template, indent=2) + "\n")


def _load_config(path):
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"[geojson_export] Could not read '{path}': {e}")

    data.pop("_readme", None)
    unknown = set(data) - set(_CONFIG_DEFAULTS)
    if unknown:
        raise SystemExit(
            f"[geojson_export] Unknown key(s) in '{path}': {sorted(unknown)} "
            f"- expected only {sorted(_CONFIG_DEFAULTS)}"
        )

    merged = dict(_CONFIG_DEFAULTS)
    merged.update(data)

    if isinstance(merged["inputs"], str):
        merged["inputs"] = [merged["inputs"]]
    if not merged["inputs"]:
        raise SystemExit(
            f"[geojson_export] '{path}' has no 'inputs' filled in yet - "
            f"add at least one .geojson path and re-run"
        )
    if merged["format"] not in ("abc", "stl"):
        raise SystemExit(f"[geojson_export] '{path}': format must be 'abc' or 'stl'")
    if merged["output_mode"] not in ("mesh", "curve"):
        raise SystemExit(f"[geojson_export] '{path}': output_mode must be 'mesh' or 'curve'")
    if merged["output"] and len(merged["inputs"]) != 1:
        raise SystemExit(
            f"[geojson_export] '{path}': 'output' can only be used with "
            f"exactly one entry in 'inputs' - use 'output_dir' instead for "
            f"more than one"
        )
    if merged["format"] == "stl" and merged["bevel_depth"] <= 0:
        print(
            "[geojson_export] WARNING: format 'stl' with bevel_depth 0 - "
            "verified to produce an empty/near-empty file (STL is a pure "
            "surface format; with no bevel there's no surface to write, "
            "regardless of output_mode). Set bevel_depth > 0."
        )

    return SimpleNamespace(**merged)


def _get_config():
    """Returns the config as a SimpleNamespace, or None if a fresh
    template was just written (nothing to run yet)."""
    config_path = Path.cwd() / CONFIG_FILENAME
    if not config_path.exists():
        _write_config_template(config_path)
        print(
            f"[geojson_export] No config file found - wrote a template to "
            f"'{config_path}'. Fill in at least 'inputs' and re-run the "
            f"same command."
        )
        return None

    print(f"[geojson_export] Using config file: {config_path}")
    return _load_config(config_path)


def main():
    args = _get_config()
    if args is None:
        return

    import bpy

    _startup_loader.load_and_register()

    single_input = len(args.inputs) == 1
    for raw_input in args.inputs:
        input_path = Path(raw_input).resolve()
        if not input_path.exists():
            print(f"[geojson_export] Skipping '{input_path}': file not found")
            continue

        output_path = _resolve_output_path(
            input_path, args.output, args.output_dir, args.format, single_input
        )

        print(f"[geojson_export] {input_path.name} -> {output_path}")
        objects = _run_import(bpy, input_path, args.output_mode)
        if not objects:
            print(f"[geojson_export] No objects created from '{input_path.name}' - skipping export")
            continue

        _apply_bevel(objects, args.bevel_depth)
        _export(bpy, objects, output_path, args.format)
        print(f"[geojson_export] Wrote {output_path} ({len(objects)} object(s))")


if __name__ == "__main__":
    main()
