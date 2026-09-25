"""
Animate a halo ancestry CSV (from ytree_ancestors_csv.py) in Blender.

Each branch (a chain of main progenitors, grouped by branch_id) becomes one
sphere, keyframed at every snapshot it exists in.  A branch that merges gets
one last keyframe at its descendant's position and time (the desc_* columns),
where it shrinks to nothing, so it is visibly absorbed rather than popping
out.  Blender's F-curves then interpolate smoothly between the snapshots.

Run via this repo's Script Browser panel (3D Viewport sidebar > Script
Runner > Scripts > "Blender Halo Import") - every setting below is exposed
there as an input field, matching the PARAMS dict, rather than needing to be
edited into the file by hand.

See the sibling script blender_halo_curves.py for a different tactic on the
same CSV: instead of a pre-animated, keyframed scene, it builds one static
Curves object with per-point/per-curve attributes for Geometry Nodes to
read and drive itself - CSV loading is shared between the two via
_halo_csv_shared.py, one directory up.
"""

import importlib.util
import math
import os
from collections import defaultdict

import bpy

PARAMS = {
    "csv_path": {
        "type": "FILE_PATH",
        "default": "//ancestors.csv",
        "name": "Ancestors CSV",
        "description": "Halo ancestry CSV produced by ytree_ancestors_csv.py",
    },
    "frame_start": {
        "type": "INT",
        "default": 1,
        "min": 0,
        "name": "Frame Start",
        "description": "Timeline frame for the earliest snapshot",
    },
    "frame_end": {
        "type": "INT",
        "default": 500,
        "min": 1,
        "name": "Frame End",
        "description": "Timeline frame for the final halo",
    },
    "time_axis": {
        "type": "ENUM",
        "default": "TIME",
        "items": [
            ("TIME", "Cosmic Time", "Space keyframes by the CSV's time column"),
            ("SCALE_FACTOR", "Scale Factor", "Space keyframes by the CSV's scale_factor column"),
            ("SNAPSHOT", "Snapshot", "Even spacing per output, regardless of the time between them"),
        ],
        "name": "Time Axis",
        "description": "Which column drives the timeline",
    },
    "center": {
        "type": "ENUM",
        "default": "FINAL",
        "items": [
            ("FINAL", "Final Halo", "Hold the final halo fixed at the origin"),
            ("MAIN_BRANCH", "Main Branch", "Subtract the main branch's position at each snapshot, so the camera rides along"),
        ],
        "name": "Center",
        "description": "What stays fixed at the origin",
    },
    "use_fit_extent": {
        "type": "BOOL",
        "default": True,
        "name": "Auto-Fit Extent",
        "description": "Scale positions so the farthest halo sits at +/- Fit Extent, preserving aspect ratio. Disable to use Position Scale as a fixed multiplier instead",
    },
    "fit_extent": {
        "type": "FLOAT",
        "default": 5.0,
        "min": 0.0001,
        "name": "Fit Extent",
        "description": "Only used when Auto-Fit Extent is on - the farthest halo along any axis lands here, in Blender units",
    },
    "position_scale": {
        "type": "FLOAT",
        "default": 1000.0,
        "min": 0.0001,
        "name": "Position Scale",
        "description": "Only used when Auto-Fit Extent is off - fixed position multiplier (e.g. with CSV positions in Mpc/h, 1000 makes one Blender unit one kpc/h)",
    },
    "final_radius": {
        "type": "FLOAT",
        "default": 0.25,
        "min": 0.0001,
        "name": "Final Radius",
        "description": "Sphere radius, in Blender units, for the final halo - others scale as (M / M_final)^(1/3)",
    },
    "min_radius": {
        "type": "FLOAT",
        "default": 0.01,
        "min": 0.0,
        "name": "Min Radius",
        "description": "Floor on sphere radius, so low-mass halos stay visible",
    },
    "interpolation": {
        "type": "ENUM",
        "default": "BEZIER",
        "items": [
            ("BEZIER", "Bezier", "Smooth motion between snapshots"),
            ("LINEAR", "Linear", "See the raw snapshot-to-snapshot steps"),
        ],
        "name": "Interpolation",
        "description": "F-curve interpolation between keyframes",
    },
    "handle_type": {
        "type": "ENUM",
        "default": "AUTO_CLAMPED",
        "items": [
            ("AUTO_CLAMPED", "Auto Clamped", "Never overshoots a keyframe"),
            ("AUTO", "Auto", "Smoother, but can overshoot"),
        ],
        "name": "Handle Type",
        "description": "F-curve handle type for new keyframes",
    },
    "make_trails": {
        "type": "BOOL",
        "default": True,
        "name": "Make Trails",
        "description": "Also draw each branch's path as a static curve",
    },
    "collection_name": {
        "type": "STRING",
        "default": "Halo Import",
        "name": "Collection",
        "description": "Root collection to build into - holds two child collections, 'Halos' (the sphere objects) and 'Trails' (the static path curves)",
    },
}


def _load_sibling(module_name):
    """Load a module from scripts/startup/ (one directory up from
    user_scripts/) by file path - user_scripts/ files are loaded standalone
    by dynamic_script_runner.py (no parent package context), so a package-
    relative import doesn't work here. Same pattern as
    constant_mass_emission_times.py's _load_sibling.
    """
    path = os.path.join(os.path.dirname(__file__), "..", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_or_create_child_collection(parent, name):
    """Get or create a collection named `name` as a child of `parent` -
    scoped to `parent`'s own children, NOT a global bpy.data.collections
    lookup by name (which would risk finding and re-attaching an
    unrelated same-named collection from elsewhere in the file - see
    country_wireframes.py's own fix for exactly this bug class earlier in
    this repo's history)."""
    existing = parent.children.get(name)
    if existing is not None:
        return existing
    coll = bpy.data.collections.new(name)
    parent.children.link(coll)
    return coll


def build(halos, params):
    frame_start = params["frame_start"]
    frame_end = params["frame_end"]
    time_axis = params["time_axis"].lower()
    center_mode = "main_branch" if params["center"] == "MAIN_BRANCH" else "final"
    fit_extent = params["fit_extent"] if params["use_fit_extent"] else None
    position_scale = params["position_scale"]
    final_radius = params["final_radius"]
    min_radius = params["min_radius"]
    interpolation = params["interpolation"]
    handle_type = params["handle_type"]
    make_trails = params["make_trails"]
    collection_name = params["collection_name"]

    final = max(halos, key=lambda h: h["scale_factor"])
    m_final = final["mass"]

    # Main-branch position per snapshot, for center_mode == "main_branch".
    centers = {h["snapshot"]: (h["x"], h["y"], h["z"]) for h in halos if h["main_branch"]}

    def centered(x, y, z, snapshot):
        cx, cy, cz = centers[snapshot] if center_mode == "main_branch" else (final["x"], final["y"], final["z"])
        return (x - cx, y - cy, z - cz)

    scale = position_scale
    if fit_extent is not None:
        # Include merger endpoints, which are keyframed too.
        points = [centered(h["x"], h["y"], h["z"], h["snapshot"]) for h in halos]
        points += [centered(h["desc_x"], h["desc_y"], h["desc_z"], h["desc_snapshot"])
                   for h in halos if h["desc_snapshot"] >= 0]
        extent = max(abs(c) for p in points for c in p)
        scale = fit_extent / extent if extent > 0 else 1.0
        print(f"Scaling positions by {scale:g} (max offset {extent:g} -> {fit_extent:g})")

    def location(x, y, z, snapshot):
        return tuple(c * scale for c in centered(x, y, z, snapshot))

    def radius(mass):
        return max(min_radius, final_radius * (mass / m_final) ** (1 / 3))

    key = {"time": "time", "scale_factor": "scale_factor", "snapshot": "snapshot"}[time_axis]
    t0 = min(h[key] for h in halos)
    t1 = max(h[key] for h in halos)

    def frame(t):
        return frame_start + (t - t0) / (t1 - t0) * (frame_end - frame_start)

    branches = defaultdict(list)
    for h in halos:
        branches[h["branch_id"]].append(h)

    root = _get_or_create_child_collection(bpy.context.scene.collection, collection_name)
    halos_coll = _get_or_create_child_collection(root, "Halos")
    trails_coll = _get_or_create_child_collection(root, "Trails") if make_trails else None

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0)
    template = bpy.context.active_object
    mesh = template.data
    bpy.data.objects.remove(template)

    materials = {}
    for name, color in (("main_branch", (1.0, 0.55, 0.1, 1.0)), ("merger", (0.2, 0.5, 1.0, 1.0))):
        mat = bpy.data.materials.get(f"halo_{name}") or bpy.data.materials.new(f"halo_{name}")
        mat.diffuse_color = color
        materials[name] = mat
    mesh.materials.append(materials["merger"])

    prefs = bpy.context.preferences.edit
    saved = prefs.keyframe_new_interpolation_type, prefs.keyframe_new_handle_type
    prefs.keyframe_new_interpolation_type = interpolation
    prefs.keyframe_new_handle_type = handle_type
    try:
        for branch_id, rows in branches.items():
            rows.sort(key=lambda h: h["scale_factor"])
            is_main = rows[0]["main_branch"]

            # The sphere mesh is shared, so the material lives on the object.
            obj = bpy.data.objects.new(f"halo_{branch_id}", mesh)
            obj.material_slots[0].link = "OBJECT"
            obj.material_slots[0].material = materials["main_branch" if is_main else "merger"]
            halos_coll.objects.link(obj)

            path = []
            for h in rows:
                f = frame(h[key])
                obj.location = location(h["x"], h["y"], h["z"], h["snapshot"])
                obj.scale = (radius(h["mass"]),) * 3
                obj.keyframe_insert("location", frame=f)
                obj.keyframe_insert("scale", frame=f)
                path.append(tuple(obj.location))

            last = rows[-1]
            merges = not is_main and last["desc_snapshot"] >= 0
            if merges:
                # Glide into the descendant and vanish there.
                f = frame(last[f"desc_{key}"])
                obj.location = location(last["desc_x"], last["desc_y"], last["desc_z"], last["desc_snapshot"])
                obj.scale = (0.0, 0.0, 0.0)
                obj.keyframe_insert("location", frame=f)
                obj.keyframe_insert("scale", frame=f)
                path.append(tuple(obj.location))

            # Hidden before the branch first appears and after it merges.
            first_frame = frame(rows[0][key])
            end_frame = frame(last[f"desc_{key}"]) if merges else None
            for prop in ("hide_viewport", "hide_render"):
                setattr(obj, prop, first_frame > frame_start)
                obj.keyframe_insert(prop, frame=frame_start)
                setattr(obj, prop, False)
                obj.keyframe_insert(prop, frame=math.floor(first_frame))
                if end_frame is not None:
                    setattr(obj, prop, True)
                    obj.keyframe_insert(prop, frame=math.ceil(end_frame) + 1)

            if is_main:
                # A clearly-named, easy-to-find linked duplicate of the main
                # branch's halo, placed directly in the root collection
                # (not "Halos") so it's reachable without expanding a
                # sub-collection - NOT a rename of halo_{branch_id} itself,
                # so anything that references halos by their numeric
                # branch_id name is unaffected. Shares the same mesh
                # data-block, same as every halo_* object already does -
                # but unlike a static trail's Curve points, a halo's motion
                # is OBJECT-level keyframes (location/scale/hide_*), not
                # mesh data, so sharing the mesh alone wouldn't move this
                # duplicate at all. Sharing `obj`'s Action makes it animate
                # in perfect lockstep with the real halo_{branch_id} object
                # - but action alone isn't enough: Blender's newer layered-
                # Action model (5.x) also needs action_slot assigned to the
                # SAME slot `obj` uses, or the duplicate just sits at its
                # raw, unanimated default transform instead of evaluating
                # any keyframes at all - confirmed directly (frame_set()
                # left it at (0,0,0) with only `.action` set, matching only
                # by coincidence wherever the real object also happened to
                # be at (0,0,0)).
                main_halo = bpy.data.objects.new("halo_main", mesh)
                main_halo.material_slots[0].link = "OBJECT"
                main_halo.material_slots[0].material = materials["main_branch"]
                main_halo.animation_data_create()
                main_halo.animation_data.action = obj.animation_data.action
                main_halo.animation_data.action_slot = obj.animation_data.action_slot
                root.objects.link(main_halo)

            if make_trails and len(path) > 1:
                curve = bpy.data.curves.new(f"trail_{branch_id}", "CURVE")
                curve.dimensions = "3D"
                spline = curve.splines.new("POLY")
                spline.points.add(len(path) - 1)
                for p, co in zip(spline.points, path):
                    p.co = (*co, 1.0)
                trail = bpy.data.objects.new(f"trail_{branch_id}", curve)
                curve.materials.append(obj.material_slots[0].material)
                trails_coll.objects.link(trail)

                if is_main:
                    # Same idea as halo_main above: a linked duplicate (not
                    # a rename) of the main branch's trail, placed directly
                    # in the root collection instead of "Trails" so it's
                    # right next to halo_main. Shares the same Curve
                    # data-block (bpy.data.objects.new(name, curve), not
                    # curve.copy()), so editing/smoothing this object's
                    # points edits the real path data too.
                    main_trail = bpy.data.objects.new("trail_main", curve)
                    root.objects.link(main_trail)
    finally:
        prefs.keyframe_new_interpolation_type, prefs.keyframe_new_handle_type = saved

    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = frame_start, frame_end
    print(f"Built {len(branches)} branches from {len(halos)} halos")


def execute(context, params):
    halo_csv = _load_sibling("_halo_csv_shared")

    csv_path = bpy.path.abspath(params["csv_path"])
    if not os.path.exists(csv_path):
        raise ValueError(f"Ancestors CSV not found: {csv_path}")

    halos = halo_csv.load(csv_path)
    if not halos:
        raise ValueError(f"No halo rows found in {csv_path}")

    build(halos, params)

    return {"FINISHED"}
