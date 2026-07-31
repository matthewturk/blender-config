import os
import importlib.util

import bpy
import numpy as np
import databpy as db

# Given a time series of (time, mass-shipped) point-attribute pairs on some
# object, computes the times at which a sequence of constant-mass "particles"
# (e.g. spheres, each representing a fixed volume of goods) should be
# emitted - so that a variable *number* of them per unit time reproduces the
# same total shipped mass over time, instead of a fixed emission rate with a
# variable size per particle. See pchip.py in the repo root for the reference
# algorithm this mirrors, and constant_mass_core.py (one level up, in
# scripts/startup/) for the actual numeric implementation - shared with the
# live-tracking version of this tool, constant_mass_emission_generator.py.
#
# Algorithm (implemented in constant_mass_core.compute_emission_times):
#   1. Build a monotonic cumulative-mass curve M(t): each (x_i, y_i) point is
#      treated as "y_i additional mass had arrived by time x_i", so M is the
#      running cumsum of y, sorted by x. PCHIP-interpolating this needs one
#      time node *before* the first data point, anchored at M=0 - without it,
#      any target mass below y_0 has no valid root, and the whole first
#      stretch of shipments (everything that arrived "by" the first recorded
#      time) would silently go unrepresented. That anchor time is
#      extrapolated backward from the first observed spacing: 2*x_0 - x_1.
#   2. Pick a constant particle mass m' - either given directly ("Mass Per
#      Sphere"), or derived from a target count ("Total Spheres": total_mass
#      / count).
#   3. Split total mass into k_max = floor(total_mass / m') whole particles.
#      Target each one's cumulative-mass threshold at its *midpoint*
#      ((k - 0.5) * m') rather than its edge - this halves the systematic
#      discretization bias versus targeting edges. Any leftover mass below
#      one full particle (at both the start and the end) is not emitted.
#   4. Solve M(t) == target for t, per target. PchipInterpolator.solve()
#      inverts the interpolant directly (it's a real root-finder built into
#      scipy for piecewise polynomials) - no manual iteration needed.
#
# Live-update note: if you'd rather this stay in sync automatically whenever
# the source object's data changes, see constant_mass_emission_generator.py -
# a separate, always-on tool (Object Properties > Constant-Mass Emission
# panel) that reruns this same computation via a depsgraph_update_post
# handler instead of you clicking a button. This script is still useful for
# a one-off, explicit export under a chosen name/collection.
#
# Fully-in-nodes note: Geometry Nodes has no built-in monotonic Hermite
# interpolation and no built-in equation solver. Repeat Zones do give it
# genuine data-dependent iteration, so a from-scratch bisection solver over a
# hand-rolled Hermite reconstruction (similar in spirit to the non-uniform
# formula in ppm_1d.py) is mechanically possible - but it would need to
# reimplement both PCHIP's slope construction *and* an iterative root solver
# from scratch, which is a much larger undertaking than this script for a
# much less certain result. Not worth it - both this script and the live
# generator above are cheap to rerun/react automatically already.


def _load_sibling(module_name):
    path = os.path.join(os.path.dirname(__file__), "..", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_core = _load_sibling("constant_mass_core")
_geo = _load_sibling("constant_mass_geometry_io")

PARAMS = {
    "source_object": {
        "type": "OBJECT",
        "default": None,
        "name": "Source Object",
        "description": "Object (Mesh or Curves) whose point attributes hold the time series - e.g. the output of sqlite_to_object.py",
    },
    "x_attribute": {
        "type": "STRING",
        "default": "x",
        "name": "Time Attribute",
        "description": "Point attribute holding the timestamp/year for each row (may have gaps, need not be pre-sorted)",
    },
    "y_attribute": {
        "type": "STRING",
        "default": "y",
        "name": "Mass Attribute",
        "description": "Point attribute holding the amount shipped at each timestamp (must be >= 0 everywhere)",
    },
    "mass_interval": {
        "type": "FLOAT",
        "default": 1.0,
        "name": "Mass Per Sphere",
        "description": "Constant mass represented by each emitted sphere. Ignored if 'Total Spheres' below is > 0",
    },
    "num_spheres": {
        "type": "INT",
        "default": 100,
        "name": "Total Spheres",
        "description": (
            "If > 0, derive the mass-per-sphere as total_mass / this count "
            "instead of using 'Mass Per Sphere' directly - the default (100) "
            "is scale-invariant regardless of your mass data's units/"
            "magnitude, unlike a fixed 'Mass Per Sphere', which can silently "
            "imply millions of spheres (and a very slow computation) if left "
            "at a value far too small for your data's actual scale"
        ),
    },
    "object_name": {
        "type": "STRING",
        "default": "Emission_Times",
        "name": "Object Name",
        "description": "Name for the created object and data-block",
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection to link the new object into (defaults to scene collection)",
    },
    "output_type": {
        "type": "ENUM",
        "default": "CURVES",
        "items": [
            ("MESH", "Mesh", "Create a Mesh object, one vertex per emitted sphere"),
            ("CURVES", "Curves", "Create a single-spline Curves object, one point per emitted sphere"),
        ],
        "name": "Output Type",
        "description": "Which kind of object to build",
    },
    "debug": {
        "type": "BOOL",
        "default": False,
        "name": "Debug Output",
        "description": "Print step-by-step progress and timing to the system console",
    },
}


def _read_point_attribute(obj, context, name):
    depsgraph = context.evaluated_depsgraph_get()
    return _geo.read_point_attribute(obj, depsgraph, name)


def _write_float_attribute(obj, name, values):
    db.store_named_attribute(
        obj, np.asarray(values, dtype=np.float32), name,
        atype=db.AttributeTypes.FLOAT, domain=db.AttributeDomains.POINT,
    )


def _write_int_attribute(obj, name, values):
    db.store_named_attribute(
        obj, np.asarray(values, dtype=np.int32), name,
        atype=db.AttributeTypes.INT, domain=db.AttributeDomains.POINT,
    )


def execute(context, params):
    obj = params["source_object"]
    if obj is None:
        raise ValueError("No source object given")

    x_attribute = params["x_attribute"].strip()
    y_attribute = params["y_attribute"].strip()
    object_name = params["object_name"]
    target_collection = params["target_collection"] or context.scene.collection
    output_type = params["output_type"]

    debug = params["debug"]
    log = (lambda msg: print(f"[constant_mass_emission_times] {msg}")) if debug else (lambda msg: None)

    log(f"reading '{x_attribute}'/'{y_attribute}' from '{obj.name}'")
    x = _read_point_attribute(obj, context, x_attribute)
    y = _read_point_attribute(obj, context, y_attribute)
    log(f"read {len(x)} rows")

    emission_times, target_masses, particle_mass = _core.compute_emission_times(
        x, y, params["mass_interval"], params["num_spheres"], log=log
    )
    k_max = len(emission_times)
    total_mass = float(np.sum(y))

    n_points = k_max
    zeros = np.zeros((n_points, 3), dtype=np.float32)

    if output_type == "MESH":
        existing_data = bpy.data.meshes.get(object_name)
        if existing_data is not None:
            bpy.data.meshes.remove(existing_data)
        obj_data = bpy.data.meshes.new(name=object_name)
        obj_data.from_pydata(zeros.tolist(), [], [])
        obj_data.update()
    else:
        existing_data = bpy.data.hair_curves.get(object_name)
        if existing_data is not None:
            bpy.data.hair_curves.remove(existing_data)
        obj_data = bpy.data.hair_curves.new(name=object_name)
        obj_data.add_curves([n_points])

    out_obj = bpy.data.objects.get(object_name)
    if out_obj is None:
        out_obj = bpy.data.objects.new(object_name, obj_data)
        target_collection.objects.link(out_obj)
    elif out_obj.data != obj_data:
        out_obj.data = obj_data

    if output_type == "CURVES":
        db.store_named_attribute(
            out_obj, zeros, "position", atype=db.AttributeTypes.FLOAT_VECTOR, domain=db.AttributeDomains.POINT
        )

    _write_float_attribute(out_obj, "emission_time", emission_times)
    _write_float_attribute(out_obj, "cumulative_mass", target_masses)
    _write_int_attribute(out_obj, "sphere_index", np.arange(1, k_max + 1, dtype=np.int32))

    leftover = total_mass - k_max * particle_mass
    print(
        f"Built '{object_name}' ({output_type}): {n_points} spheres, "
        f"mass/sphere={particle_mass:.6g}, total mass={total_mass:.6g}, "
        f"leftover (< 1 sphere, not emitted)={leftover:.6g}"
    )
    return {"FINISHED"}
