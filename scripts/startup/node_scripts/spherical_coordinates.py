NAME = "Spherical Coordinates"

# Ported from /tmp/blendyt_review/sphere_perturbations.py's
# `spherical_coordinates` function (blendyt's `nodetree_script` DSL),
# translated to this repo's `nodebpy` DSL.
#
# Judgment call vs. the original: the original computed `r = length(positions)`
# from its own `positions` parameter, but then computed `theta`/`phi` from
# `gs.position()` - the live Position node (i.e. the CURRENT evaluated point's
# position), NOT from `positions`. That's an inconsistency (arguably a bug):
# a "Cartesian to spherical" utility should depend only on its own input, not
# silently also read whatever geometry context happens to be live at the call
# site (which may not even be the same vector as `positions`). This port
# fixes that: `r`, `theta`, and `phi` are all computed from the single
# `Position` tree input consistently. Flagged here and in the port report.


def build(tree, params):
    from nodebpy import geometry as g

    position = tree.inputs.vector(
        name="Position",
        default_value=(0.0, 0.0, 0.0),
        description="Cartesian position to convert to spherical coordinates",
    )

    r = position.length()
    theta = g.Math.arccosine(value=position.z / r)
    phi = g.Math.arctan2(value=position.y, value_001=position.x)

    spherical = g.CombineXYZ(x=r, y=theta, z=phi)

    tree.outputs.vector(
        name="Spherical",
        description="(radius, polar angle theta, azimuthal angle phi)",
    ) >> spherical.o.vector
