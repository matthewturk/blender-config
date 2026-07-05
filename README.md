# Blender Config

This is my repository of Blender configuration.

I use a couple different machines for Blender, and I tend to have it managed by Steam so that I can just allow it to apply the updates, etc. But this led to the situation where I was constantly having things out of sync across my desktops. I also use [Chezmoi](https://www.chezmoi.io/) so it made sense to try to get both of them working together.

What I've set up is a `uv`-based system for installing packages that can be linked into the Blender environment, and then updating them. I suspect this may be more fragile than it appears at first, but I'll address that as I need to. Chezmoi manages linking the startup script into them, which then runs on execution and applies my config stuff and links to `sys.path`.

It's working for now!

## Supported Config Keys

In addition to render/device and asset library settings, the startup sync now supports:

- `input`: Directly maps onto Blender input/navigation preferences (for example: `select_mouse`, `view_rotate_method`, `use_zoom_to_mouse`).
- `filepaths`: Directly maps onto Blender filepath preferences.
- `external_tools`: Convenience aliases for external tool paths:
  - `text_editor` -> Blender `preferences.filepaths.text_editor`
  - `image_editor` -> Blender `preferences.filepaths.image_editor`
  - `animation_player` -> Blender `preferences.filepaths.animation_player`
- `addon_preferences`: Per add-on preference values by add-on key/module.
- `jupyter_bridge`: Starts a localhost code-execution bridge so Jupyter can send Python into the running Blender UI on the main thread.

Example external editor path for Linux is usually VS Code at `/usr/bin/code`.
On some installations it may differ (for example Flatpak/Snap wrappers).

## JupyterLab Bridge

This repo now includes a Blender-side bridge plus a small IPython extension so that a normal JupyterLab Python kernel can execute `bpy` code inside a running Blender session.

This is intentionally not a true embedded Jupyter kernel inside Blender. Blender API access is most reliable on Blender's main thread, so the safer model is:

1. Blender starts a localhost bridge during startup.
2. JupyterLab stays on its usual Python kernel.
3. `%%blender` cells are forwarded into Blender and executed on Blender's main thread.

Enable the bridge in `~/.config/blender/config.json`:

```json
{
  "jupyter_bridge": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 5667,
    "connection_file": "~/.local/state/blender-jupyter/connection.json"
  }
}
```

If you want an extra check beyond loopback-only access, add an `auth_token` value to the same object.

After restarting Blender, the startup script writes connection info to `~/.local/state/blender-jupyter/connection.json` and logs the listener address to the Blender console.

In JupyterLab, use a normal Python notebook and load the helper from this repo:

```python
import sys
sys.path.append("/home/mturk/.config/blender/blender-config")

%load_ext blender_jupyter
%blender_status
```

Then send code to Blender with a cell magic:

```python
%%blender
import bpy

obj = bpy.context.active_object
if obj is not None:
    obj.location.x += 1.0
    print(obj.name, obj.location)
```

If you keep the connection file somewhere else, pass its path on the magic line:

```python
%%blender /path/to/connection.json
print(bpy.context.scene.name)
```

For direct programmatic use without magics:

```python
from blender_jupyter import get_client

client = get_client()
client.ping()
client.exec("import bpy; print(bpy.context.scene.name)")
```
