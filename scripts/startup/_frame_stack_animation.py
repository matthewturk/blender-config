import bpy
import numpy as np
import databpy as db

# Shared logic behind user_scripts/bgeo_import.py and
# user_scripts/frame_stack_to_object.py - both build ONE animated point-cloud
# object from a list of per-frame (N, 3) position arrays, using Blender shape
# keys. Ported from blendyt's halo_importer.py (a real, working scratch
# script that did this for a directory of per-frame halo-particle CSVs):
# create the object at frame 0's positions, add a "Basis" shape key, set
# use_relative = False, then add one more shape key per subsequent frame and
# foreach_set its "co" to that frame's flattened positions. The evaluated
# frame is then driven by the Basis shape key's "Evaluation Time" (a driver
# expression like `#frame * 2`, matching halo_importer.py's own note) -
# that's a per-use decision left to whoever builds/animates the object, not
# something this helper sets up.
#
# Import this via the repo's usual "_load_sibling" pattern (see
# user_scripts/constant_mass_emission_times.py) rather than a package-
# relative import: user_scripts/ files are loaded one at a time by
# dynamic_script_runner.py via importlib.util.spec_from_file_location, with
# no parent package context, so `from . import x` doesn't work from inside
# them.
#
# Kept out of user_scripts/ itself (one directory up, in scripts/startup/) so
# dynamic_script_runner.py's directory scans (which only look for a
# PARAMS+execute pair) never mistake this for a runnable script of its own.


def build_animated_point_object(name, frames, target_collection, static_point_attrs=None):
    """Build (or update) one animated point-cloud object named `name`.

    Parameters
    ----------
    name : str
        Name for the object (and its mesh data-block).
    frames : list of (N, 3) float arrays
        One array per animation frame, all with the same N - point N must
        refer to the same physical particle in every frame (e.g. each
        frame's rows already sorted consistently before calling this).
        Callers must guarantee this; it's checked defensively below only to
        fail clearly rather than silently corrupt/misalign shape keys.
    target_collection : bpy.types.Collection
        Collection to link a newly-created object into. Ignored when
        reusing an existing object (its current collection membership is
        left alone, matching hdf5_to_curves.py's existing-object handling).
    static_point_attrs : dict, optional
        {attr_name: array} of additional per-point attributes to store via
        databpy.store_named_attribute - static (first-frame-only, not
        animated across frames), matching hdf5_to_curves.py's point
        attribute storage.

    Returns
    -------
    bpy.types.Object
        The created or updated object.
    """
    if not frames:
        raise ValueError("build_animated_point_object requires at least one frame")

    positions0 = np.asarray(frames[0], dtype=np.float32)
    n_points = positions0.shape[0]
    for i, frame in enumerate(frames):
        if frame.shape[0] != n_points:
            raise ValueError(
                f"All frames must have the same point count to animate via "
                f"shape keys; frame 0 has {n_points} points, frame {i} has "
                f"{frame.shape[0]}"
            )

    # Rebuilding the mesh data-block from scratch each run is simplest for a
    # point count that can vary between reruns (same rationale as
    # hdf5_to_curves.py's hair_curves handling) - it also discards any shape
    # keys left over from a previous run automatically, since shape keys
    # belong to the mesh data-block being removed here, not the new one, so
    # a rerun with a different frame count (or point count) never leaves
    # stale/mismatched shape keys behind.
    existing_mesh = bpy.data.meshes.get(name)
    if existing_mesh is not None:
        bpy.data.meshes.remove(existing_mesh)

    obj = bpy.data.objects.get(name)
    if obj is None:
        # No existing object to reuse - databpy.create_object (as used by
        # the original halo_importer.py) builds both the mesh and the
        # object in one call.
        obj = db.create_object(positions0, name=name, collection=target_collection)
    else:
        # An object with this name already exists from a previous run -
        # reuse its identity (keeps any modifiers/materials attached to it
        # intact) rather than letting create_object make a second,
        # auto-suffixed object. Build a fresh mesh and swap it in - the
        # same get-or-create-then-swap-.data idiom hdf5_to_curves.py uses
        # for its hair_curves data-block.
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices=positions0, edges=[], faces=[])
        mesh.update()
        obj.data = mesh

    if len(frames) == 1:
        # No animation to build - a single frame is just a static point
        # cloud; forcing a meaningless single "Basis"-only shape key here
        # would be needless machinery for something that isn't animated.
        _store_static_attrs(obj, static_point_attrs)
        return obj

    obj.shape_key_add(name="Basis")
    obj.data.shape_keys.use_relative = False
    for frame in frames[1:]:
        new_shape_key = obj.shape_key_add(from_mix=False)
        new_shape_key.points.foreach_set("co", np.asarray(frame, dtype=np.float32).flatten())

    _store_static_attrs(obj, static_point_attrs)
    return obj


def _store_static_attrs(obj, static_point_attrs):
    if not static_point_attrs:
        return
    for attr_name, arr in static_point_attrs.items():
        db.store_named_attribute(
            obj, np.asarray(arr), attr_name, domain=db.AttributeDomains.POINT
        )
