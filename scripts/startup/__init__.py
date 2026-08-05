from . import chezmoi_sync
from . import geo_coord
from . import country_wireframes
from . import get_extension_keys
from . import flat_gis_importer
from . import dynamic_script_runner
from . import gpx_import
from . import ppm1d_nodebpy
from . import data_visualization_menu
from . import constant_mass_emission_generator
from . import country_pair_batch_emitter
from . import viewport_switch
import bpy

# Define the Blender addon/script metadata block
bl_info = {
    "name": "Matt's Blender Scripts",
    "author": "Matthew Turk",
    "version": (1, 1),
    "blender": (5, 0, 0),
    "location": "Startup",
    "description": (
        "Automated preference synchronization and extension tracking exporter, along with some GIS and dynamic python execution stuff."
    ),
    "category": "System",
}


def register():
    # Pass registration downstream to your sync logic
    chezmoi_sync.register()
    geo_coord.register()
    country_wireframes.register()
    get_extension_keys.register()
    flat_gis_importer.register()
    dynamic_script_runner.register()
    gpx_import.register()
    data_visualization_menu.register()
    constant_mass_emission_generator.register()
    country_pair_batch_emitter.register()
    viewport_switch.register()
    bpy.app.timers.register(ppm1d_nodebpy.build_ppm_tree, first_interval=3.0)


def unregister():
    # Allow safe unregistering if needed
    chezmoi_sync.unregister()
    geo_coord.unregister()
    country_wireframes.unregister()
    get_extension_keys.unregister()
    flat_gis_importer.unregister()
    dynamic_script_runner.unregister()
    gpx_import.unregister()
    constant_mass_emission_generator.unregister()
    country_pair_batch_emitter.unregister()
    data_visualization_menu.unregister()
    viewport_switch.unregister()


if __name__ == "__main__":
    register()
