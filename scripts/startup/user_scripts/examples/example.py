# Location: your_scripts_folder/generate_grid.py

import bpy

# The master UI will read this dictionary to build your inputs automatically
PARAMS = {
    "grid_size": {"type": "INT", "default": 10, "min": 1, "max": 100, "name": "Grid Size"},
    "use_cubes": {"type": "BOOL", "default": True, "name": "Instantiate Cubes"},
    "prefix_name": {"type": "STRING", "default": "Generated_Node", "name": "Object Prefix"}
}

def execute(context, params):
    """This function is called when the user clicks 'Run Script'"""
    size = params["grid_size"]
    use_cubes = params["use_cubes"]
    prefix = params["prefix_name"]
    
    print(f"Executing Grid Generator: Size={size}, Cubes={use_cubes}, Prefix={prefix}")
    # Your actual execution logic goes here...
    return {'FINISHED'}