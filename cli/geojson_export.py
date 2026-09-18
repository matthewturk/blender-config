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
format        "abc" (Alembic), "stl", "fbx", "usd", or "usdz". "usdz" is
              the same USD export, just zipped into one self-contained
              file - see "usdz - a single self-contained file" below.
output_mode   "curve" (default) or "mesh" - see below, "mesh" is kept
              available but doesn't actually preserve border-line
              connectivity through any of the export formats.
bevel_depth   Only applied when output_mode is "curve" - tube radius in
              scene units. 0 (default) means no thickness. Required (> 0)
              for "stl" and "fbx".
flatten_object_attrs
              format "usd"/"usdz" only. Also writes each object's custom
              properties as real constant-interpolation USD primvars
              directly on its geometry prim, on top of the object-level
              `userProperties` that export anyway - see "Getting
              object-level properties out" below for why that second copy
              is necessary, not redundant.

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
- format "fbx" behaves exactly like "stl" here - verified the same way,
  by round-tripping through `bpy.ops.import_scene.fbx`. Blender's FBX
  exporter converts curves to meshes on write (its `object_types`
  "OTHER" category), so what reaches the file is whatever the bevel
  produced: with bevel_depth 0.05 a 4-point test curve came back as 48
  verts / 84 edges / 36 faces (real tube geometry), but with
  bevel_depth 0 the same curve came back as 4 verts / 0 edges / 0 faces
  - the shape is gone, exactly like the Alembic "mesh" case above. A
  bare-edge MESH (4 verts / 3 edges / no faces) sent straight through
  FBX came back 4 verts / 0 edges too: FBX drops loose edges the same
  way Alembic does. So "fbx" also needs output_mode "curve" AND
  bevel_depth > 0, and gets the same warning "stl" does.

So: use "curve" for all three formats. Only reach for "mesh" if you have
some other, non-Blender downstream consumer that's confirmed to handle
bare edge data from one of these formats - as far as this repo's own
testing goes, it doesn't buy you anything.

Getting object-level properties out - VERIFIED, and why Houdini can't see
them without flatten_object_attrs
-------------------------------------------------------------------------
country_wireframes.py attaches its per-feature data as object-level
custom (ID) properties: geo_kind, geo_name, geo_continent, geo_iso2,
geo_iso3, geo_m49, geo_source_file, geo_feature_index, plus one `osm:<k>`
property per original GeoJSON feature property.

Every format here that supports "custom properties" at all
(`export_custom_properties=True`, the default, passed explicitly below)
writes these as attributes on the OBJECT/TRANSFORM node - Alembic's
`.userProperties` compound, USD's `userProperties:*` namespace on the
Xform prim. Verified directly for both, and for USD by dumping the raw
file:

    def Xform "GeoJSON_Baldwin_County__AL"
    {
        custom string userProperties:geo_name = "Baldwin County, AL"
        custom int userProperties:geo_m49 = 840

        def BasisCurves "GeoJSON_Baldwin_County__AL_Curve"
        {
            point3f[] points = [...]
        }
    }

That is real, correct, present data - not a bug - but it lives one level
above the actual geometry, and that placement matters more than it looks:

- Blender's OWN importer (`wm.usd_import` / `wm.alembic_import`) knows its
  own `userProperties`/`.userProperties` convention and reconstructs
  Blender object properties from it on reimport - verified, a round-trip
  through bpy brings geo_name etc. straight back as obj[...] entries. That
  makes it easy to believe the data is universally accessible - it's only
  Blender-specific symmetry, not a USD/Alembic standard.
- A generic consumer has no such convention to fall back on. Houdini's
  classic SOP-level importer (the `usdimport` SOP, or a File SOP pointed
  at a USD file) works by flattening the USD/Alembic hierarchy into plain
  point/primitive geometry, and the only per-geometry data that flatten
  carries over is PRIMVARS (USD) - real attributes declared ON the
  geometry prim itself, with a defined interpolation (constant / uniform /
  vertex / faceVarying). A custom attribute sitting on the parent Xform,
  which owns no points or primitives of its own, has nothing to flatten
  onto - it isn't dropped by a bug, there was never a path for it to
  survive. (Houdini's Solaris/LOPs context keeps the native USD hierarchy
  and CAN see `userProperties:*` directly as ordinary prim metadata - but
  that needs Solaris specifically, e.g. a Python LOP reading
  `prim.GetAttribute(...)`, not the classic SOP import path.)
- Alembic makes this moot for anything BUT `.userProperties`: verified
  directly, Blender 5.2.2's Alembic exporter does not write generic
  geometry attributes at all, at any domain. Named INT/FLOAT/FLOAT_COLOR/
  STRING attributes added to the POINT domain of a real faced mesh (a
  cube, so "no faces" isn't the explanation) came back completely absent
  from the raw .abc - the `.arbGeomParams` container is written but empty.
  The only per-geometry channels that DO survive: UV layers (FLOAT2,
  CORNER domain), and BYTE_COLOR color attributes on CORNER specifically
  (`vcolors=True`). Consuming `.userProperties` in Houdini: Alembic SOP ->
  "Load User Properties", landing them as two JSON-string detail/primitive
  attributes (`abcUserProperties`/`abcUserPropertiesValues`) to parse
  downstream - per-object, not per-point, which is the accepted tradeoff
  for real generic geometry attributes being entirely unavailable.

So for USD specifically, `flatten_object_attrs` exists to put a second,
real copy of the same data directly on the geometry prim as a primvar -
see the next section for exactly how and why "constant" interpolation,
not per-point, is what that means in practice.

format "usd"/"usdz", and flatten_object_attrs - real primvars via direct
USD authoring, not through Blender's own exporter
-------------------------------------------------------------------------
The first version of this tried to get object properties onto points
using Blender's own mesh/curve `.attributes` API before calling
`wm.usd_export`, converting output_mode "curve"'s attribute-less legacy
Curve data into a Mesh or the newer Curves type first. Two things about
that approach turned out to be wrong once actually tested against real
Houdini usage instead of just a Blender round-trip:

- Blender 5.2.2's USD exporter crashes trying to write a STRING-typed
  attribute to a primvar, at ANY domain - verified across POINT, FACE, and
  CORNER (CURVE domain isn't even valid on a curve's own geometry type):
  "Code marked as unreachable has been executed",
  usd_attribute_utils.cc:211, and the primvar's NAME gets written with NO
  values - worse than omitting it. That's precisely the string data
  (geo_name, geo_iso2/iso3, geo_continent, geo_kind, every `osm:*`
  property) an artist actually wants to filter by; only the numeric ones
  survived.
- Per-point duplication was never actually necessary. This data is one
  value describing a whole feature (a whole county, a whole line) - USD
  primvars support "constant" interpolation for exactly that: one value
  for the entire prim, not one copy per point. That's both cheaper AND
  the semantically correct representation, and it still gets promoted
  into a Houdini attribute by the classic `usdimport` SOP flatten, the
  same as any other primvar interpolation would.

So this now bypasses Blender's own USD exporter for this data entirely
and authors real primvars directly with the actual USD API (the
`usd-core` PyPI package / `pxr` Python bindings - a real project
dependency here, `uv add usd-core` was run directly against this repo,
and verified to import in the same process as `bpy` with no conflict:
`bpy.ops.wm.usd_export` still worked correctly both before AND after a
`from pxr import Usd` in the same script run). `_flatten_object_attrs_usd`
runs as a POST-PROCESS step on the file `wm.usd_export` already wrote:
for each object with custom properties, it opens the stage, finds that
object's Xform prim by name (matching the already houdini-safe-uniqued
object name - `_make_houdini_safe_unique` runs before export, so the
in-memory Blender name and the on-disk USD prim name are identical by the
time this runs), walks every descendant prim looking for the real
geometry (anything `UsdGeom.Boundable` - BasisCurves, Mesh, whatever
`wm.usd_export` produced), and authors one constant-interpolation primvar
per property directly there. Verified on a real object from this
pipeline, dumping the patched file:

    def BasisCurves "GeoJSON_Baldwin_County__AL_Curve"
    {
        point3f[] points = [...]
        string primvars:geo_name = "Baldwin County, AL" (
            interpolation = "constant"
        )
        int primvars:geo_m49 = 840 (
            interpolation = "constant"
        )
    }

Bool, Int, and String were all verified to work through this path with no
equivalent of the STRING assert above - that bug is specific to Blender's
OWN generic-mesh-attribute-to-primvar conversion code, not to USD's data
model, so writing a String primvar directly via `UsdGeom.PrimvarsAPI`
has no such problem. This means, unlike the old approach, EVERY property
type flattens now, not just the numeric ones.

The two representations are additive, not either/or: with
`flatten_object_attrs: true`, `geo_name` shows up BOTH as
`userProperties:geo_name` on the Xform (object-level, Solaris-visible,
Blender-round-trippable) AND as `primvars:geo_name` on the geometry
(classic-SOP-visible, the whole reason this exists). One sharp edge
carried over unchanged from before: an integer feature property too big
for a 32-bit int is already a Python STRING by the time it reaches this
script, because country_wireframes.py's _safe_custom_property_value()
stringifies it upstream to dodge a Blender attribute OverflowError (US
Census ALAND/AWATER values are the usual case - Baldwin County, AL:
ALAND=4117656199). It still flattens fine now (as a String primvar,
verified), just not as the numeric type it originally was - deliberately
not re-parsed back into a number here, since a stringly-typed ID
(a FIPS code with a leading zero, say) would be indistinguishable from an
overflowed number and re-parsing it would corrupt exactly that case.

format "usdz" - a single self-contained file
-------------------------------------------------------------------------
`wm.usd_export` has no separate "give me usdz" argument - it decides
ascii/binary/zipped purely from the filepath's extension, verified
directly: the exact same export call, pointed at a path ending ".usdz"
instead of ".usd", comes back as a real zip (`PK\x03\x04` header,
readable with Python's own `zipfile`) containing a single `.usdc`.
`_resolve_output_path` already produces that extension automatically for
`format: "usdz"` - both formats run through the identical branch in
_export below.

What makes this worth having over plain "usd" specifically: this repo's
scenes generally have a World background color, and `usd_export`'s
`convert_world_material` default (on) turns that into a texture -
verified, exporting the real output of this script's own GeoJSON import
produced a `textures/color_0C0C0C.exr` file sitting loose NEXT TO the
`.usd`, not inside it. Copy or send the `.usd` alone and that texture
reference silently breaks. Re-running the identical export with a
".usdz" path instead produces ONE file - verified by unzipping it:
`['test.usdc', 'textures/color_0C0C0C.exr']`, the texture packed inside
the archive, no loose file written to disk at all.

flatten_object_attrs + "usdz" needs one extra step, because a zipped USD
package can't be edited in place - VERIFIED
-------------------------------------------------------------------------
`pxr.Usd.Stage.Open` can OPEN a `.usdz` directly, but re-`Save()`-ing a
stage whose root layer lives inside a zip package fails outright -
verified: `SdfLayer::_CheckFormatWritability`, "writing package usdz
layer is not allowed through this API". Usdz is deliberately a read-only
distribution format at the layer level.

So when `flatten_object_attrs` is on and the format is "usdz", `_export`
does not point `wm.usd_export` at the final .usdz path directly. Instead
it exports to a plain, unzipped `.usd` in a temporary directory, runs
`_flatten_object_attrs_usd` against THAT (a normal writable file, no
package involved), and only then packages the patched result into the
real output path with `pxr.UsdUtils.CreateNewUsdzPackage(staging, final)`
- verified to bundle referenced textures correctly, using the exact
world-color-texture case above as the test: the produced .usdz contained
`['test.usd', 'textures/color_0C0C0C.exr']`, same as bpy's own direct
usdz export, with the patched primvars also present. When there's nothing
to flatten (the flag is off, or no object in the batch has any custom
properties), this whole staging detour is skipped and `wm.usd_export`
targets the .usdz path directly as before - there's no writable-package
problem to route around if nothing is patching it afterward.
"""

import json
import re
import sys
import tempfile
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
    "flatten_object_attrs": False,
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


def _usd_value_type_for(Sdf, value):
    """The Sdf.ValueTypeNames constant a custom (ID) property value can be
    written as a USD primvar with, or None if its type isn't one this
    pipeline's properties ever actually take (plain scalar bool/int/float/
    str is everything country_wireframes.py ever assigns).

    `bool` is checked before `int` because Python's bool IS an int -
    reversing these would turn every flag into a 0/1 Int primvar. Unlike
    the old Blender-attribute-based approach this replaced, STRING has no
    special problem here - verified (see module docstring) that Blender's
    OWN generic-attribute-to-primvar exporter crashes on STRING, but
    authoring a String primvar directly through UsdGeom.PrimvarsAPI, as
    this pipeline does, does not hit that at all.
    """
    if isinstance(value, bool):
        return Sdf.ValueTypeNames.Bool
    if isinstance(value, int):
        return Sdf.ValueTypeNames.Int
    if isinstance(value, float):
        return Sdf.ValueTypeNames.Double
    if isinstance(value, str):
        return Sdf.ValueTypeNames.String
    return None


def _flatten_object_attrs_usd(objects, usd_path):
    """Post-process `usd_path` - a plain (non-package) file `wm.usd_export`
    has already written - authoring one constant-interpolation USD primvar
    per custom (ID) property, directly on each object's real geometry
    prim, using the actual USD API rather than Blender's own exporter.

    Why this is a separate pass instead of something done through bpy
    before export, and why "constant" rather than one value per point, is
    explained at length in the module docstring ("format usd/usdz, and
    flatten_object_attrs") - short version: Blender's exporter can't write
    STRING attributes as primvars at all (an internal assert), and a
    single value describing a whole feature belongs at "constant"
    interpolation, not duplicated across every point.

    Matches each object to its Xform prim by NAME, which only works
    because the caller runs `_make_houdini_safe_unique` before export -
    the in-memory Blender object name and the on-disk USD prim name are
    then identical. Walks every descendant of that prim (not just direct
    children) looking for real geometry (`UsdGeom.Boundable`), since a
    beveled legacy Curve was observed to sometimes export as more than one
    nested BasisCurves prim under its Xform - patching every Boundable
    found is cheap and guarantees whichever one a downstream tool actually
    reads has the primvar too.
    """
    from pxr import Sdf, Usd, UsdGeom

    objects_with_props = [(obj, {k: obj[k] for k in obj.keys()}) for obj in objects]
    objects_with_props = [(obj, props) for obj, props in objects_with_props if props]
    if not objects_with_props:
        return

    stage = Usd.Stage.Open(str(usd_path))
    flattened = 0
    skipped_unsupported = {}
    for obj, props in objects_with_props:
        target = next(
            (prim for prim in stage.Traverse() if prim.GetName() == obj.name), None
        )
        if target is None:
            print(
                f"[geojson_export] Could not find '{obj.name}' in the "
                f"written USD stage - skipping its object properties"
            )
            continue

        geom_prims = [p for p in Usd.PrimRange(target) if p.IsA(UsdGeom.Boundable)]
        for geom_prim in geom_prims:
            pv_api = UsdGeom.PrimvarsAPI(geom_prim)
            for key, value in props.items():
                value_type = _usd_value_type_for(Sdf, value)
                if value_type is None:
                    skipped_unsupported.setdefault(type(value).__name__, set()).add(key)
                    continue
                # Same identifier rule as Alembic's consumers - and a raw
                # "osm:name" would otherwise become the NESTED USD
                # namespace `primvars:osm:name` rather than one flat
                # primvar name.
                name = _houdini_safe_name(key)
                # HasPrimvar takes the bare name (CreatePrimvar's own
                # `name` argument below) - GetPrimvars()'s own GetName()
                # returns the full "primvars:"-prefixed attribute name
                # instead, which a plain `name in {...}` set check would
                # never match against.
                if pv_api.HasPrimvar(name):
                    print(
                        f"[geojson_export] Not flattening '{key}' on "
                        f"'{obj.name}': '{name}' is already a primvar on "
                        f"'{geom_prim.GetPath()}'"
                    )
                    continue
                pv_api.CreatePrimvar(name, value_type, UsdGeom.Tokens.constant).Set(
                    value
                )
                flattened += 1

    stage.GetRootLayer().Save()
    print(
        f"[geojson_export] Flattened {flattened} object propert(ies) onto "
        f"geometry as constant-interpolation USD primvars"
    )
    for type_name, keys in sorted(skipped_unsupported.items()):
        print(
            f"[geojson_export]   skipped {len(keys)} {type_name} propert(ies) "
            f"of an unsupported type - left object-level only: "
            f"{sorted(keys)[:4]}{' ...' if len(keys) > 4 else ''}"
        )


def _export(bpy, objects, output_path, fmt, flatten_object_attrs):
    if fmt in ("abc", "usd", "usdz"):
        # Only Alembic's and USD's consumers (Houdini foremost) impose
        # this. USD prim paths take exactly the same identifier rule, and
        # while Blender does sanitize them on write itself (verified:
        # "GeoJSON_Baldwin County, AL" -> "GeoJSON_Baldwin_County__AL"),
        # doing it here first is what keeps two features that sanitize to
        # the SAME string from colliding as sibling prims.
        #
        # STL has no per-object naming/hierarchy concept at all, and FBX,
        # while it does have one, is permissive about what goes in it -
        # verified:
        # an object named "GeoJSON_Baldwin County, AL" round-tripped
        # through FBX byte-for-byte, spaces and comma intact, and FBX's
        # usual consumers (Unity/Unreal/Maya) take that fine. Sanitizing
        # it here would rename objects for no benefit.
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
    elif fmt == "fbx":
        # object_types is left at its default (everything): `use_selection`
        # already narrows the export to exactly `objects`, and the default
        # set includes "OTHER", which is the category curves fall into -
        # dropping it would silently export nothing in curve mode.
        bpy.ops.export_scene.fbx(filepath=str(output_path), use_selection=True)
    elif fmt == "abc":
        # export_custom_properties is what carries country_wireframes.py's
        # object-level ID properties (geo_name, geo_iso3, the osm:* feature
        # properties, ...) into the file's .userProperties - see "Getting
        # object-level properties out through Alembic" in the module
        # docstring. It already defaults to True; passed explicitly so a
        # future default flip can't silently drop that data.
        bpy.ops.wm.alembic_export(
            filepath=str(output_path), selected=True, export_custom_properties=True
        )
    elif fmt in ("usd", "usdz"):
        # Same operator for both - `usd_export` decides ascii/binary/zipped
        # purely from output_path's extension (verified: filepath ending
        # ".usdz" alone is what makes it zip everything up, no separate
        # format argument exists on this operator), and _resolve_output_path
        # already picks that extension from `fmt`.
        #
        # export_custom_properties keeps the object-level properties too -
        # they land as `userProperties:<name>` on each prim, which is the
        # only representation Solaris/LOPs or a Blender reimport ever see.
        # flatten_object_attrs additionally writes real primvars directly
        # onto the geometry - see the module docstring for why both are
        # kept rather than one replacing the other.
        want_flatten = flatten_object_attrs and any(obj.keys() for obj in objects)
        if fmt == "usdz" and want_flatten:
            # A zipped usdz package can't be edited in place (verified -
            # see module docstring), so export to a plain, unzipped
            # staging file first, patch THAT, then package the patched
            # result into the real .usdz destination.
            with tempfile.TemporaryDirectory() as staging_dir:
                staging_path = Path(staging_dir) / (output_path.stem + ".usd")
                bpy.ops.wm.usd_export(
                    filepath=str(staging_path),
                    selected_objects_only=True,
                    export_custom_properties=True,
                )
                _flatten_object_attrs_usd(objects, staging_path)
                from pxr import UsdUtils

                if not UsdUtils.CreateNewUsdzPackage(
                    str(staging_path), str(output_path)
                ):
                    raise RuntimeError(
                        f"UsdUtils.CreateNewUsdzPackage failed to package "
                        f"'{staging_path}' into '{output_path}'"
                    )
        else:
            bpy.ops.wm.usd_export(
                filepath=str(output_path),
                selected_objects_only=True,
                export_custom_properties=True,
            )
            if want_flatten:
                _flatten_object_attrs_usd(objects, output_path)
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
        "format: 'abc' (Alembic), 'stl', 'fbx', 'usd', or 'usdz'. 'usdz' is "
        "the exact same USD export, just zipped into one self-contained "
        "file (any textures embedded inside it instead of written "
        "alongside as loose files) - see this script's module docstring "
        "for what's verified to end up inside. "
        "output_mode: 'curve' (default - verified to preserve border-line "
        "connectivity through every export format) or 'mesh' (verified "
        "NOT to - see this script's module docstring before using it). "
        "bevel_depth: only applied when output_mode is 'curve' - tube "
        "radius in scene units. 0 (default) means no thickness, which is "
        "fine for format 'abc'/'usd'/'usdz' but produces an empty/shapeless "
        "file for formats 'stl' and 'fbx' (surface formats - they drop bare "
        "edges and need the bevel to have any geometry to write at all). "
        "flatten_object_attrs: format 'usd'/'usdz' only - also write each "
        "object's custom properties as real constant-interpolation USD "
        "primvars (primvars:geo_name, ...) directly on the geometry prim, "
        "needed for a classic Houdini usdimport SOP / File SOP to see them "
        "at all - a plain USD 'userProperties:<name>' on the object's "
        "Xform (which every export already writes) only survives that "
        "kind of flatten-to-SOP-geometry import if it's a real primvar; "
        "Solaris/LOPs can see userProperties directly without this flag. "
        "Additive either way, not a replacement - object-level "
        "userProperties are written regardless of this flag. "
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
    if merged["format"] not in ("abc", "stl", "fbx", "usd", "usdz"):
        raise SystemExit(
            f"[geojson_export] '{path}': format must be 'abc', 'stl', "
            f"'fbx', 'usd', or 'usdz'"
        )
    if merged["output_mode"] not in ("mesh", "curve"):
        raise SystemExit(f"[geojson_export] '{path}': output_mode must be 'mesh' or 'curve'")
    if merged["output"] and len(merged["inputs"]) != 1:
        raise SystemExit(
            f"[geojson_export] '{path}': 'output' can only be used with "
            f"exactly one entry in 'inputs' - use 'output_dir' instead for "
            f"more than one"
        )
    if merged["flatten_object_attrs"] and merged["format"] not in ("usd", "usdz"):
        raise SystemExit(
            f"[geojson_export] '{path}': flatten_object_attrs only works "
            f"with format 'usd' or 'usdz' (got '{merged['format']}'). "
            f"Verified: Blender's Alembic exporter writes NO generic "
            f"geometry attributes at all, and STL/FBX have nowhere to put "
            f"them - see this script's module docstring. Object-level "
            f"properties still export to Alembic's .userProperties without "
            f"this."
        )
    if merged["format"] in ("stl", "fbx") and merged["bevel_depth"] <= 0:
        print(
            f"[geojson_export] WARNING: format '{merged['format']}' with "
            f"bevel_depth 0 - verified to produce an empty/shapeless file "
            f"(both are surface formats that drop bare edges; with no bevel "
            f"there's no surface to write, regardless of output_mode). "
            f"Set bevel_depth > 0."
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
        _export(bpy, objects, output_path, args.format, args.flatten_object_attrs)
        print(f"[geojson_export] Wrote {output_path} ({len(objects)} object(s))")


if __name__ == "__main__":
    main()
