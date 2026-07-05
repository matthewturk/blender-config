from . import chezmoi_sync
from . import geonodes_vertex_groups
from . import get_extension_keys

# Define the Blender addon/script metadata block
bl_info = {
    "name": "Chezmoi Environment Sync",
    "author": "Matthew Turk",
    "version": (1, 1),
    "blender": (5, 0, 0),
    "location": "Startup",
    "description": (
        "Automated preference synchronization and extension tracking" " exporter."
    ),
    "category": "System",
}


def register():
    # Pass registration downstream to your sync logic
    chezmoi_sync.register()
    geonodes_vertex_groups.register()
    get_extension_keys.register()


def unregister():
    # Allow safe unregistering if needed
    chezmoi_sync.unregister()
    geonodes_vertex_groups.unregister()
    get_extension_keys.unregister()


if __name__ == "__main__":
    register()
