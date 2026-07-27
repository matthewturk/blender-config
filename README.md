# Blender Config

This is my repository of Blender configuration.

I use a couple different machines for Blender, and I tend to have it managed by Steam so that I can just allow it to apply the updates, etc. But this led to the situation where I was constantly having things out of sync across my desktops. I also use [Chezmoi](https://www.chezmoi.io/) so it made sense to try to get both of them working together.

What I've set up is a `uv`-based system for installing packages that can be linked into the Blender environment, and then updating them. I suspect this may be more fragile than it appears at first, but I'll address that as I need to. Chezmoi manages linking the startup script into them, which then runs on execution and applies my config stuff and links to `sys.path`.

It's working for now!

## Supported Config Keys

In addition to render/device and asset library settings, the startup sync now supports:

- `input`: Directly maps onto Blender input/navigation preferences (for example: `select_mouse`, `view_rotate_method`, `use_zoom_to_mouse`).
- `filepaths`: Directly maps onto Blender filepath preferences.
- `view`: Directly maps onto Blender's View & Controls preferences (`preferences.view`), for example `show_developer_ui`, `show_tooltips_python`. Note `interface_scale` (above) is applied separately onto `view.ui_scale`.
- `edit`: Directly maps onto Blender's Edit preferences (`preferences.edit`), for example `undo_steps`, `undo_memory_limit`.
- `system`: Directly maps onto Blender's System preferences (`preferences.system`), for example `memory_cache_limit`, `gpu_backend` (the "Display Graphics" backend setting — `"OPENGL"` or `"VULKAN"`, `"METAL"` on macOS; requires an application restart to take effect).
- `experimental`: Directly maps onto Blender's Experimental feature-flag preferences (`preferences.experimental`).
- `external_tools`: Convenience aliases for external tool paths:
  - `text_editor` -> Blender `preferences.filepaths.text_editor`
  - `image_editor` -> Blender `preferences.filepaths.image_editor`
  - `animation_player` -> Blender `preferences.filepaths.animation_player`
- `addon_preferences`: Per add-on preference values by add-on key/module.
- `theme`: Applies a bundled or user interface theme preset by display name (for example `"Deep Grey"`), matched against Blender's installed theme presets by filename.

Example external editor path for Linux is usually VS Code at `/usr/bin/code`.
On some installations it may differ (for example Flatpak/Snap wrappers).
