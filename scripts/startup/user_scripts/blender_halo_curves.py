"""
Import a halo ancestry CSV (from ytree_ancestors_csv.py) as static geometry
for Geometry Nodes to drive - the sibling script, blender_halo_import.py,
instead pre-animates a visible, keyframed scene; this one does none of that.
It builds ONE Curves object holding one curve per branch (the main branch's
chain of main progenitors, plus every branch that merges into it), with no
animation, no materials, and no visibility keyframes at all - everything a
Geometry Nodes setup would need to reconstruct and drive that itself is
exposed as attributes instead. Every field parsed from the CSV is included,
not just a curated subset:

Per-point (POINT domain) - one point per snapshot row, in branch order,
plus one synthetic point for a merging branch's "glide into descendant and
vanish" instant (see below):
    position         the halo's (centered, scaled) position - the curve's
                      own point coordinates, readable as a normal attribute
                      too
    raw_position      x/y/z straight from the CSV, uncentered and unscaled
    desc_position      desc_x/desc_y/desc_z straight from the CSV
    t_norm            normalized GLOBAL time, 0-1 across the full
                      frame_start..frame_end range (not per-branch) - so it
                      composes directly with a "current time" computed in
                      Geometry Nodes (Scene Time -> Map Range against
                      frame_start/frame_end) without any extra remapping
                      needed to compare against any point on any curve
    frame             the same instant in absolute timeline frames, in case
                      frame-space is more convenient than 0-1 for some node
    radius            pre-computed sphere radius using the same mass-
                      scaling formula as blender_halo_import.py
                      (M / M_final)^(1/3), clamped to Min Radius - a
                      convenience default; roll your own formula from mass
                      if you want something different
    uid, snapshot, desc_snapshot, scale_factor, desc_scale_factor, time,
    mass, desc_mass, desc_time
                      every other CSV column that varies per point.
                      branch_id/main_branch do NOT get a point-domain copy
                      - Blender attribute names are unique per data-block
                      regardless of domain, and both are already exposed
                      at CURVE domain below (branch_id, is_main) - genuinely
                      redundant at POINT domain anyway, since they're
                      constant across every point in a branch

The synthetic merge-endpoint point (appended only to a branch that merges,
i.e. is_main is false and the last row's desc_snapshot is valid): the
CSV's own desc_* columns already describe exactly this instant - where/
when the branch merged - so this point's x/y/z/time/snapshot/scale_factor
are promoted straight from the last real row's desc_x/desc_y/desc_z/
desc_time/desc_snapshot/desc_scale_factor (this point IS that merge
instant, so its position should connect there), and ITS OWN desc_* fields
are set to -1 (this CSV's own "no descendant" sentinel - there's no known
descendant of a descendant here). uid carries over unchanged (same halo
identity).

mass at that point defaults to the same promotion (desc_mass - the
descendant's, i.e. post-merger, mass), which means the branch jumps to
looking as massive as the merged result right before it vanishes, rather
than shrinking away - two consumers of the radius/mass attributes both
sized for close to the full merged mass then briefly overlap. The Taper
Mass At Merge option decouples this: position still promotes to the
descendant's, but mass instead ramps linearly to 0 over that last
segment (Sample Curve interpolates POINT attributes linearly between
points, so one point at mass 0 is enough to produce a straight-line
taper - radius_of()'s existing Min Radius floor keeps that from ever
rendering as a literal zero-size point).

Taper Mass At Merge also inserts a matching point into the MAIN branch,
one snapshot before wherever it's about to absorb a merging branch: same
position as its own real row there (that part of its trajectory is
real), but mass reduced by everything about to be absorbed, and time
pulled back to match the merging branch's own last real point - so the
main branch's mass ramps up into its real post-merger value over the
same window the merging branch ramps down, rather than the main branch's
own mass just jumping between two real, possibly widely-spaced,
snapshots. If more than one branch merges into the main branch at the
same snapshot, their masses are summed and the earliest of their own
last-real-times is used as the ramp start.

Per-curve (CURVE domain) - one value per branch:
    branch_id         the CSV's own branch_id
    is_main           1 for the main branch, 0 otherwise - ALSO true by
                      construction that the main branch is always curve
                      index 0, so you don't need to filter on this at all
                      if index 0 is convenient
    merges            1 if this branch merges into another (a non-main
                      branch whose last row has a valid desc_snapshot), 0
                      otherwise
    appear_t          normalized global time (same 0-1 scale as t_norm)
                      when this branch's first point exists
    depart_t          normalized global time when this branch should stop
                      being shown - its merge instant if merges is 1, else
                      1.0

Run via this repo's Script Browser panel (3D Viewport sidebar > Script
Runner > Scripts > "Blender Halo Curves").
"""

import importlib.util
import os

import bpy
import numpy as np
import databpy as db

PARAMS = {
    "csv_path": {
        "type": "FILE_PATH",
        "default": "//ancestors.csv",
        "name": "Ancestors CSV",
        "description": "Halo ancestry CSV produced by ytree_ancestors_csv.py",
    },
    "object_name": {
        "type": "STRING",
        "default": "Halo_Curves",
        "name": "Object Name",
        "description": "Name for the created Curves object and data-block - one curve per branch, main branch always curve index 0",
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection to link the new object into (defaults to scene collection)",
    },
    "frame_start": {
        "type": "INT",
        "default": 1,
        "min": 0,
        "name": "Frame Start",
        "description": "Timeline frame the normalized time attributes (t_norm, appear_t, depart_t) treat as 0.0",
    },
    "frame_end": {
        "type": "INT",
        "default": 500,
        "min": 1,
        "name": "Frame End",
        "description": "Timeline frame the normalized time attributes treat as 1.0",
    },
    "time_axis": {
        "type": "ENUM",
        "default": "TIME",
        "items": [
            ("TIME", "Cosmic Time", "Normalize by the CSV's time column"),
            ("SCALE_FACTOR", "Scale Factor", "Normalize by the CSV's scale_factor column"),
            ("SNAPSHOT", "Snapshot", "Even spacing per output, regardless of the time between them"),
        ],
        "name": "Time Axis",
        "description": "Which column defines t_norm/frame/appear_t/depart_t",
    },
    "center": {
        "type": "ENUM",
        "default": "FINAL",
        "items": [
            ("FINAL", "Final Halo", "Hold the final halo fixed at the origin"),
            ("MAIN_BRANCH", "Main Branch", "Subtract the main branch's position at each snapshot"),
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
        "description": "Only used when Auto-Fit Extent is off - fixed position multiplier",
    },
    "final_radius": {
        "type": "FLOAT",
        "default": 0.25,
        "min": 0.0001,
        "name": "Final Radius",
        "description": "Radius attribute value for the final halo - others scale as (M / M_final)^(1/3)",
    },
    "min_radius": {
        "type": "FLOAT",
        "default": 0.01,
        "min": 0.0,
        "name": "Min Radius",
        "description": "Floor on the radius attribute",
    },
    "taper_mass_at_merge": {
        "type": "BOOL",
        "default": False,
        "name": "Taper Mass At Merge",
        "description": "Cross-fade mass across a merger instead of jumping it: the merging branch ramps its mass to 0 (instead of jumping to the descendant's post-merger mass) while the main branch it merges into ramps up into its real post-merger mass over that same window, instead of jumping there itself",
    },
}

# Point-domain scalar attribute names copied straight from a CSV row (see
# _extract_point_values) - everything the CSV has that isn't already
# handled separately (position/raw_position/desc_position as vectors;
# t_norm/frame/radius as derived values).
#
# Deliberately does NOT include branch_id/main_branch: Blender attribute
# names must be unique per data-block regardless of domain, and both are
# already exposed at CURVE domain (branch_id, is_main below) - genuinely
# redundant here anyway, since they're constant across every point in a
# branch. Confirmed the hard way: writing "branch_id" at POINT domain
# first, then again at CURVE domain, raised a size-mismatch error - the
# second write was validated against the first (wrong-domain) attribute's
# element count instead of creating a separate one.
_INT_POINT_ATTRS = {"uid", "snapshot", "desc_snapshot"}
_FLOAT_POINT_ATTRS = {"scale_factor", "desc_scale_factor", "time", "mass", "desc_mass", "desc_time"}


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


def _extract_point_values(row):
    """Every CSV-derived scalar for one point, keyed by output attribute
    name - shared by real rows and the synthetic merge-endpoint row (see
    _synthetic_merge_row)."""
    return {name: row[name] for name in _INT_POINT_ATTRS | _FLOAT_POINT_ATTRS}


def _synthetic_merge_row(last, taper_mass=False):
    """Build a full point-row dict for the synthetic "glide into
    descendant and vanish" point appended to a merging branch - takes the
    last real CSV row and promotes its desc_* fields (the merge instant's
    own position/time/snapshot/scale_factor) into the primary fields,
    since this point IS that merge instant. This point's own desc_* fields
    are set to -1 (this CSV's own "no descendant" sentinel) - there's no
    known descendant of a descendant here.

    mass is promoted the same way (the descendant's, post-merger mass) by
    default, matching position - unless taper_mass is set, in which case
    it's 0 instead, so the branch's mass/radius ramps out over its last
    segment rather than jumping up to the merged result's mass right
    before it vanishes.
    """
    row = dict(last)
    for k in ("x", "y", "z", "time", "snapshot", "scale_factor"):
        row[k] = last[f"desc_{k}"]
    row["mass"] = 0.0 if taper_mass else last["desc_mass"]
    for k in ("desc_x", "desc_y", "desc_z", "desc_mass", "desc_time", "desc_snapshot", "desc_scale_factor"):
        row[k] = -1
    return row


def _pre_absorption_row(main_row, ramp_from_row, absorbed_mass):
    """Synthetic point inserted into the MAIN branch just before a real row
    where it absorbs one or more merging branches (the other half of
    taper_mass) - same position and everything else as main_row (that
    part of the main branch's own trajectory is real, unaffected), but
    time/scale_factor/snapshot are pulled back to ramp_from_row's (the
    earliest-in-time of the branches merging here, so the ramp starts in
    sync with when that branch begins tapering down), and mass is
    main_row's own mass minus everything about to be absorbed - so it
    rises into main_row's real value instead of jumping there. Floors at
    0 (real catalog mass isn't always perfectly additive across a merger,
    so the subtraction could in principle go negative) - radius_of()'s
    Min Radius floor handles the rest.
    """
    row = dict(main_row)
    for k in ("time", "snapshot", "scale_factor"):
        row[k] = ramp_from_row[k]
    row["mass"] = max(0.0, main_row["mass"] - absorbed_mass)
    return row


def build(halos, params):
    object_name = params["object_name"]
    target_collection = params["target_collection"] or bpy.context.scene.collection
    frame_start = params["frame_start"]
    frame_end = params["frame_end"]
    time_axis = params["time_axis"].lower()
    center_mode = "main_branch" if params["center"] == "MAIN_BRANCH" else "final"
    fit_extent = params["fit_extent"] if params["use_fit_extent"] else None
    position_scale = params["position_scale"]
    final_radius = params["final_radius"]
    min_radius = params["min_radius"]
    taper_mass = params["taper_mass_at_merge"]

    final = max(halos, key=lambda h: h["scale_factor"])
    m_final = final["mass"]

    # Main-branch position per snapshot, for center_mode == "main_branch".
    centers = {h["snapshot"]: (h["x"], h["y"], h["z"]) for h in halos if h["main_branch"]}

    def centered(x, y, z, snapshot):
        cx, cy, cz = centers[snapshot] if center_mode == "main_branch" else (final["x"], final["y"], final["z"])
        return (x - cx, y - cy, z - cz)

    scale = position_scale
    if fit_extent is not None:
        points = [centered(h["x"], h["y"], h["z"], h["snapshot"]) for h in halos]
        points += [centered(h["desc_x"], h["desc_y"], h["desc_z"], h["desc_snapshot"])
                   for h in halos if h["desc_snapshot"] >= 0]
        extent = max(abs(c) for p in points for c in p)
        scale = fit_extent / extent if extent > 0 else 1.0
        print(f"Scaling positions by {scale:g} (max offset {extent:g} -> {fit_extent:g})")

    def location(x, y, z, snapshot):
        return tuple(c * scale for c in centered(x, y, z, snapshot))

    def radius_of(mass):
        return max(min_radius, final_radius * (mass / m_final) ** (1 / 3))

    key = {"time": "time", "scale_factor": "scale_factor", "snapshot": "snapshot"}[time_axis]
    t0 = min(h[key] for h in halos)
    t1 = max(h[key] for h in halos)

    def t_norm_of(t):
        return (t - t0) / (t1 - t0) if t1 > t0 else 0.0

    def frame_of(t):
        return frame_start + t_norm_of(t) * (frame_end - frame_start)

    branches = {}
    for h in halos:
        branches.setdefault(h["branch_id"], []).append(h)

    # Main branch always ends up as curve index 0; the rest follow sorted
    # by branch_id, for a stable, reproducible ordering across reruns.
    branch_ids_sorted = sorted(
        branches.keys(),
        key=lambda bid: (0 if branches[bid][0]["main_branch"] else 1, bid),
    )

    # taper_mass, main-branch side: for every main-branch snapshot that's
    # some other branch's merge target, work out the total mass about to
    # be absorbed there (every branch merging in at that snapshot, summed
    # - more than one can land on the same snapshot) and the earliest of
    # those branches' own last-real-point time (so the main branch's rise
    # starts in sync with the earliest one's own fall). Keyed by snapshot
    # since that's what a main-branch row is matched against below;
    # relies on the main branch actually having a row at that exact
    # snapshot; if not, that absorption entry is just never consumed.
    absorbed_by_snapshot = {}
    if taper_mass:
        for branch_id, rows in branches.items():
            rows_sorted = sorted(rows, key=lambda h: h["scale_factor"])
            if rows_sorted[0]["main_branch"]:
                continue
            last = rows_sorted[-1]
            if last["desc_snapshot"] < 0:
                continue
            target = last["desc_snapshot"]
            total, ramp_from = absorbed_by_snapshot.get(target, (0.0, last))
            total += last["mass"]
            if last[key] < ramp_from[key]:
                ramp_from = last
            absorbed_by_snapshot[target] = (total, ramp_from)

    positions = []
    raw_positions = []
    desc_positions = []
    point_attrs = {name: [] for name in ("t_norm", "frame", "radius", *_INT_POINT_ATTRS, *_FLOAT_POINT_ATTRS)}
    curve_lengths = []
    curve_attrs = {"branch_id": [], "is_main": [], "merges": [], "appear_t": [], "depart_t": []}

    def add_point(row):
        positions.append(location(row["x"], row["y"], row["z"], row["snapshot"]))
        raw_positions.append((row["x"], row["y"], row["z"]))
        desc_positions.append((row["desc_x"], row["desc_y"], row["desc_z"]))
        t = row[key]
        point_attrs["t_norm"].append(t_norm_of(t))
        point_attrs["frame"].append(frame_of(t))
        point_attrs["radius"].append(radius_of(row["mass"]))
        for name, value in _extract_point_values(row).items():
            point_attrs[name].append(value)

    for branch_id in branch_ids_sorted:
        rows = sorted(branches[branch_id], key=lambda h: h["scale_factor"])
        is_main = rows[0]["main_branch"]

        n_before = len(positions)
        for h in rows:
            if is_main and h["snapshot"] in absorbed_by_snapshot:
                total_absorbed, ramp_from = absorbed_by_snapshot[h["snapshot"]]
                add_point(_pre_absorption_row(h, ramp_from, total_absorbed))
            add_point(h)

        last = rows[-1]
        merges = not is_main and last["desc_snapshot"] >= 0
        if merges:
            add_point(_synthetic_merge_row(last, taper_mass=taper_mass))

        curve_lengths.append(len(positions) - n_before)

        curve_attrs["branch_id"].append(branch_id)
        curve_attrs["is_main"].append(int(is_main))
        curve_attrs["merges"].append(int(merges))
        curve_attrs["appear_t"].append(t_norm_of(rows[0][key]))
        curve_attrs["depart_t"].append(t_norm_of(last[f"desc_{key}"]) if merges else 1.0)

    # Rebuilding from scratch each run is simplest for a varying point/curve
    # count - reuse the existing object (rather than orphaning + renaming)
    # if this script re-runs against the same object_name, matching
    # hdf5_to_curves.py's exact convention for this.
    existing_data = bpy.data.hair_curves.get(object_name)
    if existing_data is not None:
        bpy.data.hair_curves.remove(existing_data)
    curves_data = bpy.data.hair_curves.new(name=object_name)
    curves_data.add_curves(curve_lengths)

    obj = bpy.data.objects.get(object_name)
    if obj is None:
        obj = bpy.data.objects.new(object_name, curves_data)
        target_collection.objects.link(obj)
    elif obj.data != curves_data:
        obj.data = curves_data

    for name, values in (("position", positions), ("raw_position", raw_positions), ("desc_position", desc_positions)):
        db.store_named_attribute(
            obj,
            np.array(values, dtype=np.float32),
            name,
            atype=db.AttributeTypes.FLOAT_VECTOR,
            domain=db.AttributeDomains.POINT,
        )
    for name, values in point_attrs.items():
        dtype = np.int32 if name in _INT_POINT_ATTRS else np.float32
        db.store_named_attribute(obj, np.array(values, dtype=dtype), name, domain=db.AttributeDomains.POINT)
    for name, values in curve_attrs.items():
        dtype = np.int32 if name in ("branch_id", "is_main", "merges") else np.float32
        db.store_named_attribute(obj, np.array(values, dtype=dtype), name, domain=db.AttributeDomains.CURVE)

    print(
        f"Built {len(curve_lengths)} curves ({sum(curve_lengths)} points) "
        f"from {len(halos)} halos; main branch is curve index 0"
    )


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
