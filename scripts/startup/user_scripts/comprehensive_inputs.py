import bpy

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
