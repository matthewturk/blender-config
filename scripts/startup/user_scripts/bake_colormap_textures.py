import os
import importlib.util

import bpy

# Bakes matplotlib/cmyt colormaps into horizontal-gradient Blender images -
# one pixel column per sampled color, `height` identical rows underneath so
# the gradient reads cleanly as a strip when viewed in the Image Editor.
# Colors vary along the image's WIDTH (the `resolution` param); `height`
# is purely a uniform, constant-color thickness. apply_colormap.py (in
# node_scripts/) samples these images with the normalized value on the U
# (x/width) axis, matching this layout - see that file's build() docstring
# for the reasoning.
#
# Ported from blendyt's import_cms.py (github.com/matthewturk/blendyt),
# which bakes every colormap in the cmyt package the same way (sampled via
# matplotlib, written through Image.pixels.foreach_set), but hardcodes
# ALL_CMYT-only behavior and a fixed 256x64 resolution. This version adds a
# SINGLE-colormap mode (any matplotlib/cmyt name) and PARAMS-driven sizing.


def _load_sibling(module_name):
    path = os.path.join(os.path.dirname(__file__), "..", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PARAMS = {
    "mode": {
        "type": "ENUM",
        "default": "ALL_CMYT",
        "items": [
            ("ALL_CMYT", "All CMYT Colormaps", "Bake every colormap in the cmyt package"),
            ("SINGLE", "Single Colormap", "Bake one named matplotlib/cmyt colormap"),
        ],
        "name": "Mode",
        "description": "Bake every colormap in cmyt, or just one colormap by name",
    },
    "colormap_name": {
        "type": "STRING",
        "default": "viridis",
        "name": "Colormap Name",
        "description": (
            "Used only in Single Colormap mode. Any matplotlib colormap name "
            "(e.g. 'viridis') or a cmyt one prefixed 'cmyt.' (e.g. 'cmyt.arbre')"
        ),
    },
    "resolution": {
        "type": "INT",
        "default": 256,
        "min": 8,
        "name": "Resolution",
        "description": "Number of distinct color steps sampled across the colormap (image width)",
    },
    "height": {
        "type": "INT",
        "default": 64,
        "min": 1,
        "name": "Height",
        "description": "Image height in pixels - every row is identical, this is just visual thickness",
    },
}


def _bake_one(plt, np, helper, image_name, cmap, resolution, height):
    """Bake `cmap` (a matplotlib Colormap) into `image_name`, resolution
    steps wide, height rows tall, color varying along width only."""
    vals = np.linspace(0.0, 1.0, resolution)
    mappable = plt.cm.ScalarMappable(cmap=cmap)
    mappable.set_clim(0.0, 1.0)
    row = mappable.to_rgba(vals).astype("f4")  # (resolution, 4)

    arr = np.empty((height, resolution, 4), dtype="f4")
    arr[:] = row[None, :, :]  # broadcast the same row down every line

    image = helper.get_or_create_image(image_name, resolution, height, float_buffer=True)
    helper.write_rgba(image, arr)
    image.pack()
    image.use_fake_user = True
    return image


def execute(context, params):
    import matplotlib.pyplot as plt
    import numpy as np
    import cmyt  # noqa: F401 - registers the cmyt.* colormaps with matplotlib

    helper = _load_sibling("_image_from_array")

    mode = params["mode"]
    resolution = params["resolution"]
    height = params["height"]

    if mode == "SINGLE":
        colormap_name = params["colormap_name"].strip()
        try:
            cmap = plt.get_cmap(colormap_name)
        except (ValueError, KeyError) as e:
            print(f"[bake_colormap_textures] Unknown colormap '{colormap_name}': {e}")
            return {"CANCELLED"}

        sanitized = colormap_name.replace(".", "_").replace(" ", "_")
        image_name = f"cm_{sanitized}"
        _bake_one(plt, np, helper, image_name, cmap, resolution, height)

        print(
            f"[bake_colormap_textures] Baked 1 image ('{image_name}'), "
            f"mode=SINGLE, resolution={resolution}, height={height}"
        )
        return {"FINISHED"}

    # ALL_CMYT mode
    count = 0
    for cmap_name in cmyt._utils.cmyt_cmaps:
        cmap = plt.get_cmap(f"cmyt.{cmap_name}")
        _bake_one(plt, np, helper, f"cmyt_{cmap_name}", cmap, resolution, height)
        count += 1

    print(
        f"[bake_colormap_textures] Baked {count} images, mode=ALL_CMYT, "
        f"resolution={resolution}, height={height}"
    )
    return {"FINISHED"}
