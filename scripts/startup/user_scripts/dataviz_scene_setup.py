import bpy

# Sets up a dedicated Scene for flat 2D dataviz: an orthographic camera framing
# a parameterized rectangle of the XY plane, and a single flat, shadowless sun
# light with no specular contribution - so materials render as close to their
# base color as possible, with no shading gradients, highlights or shadows to
# fight with. Render resolution height is derived from resolution_x to exactly
# match the area's aspect ratio (no stretching), and film_transparent is on by
# default so this scene's render composites cleanly over another.
#
# Everything is named after `scene_name` and looked up before creating, so
# re-running with the same name updates the existing setup in place instead
# of creating duplicates.

PARAMS = {
    "scene_name": {
        "type": "STRING",
        "default": "Dataviz",
        "name": "Scene Name",
        "description": "Name for the new (or reused) scene set up for 2D dataviz",
    },
    "area_x_min": {
        "type": "FLOAT",
        "default": 0.0,
        "name": "Area X Min",
        "description": "Left edge of the XY-plane region the camera frames",
    },
    "area_y_min": {
        "type": "FLOAT",
        "default": 0.0,
        "name": "Area Y Min",
        "description": "Bottom edge of the XY-plane region the camera frames",
    },
    "area_x_max": {
        "type": "FLOAT",
        "default": 1.0,
        "name": "Area X Max",
        "description": "Right edge of the XY-plane region the camera frames",
    },
    "area_y_max": {
        "type": "FLOAT",
        "default": 1.0,
        "name": "Area Y Max",
        "description": "Top edge of the XY-plane region the camera frames",
    },
    "margin": {
        "type": "FLOAT",
        "default": 0.0,
        "name": "Margin",
        "description": "Fractional padding added around the area on every side (0.05 = 5%)",
    },
    "resolution_x": {
        "type": "INT",
        "default": 1920,
        "name": "Resolution X",
        "description": "Render width in pixels; height is derived to exactly match the area's aspect ratio",
    },
    "camera_height": {
        "type": "FLOAT",
        "default": 10.0,
        "name": "Camera Height",
        "description": "Distance above the XY plane to place the camera (orthographic, so this doesn't affect framing)",
    },
    "sun_strength": {
        "type": "FLOAT",
        "default": 3.0,
        "name": "Sun Strength",
        "description": "Strength of the single flat, shadowless sun light",
    },
    "film_transparent": {
        "type": "BOOL",
        "default": True,
        "name": "Transparent Background",
        "description": "Render with a transparent background so this scene composites cleanly over another",
    },
}


def _get_or_new(datablocks, name, *args, **kwargs):
    block = datablocks.get(name)
    if block is None:
        block = datablocks.new(name, *args, **kwargs)
    return block


def execute(context, params):
    scene_name = params["scene_name"]
    x_min, x_max = sorted((params["area_x_min"], params["area_x_max"]))
    y_min, y_max = sorted((params["area_y_min"], params["area_y_max"]))
    margin = params["margin"]
    resolution_x = max(1, int(params["resolution_x"]))
    camera_height = params["camera_height"]

    width = (x_max - x_min) * (1.0 + 2.0 * margin)
    height = (y_max - y_min) * (1.0 + 2.0 * margin)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Area must have positive width and height")

    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0

    scene = _get_or_new(bpy.data.scenes, scene_name)

    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = max(1, round(resolution_x * height / width))
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = params["film_transparent"]

    # ── fresh, empty World so no stray ambient/env light sneaks in ──
    world = _get_or_new(bpy.data.worlds, f"{scene_name} World")
    world.use_nodes = True
    tree = world.node_tree
    bg = next((n for n in tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = tree.nodes.new("ShaderNodeBackground")
        output = next((n for n in tree.nodes if n.type == "OUTPUT_WORLD"), None)
        if output is None:
            output = tree.nodes.new("ShaderNodeOutputWorld")
        tree.links.new(bg.outputs[0], output.inputs[0])
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs["Strength"].default_value = 0.0
    scene.world = world

    # ── camera: orthographic, looking straight down -Z at the framed area ──
    cam_name = f"{scene_name} Camera"
    cam_data = _get_or_new(bpy.data.cameras, cam_name)
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.ortho_scale = width
    cam_data.clip_start = 0.01
    cam_data.clip_end = max(camera_height * 4.0, 100.0)

    cam_obj = bpy.data.objects.get(cam_name)
    if cam_obj is None:
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
    elif cam_obj.data != cam_data:
        cam_obj.data = cam_data
    cam_obj.location = (center_x, center_y, camera_height)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)

    if cam_obj.name not in scene.collection.objects:
        scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # ── lighting: one flat, shadowless, non-specular sun aimed straight down ──
    lights_coll = _get_or_new(bpy.data.collections, f"{scene_name} Lights")
    if lights_coll.name not in scene.collection.children:
        scene.collection.children.link(lights_coll)

    sun_name = f"{scene_name} Sun"
    sun_data = _get_or_new(bpy.data.lights, sun_name, type="SUN")
    sun_data.energy = params["sun_strength"]
    sun_data.angle = 0.0
    sun_data.use_shadow = False
    sun_data.specular_factor = 0.0

    sun_obj = bpy.data.objects.get(sun_name)
    if sun_obj is None:
        sun_obj = bpy.data.objects.new(sun_name, sun_data)
    elif sun_obj.data != sun_data:
        sun_obj.data = sun_data
    sun_obj.location = (center_x, center_y, camera_height)
    sun_obj.rotation_euler = (0.0, 0.0, 0.0)

    if sun_obj.name not in lights_coll.objects:
        lights_coll.objects.link(sun_obj)

    print(
        f"Set up dataviz scene '{scene.name}': area=({x_min},{y_min})-({x_max},{y_max}), "
        f"resolution={scene.render.resolution_x}x{scene.render.resolution_y}, "
        f"ortho_scale={width:.4g}"
    )
    return {"FINISHED"}
