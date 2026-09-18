NAME = "Hedgehog Sphere"

# Ported from /tmp/blendyt_review/outward_facing_sphere.py's
# `outward_facing_sphere` (blendyt's `nodetree_script` DSL) into this repo's
# `nodebpy` DSL. `size`/`density` were the blendyt tree's own function
# parameters (its `@ns.tree`-decorated inputs) - here they're exposed the
# same way, as live FLOAT sockets on the tree's Group Input, rather than
# build-time PARAMS, so they can be animated/driven in the modifier like any
# other Geometry Nodes input.


def build(tree, params):
    from nodebpy import geometry as g

    size = tree.inputs.float(
        "Size", default_value=1.0, description="Radius of the base sphere"
    )
    density = tree.inputs.float(
        "Density",
        default_value=10.0,
        description="Point density used to distribute spikes over the sphere",
    )
    # 10.0 matches DistributePointsOnFaces' own default density (see
    # nodebpy/nodes/geometry/geometry.py DistributePointsOnFaces.__init__) -
    # a reasonable middle ground for a radius-1.0 sphere. The original
    # blendyt source had no call site fixing a specific value (it's a
    # standalone node-group function), so there was nothing concrete to
    # match against.

    # segments=1024/rings=1024 are carried over verbatim from the original
    # (`gs.uv_sphere(radius=size, segments=1024, rings=1024)`) - a
    # deliberately high-resolution sphere for smooth point distribution.
    # nodebpy's own UVSphere default is a much coarser 32/16; keeping the
    # original's explicit values here since the task only asked to expose
    # `size`/`density` as tree inputs, not resolution.
    sphere = g.UVSphere(radius=size, segments=1024, rings=1024)

    points = g.DistributePointsOnFaces(mesh=sphere.o.mesh, density=density)

    # `gs.mesh_line()` in the original was called with no arguments at all.
    # nodebpy's bare MeshLine() default is count=10, offset=None (which
    # leaves Blender's own node default of Offset=(0, 0, 1) in place) -
    # i.e. a 9-unit-long line of 10 vertices. That's wildly oversized next
    # to a radius-1.0 sphere and would not read as "spikes" at all, so
    # unlike the sphere's resolution above, this default looks clearly
    # wrong to carry over unchanged. Judgment call: use a short 2-point,
    # single-segment line (count=2) with a small offset along local Z
    # (0.1 units) instead - a short needle/spike, still built along Z so
    # AlignRotationToVector's default axis="Z" below rotates it to point
    # outward from the sphere correctly.
    line = g.MeshLine(count=2, offset=(0.0, 0.0, 0.1))

    rotation = g.AlignRotationToVector(vector=g.Position().o.position)

    instances = g.InstanceOnPoints(
        points=points.o.points,
        instance=line.o.mesh,
        rotation=rotation.o.rotation,
    )

    # Multiple differently-named geometry outputs on one tree - confirmed
    # fine: each `tree.outputs.geometry(name)` call creates its own
    # interface socket (nodebpy/builder/tree.py SocketContext._add_socket
    # appends a new NodeTreeInterfaceSocket every call) wrapped to its own
    # Group Output input socket by identifier, so the three calls below
    # don't collide with each other.
    tree.outputs.geometry("Geometry") >> instances.o.instances
    tree.outputs.geometry("Points") >> points.o.points
    tree.outputs.geometry("BasicGeometry") >> sphere.o.mesh
