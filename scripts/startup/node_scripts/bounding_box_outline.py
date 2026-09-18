NAME = "Bounding Box Outline"

# Ported from /tmp/blendyt_review/grid_creator.py's `grid_as_points` (blendyt's
# `nodetree_script` DSL), translated to this repo's `nodebpy` DSL.
#
# `left_edge`/`right_edge` are exposed as live Geometry Nodes tree INPUT
# sockets (VECTOR) rather than build-time PARAMS: a bounding box's corners
# are exactly the kind of thing a user wants to wire up per-instance (or
# drive with other nodes/objects) in the node editor, not bake in at build
# time - so no PARAMS dict is needed for this node tree at all.
#
# Judgment call vs. the original: the original built `cube = gs.cube(size=
# spec.right_edge - spec.left_edge)` with no translation, which centers the
# box at the world origin regardless of where left_edge/right_edge actually
# sit - so e.g. left_edge=(0,0,0), right_edge=(2,2,2) would produce a box
# centered on the origin (from -1 to 1), not the box from (0,0,0) to (2,2,2)
# the inputs actually describe. That reads as a latent bug for a "bounding
# box outline of THIS specific box" utility, so this port ADDS a translation
# (TransformGeometry, offset by the box's midpoint) to place the outline at
# the corners actually given. This changes behavior from the original -
# flagged here and in the port report.


def build(tree, params):
    from nodebpy import geometry as g

    left_edge = tree.inputs.vector(
        name="Left Edge",
        default_value=(-1.0, -1.0, -1.0),
        description="Minimum (lower) corner of the bounding box",
    )
    right_edge = tree.inputs.vector(
        name="Right Edge",
        default_value=(1.0, 1.0, 1.0),
        description="Maximum (upper) corner of the bounding box",
    )

    size = right_edge - left_edge
    center = (left_edge + right_edge) * 0.5

    cube_mesh = g.TransformGeometry(
        geometry=g.Cube(size=size).o.mesh,
        translation=center,
    ).o.geometry

    curve = g.MeshToCurve(mesh=cube_mesh).o.curve

    curves = g.StoreNamedAttribute.point.integer(
        geometry=curve,
        name="curve_index",
        value=g.Index().o.index,
    )

    points = g.CurveToPoints(curve=curves.o.geometry)

    tree.outputs.geometry("Points") >> points.o.points
    tree.outputs.geometry("Curves") >> curves.o.geometry
