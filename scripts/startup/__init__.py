from . import chezmoi_sync
from . import country_wireframes
from . import get_extension_keys
from . import flat_gis_importer

# Define the Blender addon/script metadata block
bl_info = {
    "name": "Chezmoi Environment Sync",
    "author": "Matthew Turk",
    "version": (1, 1),
    "blender": (5, 0, 0),
    "location": "Startup",
    "description": (
        "Automated preference synchronization and extension tracking exporter."
    ),
    "category": "System",
}


def register():
    # Pass registration downstream to your sync logic
    chezmoi_sync.register()
    country_wireframes.register()
    get_extension_keys.register()
    flat_gis_importer.register()


def unregister():
    # Allow safe unregistering if needed
    chezmoi_sync.unregister()
    country_wireframes.unregister()
    get_extension_keys.unregister()
    flat_gis_importer.unregister()


if __name__ == "__main__":
    register()
