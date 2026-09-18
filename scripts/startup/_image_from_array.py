# Shared logic behind user_scripts/bake_colormap_textures.py (and any other
# script that needs to bake a numpy RGBA array into a bpy.types.Image) - see
# _collection_to_lists_shared.py for why this lives one directory up, in
# scripts/startup/, rather than inside user_scripts/ or node_scripts/
# themselves: dynamic_script_runner.py's directory scans only look for a
# PARAMS+execute pair or a build() function, so a plain helper module kept
# alongside those folders (instead of one level up here) would wrongly be
# treated as a runnable script/node-tree entry of its own.
#
# Import this via the repo's usual "_load_sibling" pattern (see
# user_scripts/constant_mass_emission_times.py) rather than a package-
# relative import: user_scripts/ and node_scripts/ files are loaded one at a
# time by dynamic_script_runner.py via importlib.util.spec_from_file_
# location, with no parent package context, so `from . import x` doesn't
# work from inside them.

import numpy as np


def get_or_create_image(name, width, height, float_buffer=True):
    """Get an existing image by name if present, else create a new one.

    Matches the `if name not in bpy.data.images: ... else: ...` reuse
    pattern used elsewhere in this toolchain (import_cms.py / ytgrids_in_
    blender.py in the blendyt reference repo) - baking the same colormap
    name twice reuses the same data-block instead of piling up
    cmyt_viridis, cmyt_viridis.001, ... Does NOT resize/reallocate an
    existing image whose dimensions no longer match `width`/`height` -
    remove it from bpy.data.images first if you need a clean rebuild at a
    different resolution.
    """
    import bpy

    if name not in bpy.data.images:
        return bpy.data.images.new(name, width, height, alpha=False, float_buffer=float_buffer)
    return bpy.data.images[name]


def write_rgba(image, rgba_array):
    """Write a (height, width, 4) float32 RGBA array into `image.pixels`.

    Blender's Image.pixels is a flat row-major buffer: consecutive floats
    are (r, g, b, a) for column 0, 1, 2, ... of row 0, then row 1, and so
    on - so a numpy array laid out (height, width, 4) and ravelled in C
    order matches it directly. This is the same convention import_cms.py
    relies on: it builds a (256, 64, 4) array and feeds it straight to
    foreach_set after a plain `.ravel(order="C")` (no transpose), against
    an image created with `bpy.data.images.new(name, 64, 256, ...)` - i.e.
    width=64, height=256, matching the array's (height, width, 4) shape.
    """
    rgba_array = np.asarray(rgba_array, dtype=np.float32)
    width, height = image.size[0], image.size[1]
    if rgba_array.shape != (height, width, 4):
        raise ValueError(
            f"Expected an array shaped (height={height}, width={width}, 4) "
            f"to match image '{image.name}' ({width}x{height}), got "
            f"{rgba_array.shape}"
        )
    image.pixels.foreach_set(rgba_array.ravel(order="C"))
