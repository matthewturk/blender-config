# TODO

Follow-ups from the October 2026 asset/config audit and the `assets.toml` work.

## Personal / AVL split (done 2026-10-28, follow-ups)

All 55 managed assets, plus the IGUIDE trade CSVs and `CountryData.h5` (now in `data/`), moved from `~/blender-assets` to `~/avl-blender-assets`. Each library has its own `assets.toml` and `blender_assets.cats.txt` (catalog UUIDs unchanged). "AVL Assets" was added to the chezmoi Blender config.

- [ ] Relocate the broken links in these project files (Outliner → Blender File → right-click the library → Relocate, then pick the same file under `~/avl-blender-assets`):
  - `~/blender-projects/I-GUIDE/`: `New Globe`, `processing in blender`, `processing in blender1`, `alltoall`, `Untitled`, `connecting-points-on-globe`, `connecting-points-on-globe1`
  - `~/spheresmoving.blend`, `~/blender-projects/spheresmoving.blend`: `coordinate-utilities`, `force-calculation` (their `position-noise.blend` link was already broken; point it at `Position Randomization/position-noise.blend`)
  - `~/blah.blend`: `coordinate-utilities`
  - `~/blender-projects/fluid-attempt.blend`: `box`
  - `~/blender-projects/hammered-copper-well.blend`, `alternate-brass.blend`: `Position Randomization/position-noise`
- [ ] Fix the hard-coded CSV paths in the IGUIDE nodes (`/data/IGUIDE/…`, `~/data/IGUIDE/…`, `//Trade_*.csv`) to point at `data/` in the AVL library (e.g. `//../data/…` from `IGUIDE/`).
- [ ] Check the other Syncthing machines: the moved files were deleted from the synced `~/blender-assets`.
- [ ] Pick the shared network drive mount point and change the "AVL Assets" path in `~/.local/share/chezmoi/dot_config/blender/config.json.tmpl`. Every machine should use the same path.
- [ ] Before the first git commit in `~/avl-blender-assets`, add a `.gitignore` for `*.blend1` and decide whether `data/CountryData.h5` (154 MB) belongs in git or git-lfs.
- [ ] Decide on `interp.csv` and the loose OSM/GeoJSON/import scripts still in `~/blender-assets`.

## AVL library (`~/avl-blender-assets`)

- [ ] Commit `nodes/` (the nodebpy mirror) with the library, and rerun `blender-manager export-code -l ~/avl-blender-assets --blender-bin …` after editing node groups. Optionally add `export-code --check` as a pre-commit hook.
- [ ] Bump this repo's nodebpy pin (`uv add "nodebpy>=520.40"`): the venv still has 520.6.0, which the startup scripts load.
- [ ] Node groups nodebpy 520.40 can't rebuild yet (fine for the mirror, blocks making Python the source): Transfer Function Curves (Combine List), Convert Columns / Filter Attribute by Integer List (menu default set before link), Find First Match / String List Intersection (`list_length`), Get Country Code (string socket subscript).

- [ ] Write descriptions in `assets.toml`. 52 of the 55 entries are blank. Blender's style is one short sentence. Edit the file directly or use `e` in the TUI.
- [ ] Optionally add folder tags (e.g. `[folders."IGUIDE"] tags = ["iguide"]`) and per-asset tags.
- [ ] Apply the metadata (author "NCSA AVL", CC0, copyright Matthew Turk). Review with `blender-manager apply -l ~/avl-blender-assets --blender-bin /data/SteamLibrary/steamapps/common/Blender/blender`, then add `--write` (or press `Shift+A` in the TUI). After that, `check` should report the library in sync.
- [ ] Decide what to do with two stray text blocks that point outside the library:
  - `colormaps.blend` → `~/yt/blendyt/import_cms.py` (suggest making it internal)
  - `generic-grids.blend` → a Steam `space_node.py` (suggest deleting it)
- [ ] Decide on `brick-texture.blend1` in `~/blender-assets` (Purple Planet; left alone).
- [ ] Look at the Compute Trade Values file, which has 52M-point curves (file size and load time).

## Blender preferences

- [ ] Confirm the "User Library" (`~/Documents/Blender/Assets`) should use PACK, since everything else uses LINK.

## blender-manager-tui (`~/dev/blender-manager-tui`)

- [ ] Review and commit the manifest work. It sits on top of the uncommitted scan-cache changes, so it may want two commits.
- [ ] Try `e` / `b` / `m` / `Shift+A` in the TUI on a managed asset and on an excluded one.

## This repo

- [ ] Try the three d3blender conversions interactively (all verified headless only): `blender_halo_import.py`, plus AVL GeoViz's Create Markers and GPX import. Each now updates its objects in place on rerun instead of deleting or duplicating them.
- [ ] AVL GeoViz: `country_wireframes.py` re-downloads the Natural Earth zip on every Create/Refresh; cache it.
- [ ] AVL GeoViz: test `flat_gis_importer.py` building/road/marker imports on 5.4 end to end; its GN input setter was fixed for 5.2+ but only the setter itself was verified.

- [ ] Review and commit the audit fixes: `_attr_io_shared.py`, the `_load_sibling` imports, the `user_scripts/examples/` move, dropping the PPM timer, and `tests/constant_mass_core_test.py`.
- [ ] Write the FAO→HDF5 conversion script.

## Extensions

- [ ] Install Script Runner from its GitHub release (`dynamic_script_runner.py` has been removed from this repo).
- [ ] Install Adaptive Viewport Clipping from `~/dev/blender-viewport-clipping` (`viewport_switch.py` has been removed from this repo).
- [ ] Publish AVL GeoViz: create the GitHub repo, push, tag `v1.0.0` (needs d3blender public). Its GIS modules are no longer registered from this repo's startup.
- [ ] In Script Runner's preferences, add `scripts/startup/user_scripts` (Scripts) and `scripts/startup/node_scripts` (Node Scripts) from this repo.

## Sharing with a team (later)

- [ ] Pin a team Blender version and `bpy` version. Right now the binary is 5.4 Alpha and the venv's `bpy` is 5.2.2.
- [ ] Set file permissions once there's a project group.
- [ ] Move the scripts into a Blender extension. Done: script runner, viewport clipping and AVL GeoViz (geo suite plus the constant-mass tools) in `~/dev/blender-script-runner`, `~/dev/blender-viewport-clipping` and `~/dev/blender-avl-geoviz`.
- [ ] Do a catalog reorganization pass (deferred from the first pass).
