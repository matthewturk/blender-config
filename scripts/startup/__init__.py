from . import chezmoi_sync
from . import get_extension_keys
from . import jupyter_bridge

# Define the Blender addon/script metadata block
bl_info = {
    "name": "Chezmoi Environment Sync",
    "author": "Matthew Turk",
    "version": (1, 1),
    "blender": (5, 0, 0),
    "location": "Startup",
    "description": "Automated preference synchronization and extension "
    "tracking exporter.",
    "category": "System",
}


def register():
    # Pass registration downstream to your sync logic
    chezmoi_sync.register()
    get_extension_keys.register()
    jupyter_bridge.register()


def unregister():
    # Allow safe unregistering if needed
    jupyter_bridge.unregister()
    chezmoi_sync.unregister()
    get_extension_keys.unregister()


if __name__ == "__main__":
    register()
