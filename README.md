# Blender Config

This is my repository of Blender configuration.

I use a couple different machines for Blender, and I tend to have it managed by Steam so that I can just allow it to apply the updates, etc. But this led to the situation where I was constantly having things out of sync across my desktops. I also use [Chezmoi](https://www.chezmoi.io/) so it made sense to try to get both of them working together.

What I've set up is a `uv`-based system for installing packages that can be linked into the Blender environment, and then updating them. I suspect this may be more fragile than it appears at first, but I'll address that as I need to. Chezmoi manages linking the startup script into them, which then runs on execution and applies my config stuff and links to `sys.path`.

It's working for now!

## Geometry Nodes Vertex Group Sync

Geometry Nodes still treats many weight-style results as attributes unless the original input geometry stays in the stream, which is why the common join/delete workaround preserves vertex groups.

This config now includes a startup helper panel on mesh data properties called `Geometry Nodes Vertex Groups`. It can:

- copy scalar point attributes from the evaluated Geometry Nodes result back onto the source object as real vertex groups
- bake a new mesh object from the evaluated result when the node tree replaces the input geometry entirely
- limit syncing to a comma-separated list of attribute names, or sync every scalar point attribute when left blank
- auto-sync after depsgraph updates if you enable `Auto Sync`

Use `Sync Geometry Nodes Vertex Groups` when the evaluated result still matches the source mesh topology. Use `Bake Evaluated Copy` when the node tree fully replaces the input geometry and you want a real mesh object with real vertex groups, without the join/delete workaround.

## Supported Config Keys

In addition to render/device and asset library settings, the startup sync now supports:

- `input`: Directly maps onto Blender input/navigation preferences (for example: `select_mouse`, `view_rotate_method`, `use_zoom_to_mouse`).
- `filepaths`: Directly maps onto Blender filepath preferences.
- `external_tools`: Convenience aliases for external tool paths:
  - `text_editor` -> Blender `preferences.filepaths.text_editor`
  - `image_editor` -> Blender `preferences.filepaths.image_editor`
  - `animation_player` -> Blender `preferences.filepaths.animation_player`
- `addon_preferences`: Per add-on preference values by add-on key/module.

Example external editor path for Linux is usually VS Code at `/usr/bin/code`.
On some installations it may differ (for example Flatpak/Snap wrappers).
