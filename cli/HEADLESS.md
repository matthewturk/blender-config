# Running this repo fully headless (no Blender GUI, no real Blender install)

`bpy` (the standalone PyPI build of Blender) is a real dependency of this repo's
`pyproject.toml` - added and verified in place, not a separate project. This document is the
"zero to full" story: what actually works, what had to be fixed to get there, and the real
limitations to keep in mind.

## Quick start

```bash
cd ~/.config/blender/blender-config   # or wherever you've cloned this repo
uv sync
uv run python cli/geojson_export.py
```

That's it - `uv sync` installs `bpy` alongside every other dependency this repo already
uses (`databpy`, `nodebpy`, `geopandas`, `scipy`, `yt`, `rasterio`, `osmnx`, `cmyt`, ...), all
resolved together in one lockfile, no splitting into separate environments. The first run of
`geojson_export.py` with no config file yet will write you a template and tell you to fill it
in - see `cli/geojson_export.py`'s own docstring for the config fields.

Any new `cli/` tool should follow the same two pieces: `cli/_startup_loader.py` (loads
`scripts/startup/` as the real `chezmoi` package and registers it, without needing a real
Blender launch) and a JSON config file in the current working directory instead of CLI
arguments (see `cli/geojson_export.py`'s docstring for why - `blender -P` doesn't pass
arguments through the way you'd expect).

## What had to be fixed to make this work

**`bmesh` isn't in the pip `bpy` wheel.** Checked directly: the installed package has exactly
one compiled extension (`bpy/__init__.so`) plus Blender's bundled pure-Python factory scripts
- no compiled `bmesh` module anywhere, and there's no separate `bmesh` package on PyPI either.
Three files in `scripts/startup/` did `import bmesh` - two actually used it
(`country_wireframes.py`'s `_build_sphere_mesh`, `flat_gis_importer.py`'s
`create_default_marker_object`, both just building a UV-sphere/cone primitive), one had a
dead unused import (`gpx_import.py`). Fixed by replacing the `bmesh.ops.create_uvsphere`/
`create_cone` calls with `bpy.ops.mesh.primitive_uv_sphere_add`/`primitive_cone_add` (build
into a throwaway object, take its mesh, discard the object) - verified this pattern works
with no GPU/display at all. As of this fix, nothing in this repo needs `bmesh` any more, so
this is now a non-issue - but if you add a NEW bmesh call to any startup script in the
future, it will break under headless `bpy` even though it works fine under a real Blender
install. Use the primitive-operator-plus-extract pattern instead, or build the mesh directly
via `bpy.data.meshes.new()` + `from_pydata()`.

**`_startup_loader.py`'s "already loaded" check was silently broken.** It used to check
`hasattr(bpy.ops.object, "import_geojson_wireframes")` - but `bpy.ops.<category>` attribute
access is fully dynamic and returns a truthy-looking callable for *any* name, real or made
up (`hasattr(bpy.ops.object, "totally_made_up_xyz")` is also `True`). That meant the loader
always believed everything was already registered and never actually loaded anything. Fixed
to check `hasattr(bpy.types, "OBJECT_OT_import_geojson_wireframes")` instead - `bpy.types` is
the real registration target `bpy.utils.register_class` populates, so this actually reflects
whether the package has been loaded.

**A genuine `country_wireframes.py` bug, found via real use (not headless-specific):**
`OverflowError` assigning a large GeoJSON integer property (US Census `ALAND`/`AWATER`, land/
water area in square meters, routinely exceeds 32-bit int range) as a Blender custom
property. Fixed with a range check that falls back to `str()` only for out-of-range ints. See
[[geojson-cli-export-2026-09]] memory for the full story - unrelated to bpy vs. real Blender,
would have hit either way.

## What's still a real limitation

**Version mismatch.** The pip `bpy` wheel tracks stable/LTS Blender releases (5.2.2 LTS as
of this investigation); your interactive Blender install can legitimately be a different
version (an alpha/dev build in particular, which will never have a matching pip wheel at
all). RNA properties, operator names, and enum values can differ between versions. Everything
in this document was verified against `bpy==5.2.2` specifically - if your real Blender is a
meaningfully different version and something breaks, that's the first thing to suspect.
`chezmoi_sync.py`'s registration already degrades gracefully for at least one such case
(an empty Cycles device-type enum list under headless `bpy`, logged as a warning, not a
crash) - most of the rest of this repo's operator/property surface hasn't been exhaustively
checked against 5.2.2 the way the GeoJSON import path has.

**`flat_gis_importer.py`'s own venv-bridging hack (`_ensure_venv()`) is now redundant but
harmless** when running through this repo's own `uv` environment - it exists to give
Blender's *real* bundled Python (which has no site-packages of its own) access to this
repo's managed dependencies, by hardcoding a `sys.path.append` to
`~/.config/blender/blender-config/.venv/.../site-packages`. Under `uv run` here, that path is
already on `sys.path` via the venv itself, so the append is a no-op (guarded by an `if ...
not in sys.path` check) - confirmed harmless, not worth removing since it's still needed for
the real-Blender-bundled-Python scenario.

**Everything else in `scripts/startup/` beyond the GeoJSON import path is unverified under
headless `bpy`.** The fixes and tests above cover exactly the path `cli/geojson_export.py`
exercises (GeoJSON import, custom properties, UV-sphere marker creation, STL/Alembic/FBX/USD export,
round-tripped back into bpy to confirm real geometry). Other features (OSM import, Blue
Marble imagery, the constant-mass-emission generator, node_scripts/, etc.) haven't been run
under headless `bpy` at all yet - treat them as unverified until someone actually exercises
them this way, the same as everything flagged throughout this repo's memory notes.
