import bpy

# Cycles render-cost audit, adapted to run through the Script Browser instead
# of pasting into the Scripting tab. Prints a read-only diagnostic report
# (device, sampling, light bounces, volumes, geometry, hair/particles,
# textures, output settings, shader cost signals, lights/world) - handy to
# run right before starting a real render. Output appears in the System
# Console (Window > Toggle System Console on Windows; launch from a
# terminal on macOS/Linux).
#
# Every Cycles/light property below is read defensively (falls back to
# "n/a" and skips the associated check) rather than accessed directly -
# Cycles X (Blender 4.0+) removed or renamed several properties this
# script's original form assumed exist (e.g. `feature_set`, the old
# Supported/Experimental toggle, is gone), and there's no single Blender
# version this needs to work across, so degrading gracefully per-property
# is more robust than hardcoding one version's exact API shape.
#
# "Apply Sampling Overrides" is off by default, so a plain run is still
# fully read-only (changes nothing). Turn it on to also write Max Samples /
# Adaptive Sampling / Noise Threshold / Resolution % straight from this
# panel - e.g. to drop to a fast low-res test pass, or dial in a
# stricter/looser noise threshold, without leaving this dialog to go find
# those settings in Render Properties.

PARAMS = {
    "apply_overrides": {
        "type": "BOOL",
        "default": False,
        "name": "Apply Sampling Overrides",
        "description": "If on, write the four settings below to the scene before running the audit. Off by default so a plain run stays read-only",
    },
    "max_samples": {
        "type": "INT",
        "default": 1024,
        "name": "Max Samples",
        "description": "Cycles max samples (only written if Apply Sampling Overrides is on)",
        "min": 1,
        "max": 100000,
    },
    "use_adaptive_sampling": {
        "type": "BOOL",
        "default": True,
        "name": "Use Adaptive Sampling",
        "description": "Only written if Apply Sampling Overrides is on",
    },
    "adaptive_threshold": {
        "type": "FLOAT",
        "default": 0.01,
        "name": "Noise Threshold",
        "description": "Cycles adaptive sampling noise threshold (only written if Apply Sampling Overrides is on)",
        "min": 0.0,
        "max": 1.0,
    },
    "resolution_percentage": {
        "type": "INT",
        "default": 100,
        "name": "Resolution %",
        "description": "Render resolution percentage - handy for a fast low-res test pass (only written if Apply Sampling Overrides is on)",
        "min": 1,
        "max": 100,
    },
}


def execute(context, params):
    scene = context.scene
    cy = scene.cycles
    prefs = context.preferences.addons.get("cycles")

    def g(obj, name, default=None):
        return getattr(obj, name, default) if obj is not None else default

    def fmt(value, na="n/a"):
        return na if value is None else value

    W = 78

    def head(t):
        print("\n" + "=" * W)
        print(t)
        print("=" * W)

    def flag(cond, msg):
        print(("  [!] " if cond else "  [ok] ") + msg)

    def unavailable(label):
        print(f"  [n/a] {label} not available in this Blender version")

    if params.get("apply_overrides"):
        applied = []
        if hasattr(cy, "samples"):
            cy.samples = params["max_samples"]
            applied.append(f"max_samples={cy.samples}")
        if hasattr(cy, "use_adaptive_sampling"):
            cy.use_adaptive_sampling = params["use_adaptive_sampling"]
            applied.append(f"use_adaptive_sampling={cy.use_adaptive_sampling}")
        if hasattr(cy, "adaptive_threshold"):
            cy.adaptive_threshold = params["adaptive_threshold"]
            applied.append(f"adaptive_threshold={cy.adaptive_threshold}")
        scene.render.resolution_percentage = params["resolution_percentage"]
        applied.append(f"resolution_percentage={scene.render.resolution_percentage}")
        print("Applied overrides: " + ", ".join(applied))

    # ---------------------------------------------------------------- device
    head("DEVICE")
    feature_set = g(cy, "feature_set")
    device = g(cy, "device")
    print(f"  Feature set:      {fmt(feature_set)}")
    print(f"  Device:           {fmt(device)}")
    if prefs:
        p = prefs.preferences
        print(f"  Compute backend:  {p.compute_device_type}")
        active = []
        for d in p.devices:
            if d.use:
                active.append(f"{d.name} ({d.type})")
        print(f"  Active devices:   {', '.join(active) if active else 'NONE'}")
        gpus = [d for d in p.devices if d.use and d.type != "CPU"]
        cpus = [d for d in p.devices if d.use and d.type == "CPU"]
        if device is not None:
            flag(device == "CPU", "Rendering on CPU" if device == "CPU"
                 else "Rendering on GPU")
        flag(bool(gpus and cpus),
             "CPU + GPU both active - CPU can bottleneck tile scheduling; "
             "try GPU only" if (gpus and cpus) else "Device mix is fine")

    if feature_set is not None:
        flag(feature_set == "EXPERIMENTAL",
             "Experimental feature set enabled (adaptive subdiv / true displacement "
             "available and expensive)" if feature_set == "EXPERIMENTAL"
             else "Supported feature set")
    else:
        unavailable("Feature set (Cycles X merged the old Supported/Experimental split)")

    # ---------------------------------------------------------------- sampling
    head("SAMPLING")
    samples = g(cy, "samples")
    adaptive_min_samples = g(cy, "adaptive_min_samples")
    use_adaptive_sampling = g(cy, "use_adaptive_sampling")
    adaptive_threshold = g(cy, "adaptive_threshold")
    time_limit = g(cy, "time_limit")
    use_light_tree = g(cy, "use_light_tree")

    print(f"  Max samples:          {fmt(samples)}")
    print(f"  Min samples:          {fmt(adaptive_min_samples)}")
    print(f"  Adaptive sampling:    {fmt(use_adaptive_sampling)}")
    print(f"  Noise threshold:      {fmt(adaptive_threshold)}")
    print(f"  Time limit:           {fmt(time_limit or ('none' if time_limit is not None else None))}")
    print(f"  Sampling pattern:     {fmt(g(cy, 'sampling_pattern'))}")
    print(f"  Light tree:           {fmt(use_light_tree)}")

    if use_adaptive_sampling and samples is not None and adaptive_min_samples is not None:
        print(
            f"  Effective per-pixel samples: adaptive, between "
            f"{adaptive_min_samples} and {samples} (a pixel stops "
            f"sampling early once its noise estimate drops below "
            f"{fmt(adaptive_threshold)})"
        )
    elif samples is not None:
        print(
            f"  Effective per-pixel samples: fixed at {samples} "
            "(adaptive sampling is off, so every pixel always uses the full count)"
        )
    else:
        unavailable("Effective per-pixel samples (samples property)")

    if use_adaptive_sampling is not None:
        flag(not use_adaptive_sampling,
             "Adaptive sampling OFF - you pay full samples on already-clean pixels"
             if not use_adaptive_sampling else "Adaptive sampling on")
    if samples is not None:
        flag(samples > 1024,
             f"Max samples {samples} is high; with a 0.01 noise threshold most "
             "landscape shots converge well before this"
             if samples > 1024 else f"Max samples {samples} is reasonable")
    if adaptive_threshold is not None:
        flag(adaptive_threshold < 0.005,
             f"Noise threshold {adaptive_threshold} is very strict - "
             "0.01 is usually indistinguishable and much faster"
             if adaptive_threshold < 0.005 else "Noise threshold reasonable")
    if use_light_tree is not None:
        flag(not use_light_tree,
             "Light tree OFF - slower convergence with many lights"
             if not use_light_tree else "Light tree on")

    # ---------------------------------------------------------------- bounces
    head("LIGHT PATHS  (biggest lever for foliage-heavy scenes)")
    max_bounces = g(cy, "max_bounces")
    diffuse_bounces = g(cy, "diffuse_bounces")
    glossy_bounces = g(cy, "glossy_bounces")
    transmission_bounces = g(cy, "transmission_bounces")
    volume_bounces = g(cy, "volume_bounces")
    transparent_max_bounces = g(cy, "transparent_max_bounces")

    print(f"  Total max bounces:    {fmt(max_bounces)}")
    print(f"  Diffuse:              {fmt(diffuse_bounces)}")
    print(f"  Glossy:               {fmt(glossy_bounces)}")
    print(f"  Transmission:         {fmt(transmission_bounces)}")
    print(f"  Volume:               {fmt(volume_bounces)}")
    print(f"  Transparent max:      {fmt(transparent_max_bounces)}")
    print(f"  Fast GI approx:       {fmt(g(cy, 'use_fast_gi'))}")

    if transparent_max_bounces is not None:
        flag(transparent_max_bounces > 4,
             f"Transparent bounces = {transparent_max_bounces}. Alpha-clipped "
             "leaves/grass make every ray traverse many transparent hits. Try 3-4"
             if transparent_max_bounces > 4 else "Transparent bounces are lean")
    if max_bounces is not None:
        flag(max_bounces > 8,
             f"Total bounces = {max_bounces}; outdoor scenes rarely need >6-8"
             if max_bounces > 8 else "Total bounces reasonable")
    if transmission_bounces is not None:
        flag(transmission_bounces > 8,
             f"Transmission bounces = {transmission_bounces} - only needed for "
             "stacked glass/water" if transmission_bounces > 8
             else "Transmission bounces reasonable")

    # ---------------------------------------------------------------- volumes
    head("VOLUMES")
    volume_step_rate = g(cy, "volume_step_rate")
    volume_preview_step_rate = g(cy, "volume_preview_step_rate")
    volume_max_steps = g(cy, "volume_max_steps")
    print(f"  Step rate (render):   {fmt(volume_step_rate)}")
    print(f"  Step rate (preview):  {fmt(volume_preview_step_rate)}")
    print(f"  Max steps:            {fmt(volume_max_steps)}")

    vol_objs, vol_mats = [], []
    for ob in scene.objects:
        if ob.type == "VOLUME":
            vol_objs.append(ob.name)
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        for n in mat.node_tree.nodes:
            if "VOLUME" in n.bl_idname.upper() or n.bl_idname in (
                    "ShaderNodeVolumeScatter", "ShaderNodeVolumeAbsorption",
                    "ShaderNodeVolumePrincipled"):
                vol_mats.append(mat.name)
                break

    world_vol = False
    w = scene.world
    if w and w.use_nodes and w.node_tree:
        out = next((n for n in w.node_tree.nodes
                    if n.bl_idname == "ShaderNodeOutputWorld"), None)
        if out and out.inputs.get("Volume") and out.inputs["Volume"].links:
            world_vol = True

    print(f"  Volume objects:       {len(vol_objs)} {vol_objs[:5]}")
    print(f"  Volume materials:     {len(set(vol_mats))} {sorted(set(vol_mats))[:5]}")
    print(f"  World volume (atmos): {world_vol}")

    has_vol = bool(vol_objs or vol_mats or world_vol)
    if volume_step_rate is not None:
        flag(has_vol and volume_step_rate < 1.0,
             f"Volumes present and step rate {volume_step_rate} < 1.0 - this is "
             "very likely your dominant cost. Raise toward 1.0-2.0"
             if (has_vol and volume_step_rate < 1.0)
             else ("Volumes present, step rate acceptable" if has_vol
                   else "No volumes in scene"))
    else:
        unavailable("volume_step_rate")
    if volume_bounces is not None:
        flag(has_vol and volume_bounces > 2,
             f"Volume bounces = {volume_bounces}; 0-1 is usually enough for haze"
             if (has_vol and volume_bounces > 2) else "Volume bounces fine")

    # ---------------------------------------------------------------- geometry
    head("GEOMETRY  (top 15 objects by evaluated triangles)")
    depsgraph = context.evaluated_depsgraph_get()

    rows, total_tris = [], 0
    for ob in scene.objects:
        if ob.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        if not ob.visible_get() and ob.hide_render:
            continue
        try:
            ev = ob.evaluated_get(depsgraph)
            me = ev.to_mesh()
        except Exception:
            continue
        if me is None:
            continue
        me.calc_loop_triangles()
        tris = len(me.loop_triangles)
        total_tris += tris
        mods = [f"{m.type}" for m in ob.modifiers if m.show_render]
        subd = next((m for m in ob.modifiers
                     if m.type == "SUBSURF" and m.show_render), None)
        note = ""
        if subd:
            note += f" subdiv r{subd.render_levels}/v{subd.levels}"
        if any(m.type == "DISPLACE" for m in ob.modifiers):
            note += " DISPLACE"
        rows.append((tris, ob.name, ",".join(mods), note, ob.hide_render))
        ev.to_mesh_clear()

    rows.sort(reverse=True)
    print(f"  Scene total (render-evaluated): {total_tris:,} tris\n")
    print(f"  {'tris':>12}  {'%':>5}  name / modifiers")
    for tris, name, mods, note, hidden in rows[:15]:
        pct = (tris / total_tris * 100) if total_tris else 0
        tag = " [hidden in render]" if hidden else ""
        print(f"  {tris:>12,}  {pct:>4.1f}%  {name}{tag}")
        if mods or note:
            print(f"                       [{mods}]{note}")

    flag(total_tris > 50_000_000,
         f"{total_tris:,} tris - BVH build and memory will dominate; consider "
         "instancing, lower render subdiv, or LODs on distant geometry"
         if total_tris > 50_000_000 else "Total triangle count manageable")

    heavy_subd = [(o.name, m.render_levels, m.levels)
                  for o in scene.objects for m in o.modifiers
                  if m.type == "SUBSURF" and m.show_render and m.render_levels >= 3]
    flag(bool(heavy_subd),
         f"Render subdivision >=3 on: {heavy_subd[:6]} - render levels are often "
         "left far above what the camera resolves" if heavy_subd
         else "No excessive render subdivision")

    # ---------------------------------------------------------------- hair
    head("HAIR / PARTICLES  (grass, undergrowth)")
    psys_rows = []
    for ob in scene.objects:
        for ps in getattr(ob, "particle_systems", []):
            s = ps.settings
            psys_rows.append((ob.name, ps.name, s.type, s.count,
                              s.rendered_child_count, s.child_percent,
                              s.render_type))
    if psys_rows:
        for o, p, t, cnt, rchild, vchild, rt in psys_rows:
            print(f"  {o} / {p}: type={t} count={cnt:,} "
                  f"render_children={rchild:,} viewport_children={vchild:,} "
                  f"render_as={rt}")
        big = [r for r in psys_rows if r[4] > 100_000]
        flag(bool(big),
             "Very high render child counts - a common landscape bottleneck"
             if big else "Child counts reasonable")
    else:
        print("  none")

    hair_curves = [o.name for o in scene.objects if o.type == "CURVES"]
    print(f"  Hair Curves objects:  {len(hair_curves)} {hair_curves[:5]}")

    # ---------------------------------------------------------------- textures
    head("TEXTURES")
    imgs = sorted(bpy.data.images, key=lambda i: i.size[0] * i.size[1],
                  reverse=True)
    big_tex = 0
    for im in imgs[:15]:
        w_, h_ = im.size
        if w_ * h_ == 0:
            continue
        if max(w_, h_) >= 4096:
            big_tex += 1
        print(f"  {w_:>6} x {h_:<6}  {im.file_format:<6} "
              f"packed={im.packed_file is not None}  {im.name}")
    print(f"\n  Total images: {len(bpy.data.images)}  (>=4K among top 15: {big_tex})")
    flag(big_tex >= 5,
         "Several 4K+ textures - if they're on distant or small-in-frame objects, "
         "downres them; texture memory forces GPU-to-host fallback when exceeded"
         if big_tex >= 5 else "Texture sizes reasonable")

    # ---------------------------------------------------------------- output
    head("OUTPUT / PERFORMANCE")
    r = scene.render
    use_denoising = g(cy, "use_denoising")
    denoiser = g(cy, "denoiser")
    denoising_input_passes = g(cy, "denoising_input_passes")

    print(f"  Resolution:           {r.resolution_x} x {r.resolution_y} "
          f"@ {r.resolution_percentage}%")
    print(f"  Frame range:          {scene.frame_start}-{scene.frame_end}")
    print(f"  Motion blur:          {r.use_motion_blur}")
    print(f"  Persistent data:      {r.use_persistent_data}")
    print(f"  Denoise (render):     {fmt(use_denoising)}")
    if use_denoising:
        print(f"    denoiser:           {fmt(denoiser)}")
        print(f"    input passes:       {fmt(denoising_input_passes)}")
    print(f"  Tile size:            {fmt(g(cy, 'tile_size'))}")
    print(f"  Use spatial splits:   {fmt(g(cy, 'debug_use_spatial_splits'))}")
    print(f"  Compositing:          {scene.use_nodes}")

    anim = scene.frame_end > scene.frame_start
    flag(anim and not r.use_persistent_data,
         "Animation range with Persistent Data OFF - BVH is rebuilt every frame. "
         "Turning it on is often a large win (costs RAM)"
         if (anim and not r.use_persistent_data) else "Persistent data setting ok")
    flag(r.use_motion_blur,
         "Motion blur on - adds cost even on static geometry"
         if r.use_motion_blur else "Motion blur off")
    if use_denoising is not None and denoiser is not None and device is not None:
        flag(use_denoising and denoiser == "OPENIMAGEDENOISE" and device == "GPU",
             "OpenImageDenoise on a GPU render - check whether OptiX denoising is "
             "available, it's much faster"
             if (use_denoising and denoiser == "OPENIMAGEDENOISE" and device == "GPU")
             else "Denoiser choice ok")

    # ---------------------------------------------------------------- shaders
    head("SHADER COST SIGNALS")
    expensive = {
        "ShaderNodeSubsurfaceScattering": "SSS",
        "ShaderNodeBsdfHair": "hair BSDF",
        "ShaderNodeBsdfHairPrincipled": "principled hair",
        "ShaderNodeBsdfTranslucent": "translucent",
        "ShaderNodeBsdfRefraction": "refraction",
        "ShaderNodeTexNoise": "noise tex",
        "ShaderNodeTexMusgrave": "musgrave",
        "ShaderNodeTexVoronoi": "voronoi",
        "ShaderNodeAmbientOcclusion": "AO node",
        "ShaderNodeBevel": "bevel node",
        "ShaderNodeDisplacement": "displacement",
    }
    tally = {}
    disp_mats = []
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        for n in mat.node_tree.nodes:
            label = expensive.get(n.bl_idname)
            if label:
                tally[label] = tally.get(label, 0) + 1
        if mat.displacement_method in {"DISPLACEMENT", "BOTH"}:
            disp_mats.append(mat.name)

    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {v:>4} x {k}")
    if not tally:
        print("  no notably expensive shader nodes found")

    flag(bool(disp_mats),
         f"True displacement enabled on: {disp_mats[:6]} - this tessellates "
         "geometry at render time and can explode memory"
         if disp_mats else "No true displacement")
    flag(tally.get("bevel node", 0) > 0,
         "Bevel node present - it traces extra rays per shade; expensive at scale"
         if tally.get("bevel node") else "No bevel nodes")
    flag(tally.get("AO node", 0) > 0,
         "AO node present - also traces extra rays per shade"
         if tally.get("AO node") else "No AO nodes")

    # ---------------------------------------------------------------- lights
    head("LIGHTS & WORLD")
    for ob in scene.objects:
        if ob.type != "LIGHT":
            continue
        l = ob.data
        l_cycles = g(l, "cycles")
        mis = g(l_cycles, "use_multiple_importance_sampling")
        print(f"  {ob.name}: {l.type} size-ish={fmt(g(l, 'shadow_soft_size'))} "
              f"mis={fmt(mis)}")
    if w:
        w_cycles = g(w, "cycles")
        sample_as_light = g(w_cycles, "sample_as_light")
        map_resolution = g(w_cycles, "sample_map_resolution")
        print(f"  World: {w.name}  "
              f"sample_as_light={fmt(sample_as_light)}  "
              f"map_resolution={fmt(map_resolution)}")
        if sample_as_light is not None:
            flag(not sample_as_light,
                 "World MIS off - HDRI lighting will be noisy and need more samples"
                 if not sample_as_light else "World MIS on")

    head("DONE")
    print("  Re-run after each change and compare against a fixed test frame.")
    print("  Also check the render window's stats readout: it splits time into")
    print("  BVH build / sampling / denoising, which tells you which section")
    print("  above actually matters for your scene.")

    return {"FINISHED"}
