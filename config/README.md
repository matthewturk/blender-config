# Config

This directory holds the config-sync system: `chezmoi_sync.py` (the implementation, real and
live - this is what actually runs) and three **non-live reference copies** documenting the
schema it reads: `config.json.tmpl`, `example.config.json`, and
`run_onchange_after_configure-blender-paths.sh.tmpl`.

This is a config-management concern, not a Blender feature or plugin - it's kept separate
from `scripts/startup/`, which holds the actual GIS importers, node builders, and other
add-on functionality. `scripts/startup/_chezmoi_sync_shim.py` is the only link between the
two: a thin re-export so Blender's real startup-scan (which only looks inside
`scripts/startup/`) still finds a registration entry point, while the real logic lives here.

## IMPORTANT: the *.tmpl files here are reference copies, not the live ones

Confirmed by direct comparison (2026-09): chezmoi does NOT read `config.json.tmpl` or
`run_onchange_after_configure-blender-paths.sh.tmpl` from this repo at all. The versions that
actually run live in chezmoi's own *source* directory (`chezmoi source-path`, typically
`~/.local/share/chezmoi/`) as an entirely separate set of files:

- Real, live template: `~/.local/share/chezmoi/dot_config/blender/config.json.tmpl`
- Real, live hook: `~/.local/share/chezmoi/run_onchange_after_configure-blender-paths.sh.tmpl`

This repo is itself pulled into place by chezmoi as a `git-repo` external (see
`.chezmoiexternal.toml` in that source directory) - it's the *destination* of that external,
not the *source* of anything chezmoi templates. The two `.tmpl` files here have already been
found to have DRIFTED from the real ones (different templating logic entirely, not just a
formatting difference) - don't trust them as ground truth for what a given machine will
actually get, and don't expect editing them here to change any real machine's behavior.
They're kept only because a couple of this repo's own Python files cite them by name as
documentation (see `_chezmoi_sync_shim.py`, `cli/_startup_loader.py`) - if you change the
real chezmoi-managed versions, update these to match by hand; there is no automation keeping
them in sync.

## How the rendered config actually reaches Blender (the real path)

1. The REAL `config.json.tmpl` (in chezmoi's source directory, not here) is chezmoi's source
   template - per-host values (device type, interface scale, asset library path, ...) are
   filled in via chezmoi's templating when you run `chezmoi apply` on a given machine.
2. Chezmoi renders it out to `~/.config/blender/config.json` - **outside this repo entirely**,
   a sibling of wherever this repo itself is checked out. `chezmoi_sync.py` only ever reads
   that rendered file, never any `.tmpl` file directly (from this repo or chezmoi's source).
3. `chezmoi_sync.py`'s `load_and_sync_chezmoi()` (registered on Blender's `load_post` handler)
   reads that file and applies each section to `bpy.context.preferences`.
4. Everything fails soft: a missing `config.json` prints an informational message and does
   nothing (not an error - a machine with no chezmoi setup at all works fine, just without
   any preference sync); an invalid value in one section (an unrecognized device type, a
   missing theme preset, a malformed asset-library entry) prints a warning and skips just
   that section, without blocking the rest of the file from applying.

`example.config.json` (here, genuinely just a reference file - there's no separate "real"
copy of this one anywhere) is a plain JSON copy of the same shape, with no chezmoi template
syntax - useful for seeing what a fully-rendered config actually looks like, or as a starting
point on a machine that isn't using chezmoi at all (just copy it to
`~/.config/blender/config.json` and edit the values directly).

## Schema

Every top-level key is optional - omit anything you don't want managed.

| Key | Applies to | Notes |
|---|---|---|
| `interface_scale` | `preferences.view.ui_scale` | Applied separately from the rest of `view` below. |
| `render_device_type` | `preferences.addons['cycles'].preferences.compute_device_type` | One of Blender's real enum values: `NONE`, `CUDA`, `OPTIX`, `HIP`, `METAL`, `ONEAPI` - **all caps**, no mixed-case variants. Validated against the live enum at apply time; an invalid value warns and skips (doesn't block anything else). |
| `theme` | `preferences.themes` | A bundled or user interface theme preset, matched by display name (e.g. `"Deep Grey"`) against Blender's installed theme presets by filename. Missing preset warns and skips. |
| `input` | `preferences.inputs` | e.g. `select_mouse`, `view_rotate_method`, `use_zoom_to_mouse`. |
| `filepaths` | `preferences.filepaths` | Direct passthrough. |
| `view` | `preferences.view` | e.g. `show_developer_ui`, `show_tooltips_python`. |
| `edit` | `preferences.edit` | e.g. `undo_steps`, `undo_memory_limit`. |
| `system` | `preferences.system` | e.g. `memory_cache_limit`, `gpu_backend` (`"OPENGL"`/`"VULKAN"`/`"METAL"` on macOS - requires an app restart). |
| `experimental` | `preferences.experimental` | Direct passthrough of feature-flag booleans. |
| `external_tools` | `preferences.filepaths.*` | Convenience aliases: `text_editor`, `image_editor`, `animation_player`. |
| `addon_preferences` | per-add-on preferences | Keyed by add-on module/key. |
| `asset_libraries` | `preferences.filepaths.asset_libraries` | List of `{"name": ..., "path": ..., "import_method": "LINK"\|"APPEND"\|"APPEND_REUSE"}` (the last is optional). Existing libraries are updated in place by name; new ones are added. |
| `extensions` | installed/enabled add-ons | List of extension/add-on package IDs (e.g. `"blender_id"`, a classic add-on module name, or a Blender 4.2+ extension package ID - both are treated as equivalent). Anything listed that's installed-but-disabled gets enabled; anything not installed at all is reported as missing (not auto-installed over the network). `scripts/startup/get_extension_keys.py` is a small helper that harvests the currently-enabled extension keys from a running Blender session into exactly this list's format, via the clipboard - handy for populating this key from a machine that's already set up the way you want. |

`interface_scale`/`render_device_type`/`theme` are flat top-level keys (not nested); every
other row above is a nested object.

## Known gaps (as of 2026-09)

- No config key currently maps onto Cycles render *engine* settings beyond the device type
  (samples, denoising, etc.) - only what's listed above is implemented.
- `render_device_type`'s valid-value check depends on being able to introspect
  `compute_device_type`'s real enum at apply time; in at least one headless/background
  session this came back as an empty list (fails safe - warns and skips - but the device
  type then never gets applied in that session either).
