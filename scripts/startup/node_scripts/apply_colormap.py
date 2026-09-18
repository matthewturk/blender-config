NAME = "Colormapped Mesh"

MATERIAL_NAME = "Apply Colormap"

# Ported from blendyt's apply_colormap.py (github.com/matthewturk/blendyt,
# nodetree_script DSL) to this repo's nodebpy DSL. The original builds two
# separate node trees - a "Colormapped Mesh" geometry-nodes group and an
# "Apply Colormap" material - from two separate @ns.tree/@ns.materialtree
# decorated functions. This file builds both from the single build() call
# this repo's node_script contract gives us: the geometry group into the
# `tree` that's passed in (the modifier-facing half), and the material as a
# side effect, keyed off `params["colormap_image_name"]` (the shading half -
# not itself a geometry-nodes concept, so it can't live in `tree`).
#
# Geometry side: stores `attribute_name` (a build-time PARAMS string, not a
# runtime tree-input socket like the original's `property_name: ns.String` -
# this repo's PARAMS system already provides that parameterization at build
# time, see attribute_curve_map.py's `attr_name` param for the same
# convention) as a POINT-domain "cm_value" float attribute, computes its
# min/max across the geometry, converts to a single instance, and stores
# "cm_min"/"cm_max" as INSTANCE-domain attributes on it - exactly the
# original's `colormapped_mesh`.
#
# Material side: reads "cm_min"/"cm_max" back from the INSTANCER and
# "cm_value" from the GEOMETRY, normalizes with Map Range, and samples an
# Image Texture at a UV built from the normalized value - exactly the
# original's `apply_colormap`, EXCEPT for which axis the normalized value
# drives (see the UV vector comment in build() below - this is a deliberate
# change from the original, not a port mistake).

PARAMS = {
    "attribute_name": {
        "type": "STRING",
        "default": "",
        "name": "Attribute Name",
        "description": "Named attribute on the input geometry to colorize",
    },
    "colormap_image_name": {
        "type": "STRING",
        "default": "cmyt_arbre",
        "name": "Colormap Image",
        "description": (
            "Name of an image already baked by bake_colormap_textures.py "
            "(e.g. 'cmyt_arbre' or 'cm_viridis') - sampled by the 'Apply "
            "Colormap' material this also (re)builds"
        ),
    },
}


def _build_geometry_group(tree, params):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Geometry")
    attribute_name = params.get("attribute_name", "")

    stored_value = g.StoreNamedAttribute.point.float(
        geometry=geometry,
        name="cm_value",
        value=g.NamedAttribute.float(name=attribute_name).o.attribute,
    )
    stats = g.AttributeStatistic(
        geometry=stored_value.o.geometry,
        attribute=g.NamedAttribute.float(name="cm_value").o.attribute,
        domain="POINT",
    )
    instances = g.GeometryToInstance(stored_value.o.geometry)
    stored_min = g.StoreNamedAttribute.instance.float(
        geometry=instances.o.instances,
        name="cm_min",
        value=stats.o.min,
    )
    stored_minmax = g.StoreNamedAttribute.instance.float(
        geometry=stored_min.o.geometry,
        name="cm_max",
        value=stats.o.max,
    )

    tree.outputs.geometry("Output") >> stored_minmax.o.geometry


def _build_material(params):
    import bpy
    from nodebpy import shader as ss

    image_name = params.get("colormap_image_name", "") or "cmyt_arbre"

    # MaterialBuilder (nodebpy.builder.tree.MaterialBuilder, used by
    # nodebpy.shader.material()) always calls bpy.data.materials.new(name) -
    # unlike g.tree(existing_or_name), it has no "reuse an existing
    # data-block" path. So rebuild-on-rerun is done by hand here, the same
    # remove-then-recreate way hdf5_to_curves.py/sqlite_to_object.py handle
    # data-blocks that need a full rebuild rather than an in-place edit.
    existing_material = bpy.data.materials.get(MATERIAL_NAME)
    if existing_material is not None:
        bpy.data.materials.remove(existing_material)

    with ss.material(MATERIAL_NAME, fake_user=True) as mat:
        cm_min = ss.Attribute(attribute_type="INSTANCER", attribute_name="cm_min").o.fac
        cm_max = ss.Attribute(attribute_type="INSTANCER", attribute_name="cm_max").o.fac
        cm_value = ss.Attribute(attribute_type="GEOMETRY", attribute_name="cm_value").o.fac

        normalized = ss.MapRange(
            value=cm_value,
            from_min=cm_min,
            from_max=cm_max,
            to_min=0.0,
            to_max=1.0,
        ).o.result

        # UV axis: bake_colormap_textures.py bakes a HORIZONTAL gradient -
        # color varies along the image's WIDTH, height is a uniform strip
        # (see that file's module docstring) - so the normalized value has
        # to land on U (x), not V (y), to actually land on a different
        # column per value. The original blendyt version built `combine_xyz
        # (x=0.5, y=normalized, z=1.0)` - normalized on Y - which only reads
        # the intended gradient back correctly against a VERTICAL layout
        # (color varying along height). Since this repo's own bake script
        # (built alongside this file, for internal consistency) is
        # horizontal, x/y are swapped here relative to the original.
        uv = ss.CombineXYZ(x=normalized, y=0.5, z=1.0).o.vector

        image = bpy.data.images.get(image_name)
        if image is None:
            print(
                f"[apply_colormap] Image '{image_name}' not found in "
                f"bpy.data.images - bake it first via bake_colormap_"
                f"textures.py. Falling back to a flat default color."
            )
            base_color = (0.8, 0.8, 0.8, 1.0)
        else:
            image_texture = ss.ImageTexture(vector=uv)
            image_texture.node.image = image
            base_color = image_texture.o.color

        bsdf = ss.PrincipledBSDF(base_color=base_color)
        ss.MaterialOutput(surface=bsdf)

    return mat.material


def build(tree, params):
    _build_geometry_group(tree, params)
    _build_material(params)
