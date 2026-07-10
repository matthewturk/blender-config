import bpy
import os

# Comprehensive parameter dictionary mapping standard UI types to Blender properties
PARAMS = {
    # Basic Numeric & Boolean Types
    "grid_size": {
        "type": "INT", 
        "default": 10, 
        "min": 1, 
        "max": 100, 
        "name": "Grid Size",
        "description": "Number of elements along one axis"
    },
    "scale_factor": {
        "type": "FLOAT", 
        "default": 1.0, 
        "min": 0.0, 
        "max": 10.0, 
        "name": "Scale Factor",
        "description": "Global multiplier for asset scaling"
    },
    "use_cubes": {
        "type": "BOOL", 
        "default": True, 
        "name": "Instantiate Cubes",
        "description": "Toggle between custom object or default cube primitives"
    },
    
    # Text & Categorical Selection
    "prefix_name": {
        "type": "STRING", 
        "default": "Generated_Node", 
        "name": "Object Prefix",
        "description": "Prefix applied to all newly created objects"
    },
    "distribution_type": {
        "type": "ENUM", 
        "default": "GRID", 
        "items": [
            ("GRID", "Grid", "Arrange in a standard grid layout"),
            ("RANDOM", "Random", "Scatter randomly within bounds"),
            ("SPIRAL", "Spiral", "Arrange in a Fibonacci spiral")
        ],
        "name": "Distribution Style"
    },
    
    # Color (Vector of 3 or 4 floats)
    "instanced_color": {
        "type": "COLOR", 
        "default": (0.1, 0.6, 0.8, 1.0), # RGBA
        "name": "Viewport Color",
        "description": "Color applied to the generated geometry viewport display"
    },
    
    # Blender ID Data References (Objects & Collections)
    # Note: Your UI runner should map these types to bpy.props.PointerProperty 
    # pointing to bpy.types.Object and bpy.types.Collection respectively.
    "target_object": {
        "type": "OBJECT", 
        "default": None, 
        "name": "Source Object",
        "description": "The specific object to instance (leaves blank for primitives)"
    },
    "target_collection": {
        "type": "COLLECTION", 
        "default": None, 
        "name": "Target Collection",
        "description": "The scene collection where new elements will be organized"
    },
    "import_source": {
        "type": "FILE_PATH", 
        "default": "//data.json", 
        "name": "Source File",
        "description": "Select the target file to parse"
    },
    "export_destination": {
        "type": "DIR_PATH", 
        "default": "/tmp", 
        "name": "Output Directory",
        "description": "Select where generated asset logs should be saved"
    },
    "target_material": {
        "type": "POINTER",
        "target": "Material",
        "name": "Surface Material",
        "description": "Material to apply to generated geometry surfaces"
    },
    "target_image": {
        "type": "POINTER",
        "target": "Image",
        "name": "Texture Map",
        "description": "Image data block to feed into shader nodes"
    },
    "target_text_block": {
        "type": "POINTER",
        "target": "Text",
        "name": "Configuration Script",
        "description": "An internal .txt or .py file containing procedural parameters"
    },
    "source_scene": {
        "type": "POINTER",
        "target": "Scene",
        "name": "Link Elements From",
        "description": "Scene data block to look into for master instances"
    },
    
    # 2. Hard Disk File I/O Pickers
    "import_path": {
        "type": "FILE_PATH",
        "default": "//assets_manifest.json",
        "name": "Asset Manifest File",
        "description": "Path to the configuration spreadsheet or tracking log"
    },
    "output_folder": {
        "type": "DIR_PATH",
        "default": "/tmp",
        "name": "Render Export Directory",
        "description": "Destination directory folder on disk for bake storage"
    },
    
    # 3. Numeric Specializations with Units & Coordinates
    "voxel_resolution": {
        "type": "INT_VECTOR",
        "default": (128, 128, 64),
        "name": "Voxel Grid Dimensions",
        "description": "Bounding box subdivision sizes along XYZ axes"
    },
    "spawn_radius": {
        "type": "FLOAT",
        "default": 2.5,
        "unit": "LENGTH", # Spawns meters/feet marks dynamically in UI
        "name": "Scatter Margin",
        "description": "Distance parameter translated directly to scene scale units"
    },
    "rotation_offset": {
        "type": "FLOAT",
        "default": 1.5708, # Pi/2 radians
        "unit": "ROTATION", # Automatically displays as degrees (90°) in UI
        "name": "Anisotropic Spin",
        "description": "Internal radian multiplier converted to rotational visual feedback"
    },
    "simulation_duration": {
        "type": "FLOAT",
        "default": 5.0,
        "unit": "TIME", # Automatically appends 's' (seconds) or frame counts
        "name": "Bake Duration",
        "description": "Total active life envelope window duration"
    },
    
    # 4. Multi-Select Enum Checklist Flags
    "render_passes": {
        "type": "ENUM",
        "default": {"COMBINED", "DIFFUSE"}, # Python Set wrapper
        "options": {"ENUM_FLAG"},           # Python Set containing the flag string
        "items": [
            ("COMBINED", "Combined Beauty", "Render complete pass stack output"),
            ("DIFFUSE", "Diffuse Component", "Render albedo/color illumination details"),
            ("GLOSSY", "Glossy Specular", "Isolate reflections vectors"),
            ("EMISSION", "Emission Pass", "Isolate glow luminosity maps")
        ],
        "name": "Active Engine Buffers"
    }
}

def execute(context, params):
    """
    This function is called when the user clicks 'Run Script' 
    with the parsed UI values passed in via the params dictionary.
    """
    # 1. Unpack basic parameters
    size = params["grid_size"]
    scale = params["scale_factor"]
    use_cubes = params["use_cubes"]
    prefix = params["prefix_name"]
    dist_style = params["distribution_type"]
    color = params["instanced_color"]
    
    # 2. Unpack Blender Data references 
    # (Expects actual bpy.types.Object / Collection references passed by your runner)
    source_obj = params["target_object"]
    dest_collection = params["target_collection"]
    raw_file_path = params["import_source"]
    raw_dir_path = params["export_destination"]
    
    # 2. Inspect In-Scene Pointer ID Objects
    mat = params["target_material"]
    img = params["target_image"]
    txt = params["target_text_block"]
    scn = params["source_scene"]
    
    print(f"[Data Blocks] Material Linked: {mat.name if mat else 'None'}")
    print(f"[Data Blocks] Texture Image Linked: {img.name if img else 'None'}")
    print(f"[Data Blocks] Text Config Linked: {txt.name if txt else 'None'}")
    print(f"[Data Blocks] Source Scene Linked: {scn.name if scn else 'None'}")
    
    # 3. Handle Special Math Vectors and Unit Quantities
    dimensions = params["voxel_resolution"]
    radius = params["spawn_radius"]
    rot = params["rotation_offset"]
    duration = params["simulation_duration"]
    
    print(f"[Math Config] Grid Structure Arrays: {list(dimensions)}")
    print(f"[Math Config] Distance Scalar: {radius}m | Angle: {rot} rad | Envelope: {duration}s")
    
    # 4. Handle Active Multi-select Sets
    active_passes = params["render_passes"]
    print(f"[Aesthetics] Multi-Select Checklist Flags Active: {list(active_passes)}")
    
    # Pro-tip: Resolve Blender's relative path prefix (like '//') to absolute paths
    absolute_file = bpy.path.abspath(raw_file_path)
    absolute_dir = bpy.path.abspath(raw_dir_path)
    
    print("\n--- Running File I/O Script ---")
    print(f"Targeting File: {absolute_file}")
    print(f"Targeting Directory: {absolute_dir}")
    
    if os.path.exists(absolute_file):
        print("File verified on disk.")
    else:
        print("File does not exist yet; setting up initialization rules.")
    
    # Log configuration summary to the console
    print("\n--- Executing Comprehensive Script Runner ---")
    print(f"Config: Size={size}, Scale={scale}, Style={dist_style}")
    print(f"Naming Prefix: '{prefix}' | Color Vector: {list(color)}")
    
    # Handle Object Reference Logic
    if source_obj:
        print(f"Target Object Detected: '{source_obj.name}' (Type: {source_obj.type})")
    else:
        print("Target Object: None (Using default primitives instead)")
        
    # Handle Collection Reference Logic
    if dest_collection:
        print(f"Target Destination Collection: '{dest_collection.name}'")
    else:
        # Fallback to active scene collection if none is specified
        dest_collection = context.scene.collection
        print(f"Target Destination Collection: None (Defaulting to Master Collection)")

    # Example execution flow
    try:
        # Your geometry/scene generation logic goes here...
        # e.g., if source_obj and not use_cubes: duplicate source_obj inside dest_collection
        
        return {'FINISHED'}
        
    except Exception as e:
        print(f"Execution failed: {str(e)}")
        return {'CANCELLED'}
