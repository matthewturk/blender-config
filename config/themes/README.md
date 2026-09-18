# Checked-in theme presets

Drop bare interface-theme `.xml` files here (the kind exported via Preferences > Themes >
Presets > "Save As Preset", or a standalone `.xml` someone hands you with no
`blender_manifest.toml` alongside it - a bare theme file can never become a real
Extensions-platform package with its own ID; see `../README.md`'s theme section).

`chezmoi_sync.py`'s `_sync_repo_theme_presets()` copies every `*.xml` here into this
machine's real `scripts/presets/interface_theme/` directory on every Blender launch
(only writing when a file is missing or its bytes differ from the checked-in copy), so a
theme tracked here is available on any machine after `chezmoi apply` with no separate
manual install step. Reference it by its display name in `config.json`'s `theme` key -
the same name Preferences > Themes > Presets shows in its dropdown (derived from the
filename via `bpy.path.display_name()`, e.g. `Blender_Dark.xml` -> "Blender Dark").

A theme that DOES come as a real packaged extension (a `.zip` with `blender_manifest.toml`
+ one or more `.xml` files) does not belong here - install it through Blender's Extensions
system instead (Get Extensions > Install from Disk, or drag-and-drop the zip), which gives
it a real package ID and update/uninstall tracking that a bare file drop never can.
