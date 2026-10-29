from . import _chezmoi_sync_shim as chezmoi_sync
from . import get_extension_keys
import bpy

# The GIS and data-viz tools now live in the AVL GeoViz extension
# (~/dev/blender-avl-geoviz). geo_coord.py and country_wireframes.py stay
# here, unregistered, only for cli/geojson_export.py (see
# cli/_startup_loader.py); constant_mass_core.py, constant_mass_geometry_io.py
# and _attr_io_shared.py stay for user_scripts/.

# Define the Blender addon/script metadata block
bl_info = {
    "name": "Matt's Blender Scripts",
    "author": "Matthew Turk",
    "version": (1, 1),
    "blender": (5, 0, 0),
    "location": "Startup",
    "description": (
        "Automated preference synchronization and extension tracking exporter. The script runner, viewport clipping and GIS tools now live in their own extensions (~/dev/blender-script-runner, ~/dev/blender-viewport-clipping, ~/dev/blender-avl-geoviz)."
    ),
    "category": "System",
}


def register():
    # Pass registration downstream to your sync logic
    chezmoi_sync.register()
    get_extension_keys.register()


def unregister():
    # Allow safe unregistering if needed
    chezmoi_sync.unregister()
    get_extension_keys.unregister()


if __name__ == "__main__":
    register()
