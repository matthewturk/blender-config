bl_info = {
    "name": "Dynamic Script Runner with Hot-Reload",
    "author": "Matthew Turk",
    "version": (1, 3),
    "blender": (4, 2, 0),
    "category": "Development",
}

import bpy
import os
import sys
import importlib.util

DYNAMIC_CLASSES = []
SCRIPT_REGISTRY = {}

def load_external_scripts():
    global SCRIPT_REGISTRY
    SCRIPT_REGISTRY.clear()
    
    # Target folder: 'user_scripts' folder next to the add-on script
    scripts_dir = os.path.join(os.path.dirname(__file__), "user_scripts")
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
        return []

    items = []
    for f in os.listdir(scripts_dir):
        if f.endswith(".py") and not f.startswith("__"):
            path = os.path.join(scripts_dir, f)
            module_name = f[:-3]
            
            # Flush Python's module cache for the target script
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            spec = importlib.util.spec_from_file_location(module_name, path)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                if hasattr(mod, "PARAMS") and hasattr(mod, "execute"):
                    SCRIPT_REGISTRY[module_name] = mod
                    label = mod.PARAMS.get("label", module_name.replace('_', ' ').title())
                    items.append((module_name, label, f"Run {f}"))
            except Exception as e:
                print(f"Failed to load script {f}: {e}")
    return items


def get_script_items(self, context):
    return load_external_scripts()


class DynamicScriptSettings(bpy.types.PropertyGroup):
    selected_script: bpy.props.EnumProperty(
        name="Select Script",
        description="Choose a script from your automation folder",
        items=get_script_items
    )

def create_blender_props(params_dict):
    """Maps custom PARAMS configurations to registered bpy.props factories."""
    props = {}
    
    for key, spec in params_dict.items():
        if key == "label":
            continue
        p_type = spec.get("type")
        p_name = spec.get("name", key)
        p_desc = spec.get("description", "")
        
        if p_type == "INT":
            props[key] = bpy.props.IntProperty(
                name=p_name, description=p_desc,
                default=spec.get("default", 0),
                min=spec.get("min", -2147483648), max=spec.get("max", 2147483647)
            )
        elif p_type == "FLOAT":
            props[key] = bpy.props.FloatProperty(
                name=p_name, description=p_desc,
                default=spec.get("default", 0.0),
                min=spec.get("min", -3.402823e+38), max=spec.get("max", 3.402823e+38)
            )
        elif p_type == "BOOL":
            props[key] = bpy.props.BoolProperty(
                name=p_name, description=p_desc, default=spec.get("default", False)
            )
        elif p_type == "STRING":
            props[key] = bpy.props.StringProperty(
                name=p_name, description=p_desc, default=spec.get("default", "")
            )
        elif p_type == "ENUM":
            props[key] = bpy.props.EnumProperty(
                name=p_name, description=p_desc,
                items=spec.get("items", []), default=spec.get("default")
            )
        elif p_type == "COLOR":
            # Determines float array length based on default length (RGB vs RGBA)
            default_val = spec.get("default", (1.0, 1.0, 1.0, 1.0))
            props[key] = bpy.props.FloatVectorProperty(
                name=p_name, description=p_desc,
                default=default_val, size=len(default_val),
                subtype='COLOR', min=0.0, max=1.0
            )
        elif p_type == "VECTOR":
            props[key] = bpy.props.FloatVectorProperty(
                name=p_name, description=p_desc,
                default=spec.get("default", (0.0, 0.0, 0.0)),
                subtype='TRANSLATION'
            )
        elif p_type == "OBJECT":
            props[key] = bpy.props.PointerProperty(
                name=p_name, description=p_desc, type=bpy.types.Object
            )
        elif p_type == "COLLECTION":
            props[key] = bpy.props.PointerProperty(
                name=p_name, description=p_desc, type=bpy.types.Collection
            )
            
    return props

def make_dynamic_operator(script_name, mod):
    # Enforce lowercase name matching for structural consistency
    sanitized_name = script_name.lower()
    bl_idname = f"script_runner.dynamic_{sanitized_name}"
    bl_label = f"Run {script_name.replace('_', ' ').title()}"
    
    class_dict = {
        'bl_idname': bl_idname,
        'bl_label': bl_label,
        'bl_options': {'REGISTER', 'UNDO'},
        '__annotations__': {}  
    }

    def execute(self, context):
        runtime_params = {}
        # Explicit lower-case lookup match
        prop_attr = f"sr_props_{script_name.lower()}"
        props_container = getattr(context.scene, prop_attr, None)
        
        for key, spec in mod.PARAMS.items():
            if key != "label":
                if props_container and hasattr(props_container, key):
                    val = getattr(props_container, key)
                    if spec["type"] in {"COLOR", "VECTOR"}:
                        runtime_params[key] = tuple(val)
                    else:
                        runtime_params[key] = val
                else:
                    runtime_params[key] = spec.get("default")
                    
        return mod.execute(context, runtime_params)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        # Explicit lower-case lookup match to prevent API registration misses
        prop_attr = f"sr_props_{script_name.lower()}"
        props_container = getattr(context.scene, prop_attr, None)
        
        if props_container:
            for key in mod.PARAMS.keys():
                if key != "label":
                    # Directly draw from the scene properties wrapper
                    layout.prop(props_container, key)
        else:
            layout.label(text="Error loading parameters.", icon='ERROR')

    class_dict['execute'] = execute
    class_dict['invoke'] = invoke
    class_dict['draw'] = draw

    return type(f"SR_OT_dynamic_{script_name}", (bpy.types.Operator,), class_dict)


class SR_OT_reload_scripts(bpy.types.Operator):
    """Scan scripts folder, wipe old operators/property groups, and generate new parameters"""
    bl_idname = "script_runner.reload_scripts"
    bl_label = "Refresh Script Library"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global DYNAMIC_CLASSES
        
        # Unregister all dynamic classes (operators and property groups)
        for cls in DYNAMIC_CLASSES:
            try:
                if issubclass(cls, bpy.types.PropertyGroup):
                    prop_name = cls.__name__
                    if hasattr(bpy.types.Scene, prop_name):
                        delattr(bpy.types.Scene, prop_name)
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
        DYNAMIC_CLASSES.clear()
        
        script_items = load_external_scripts()
        for name, _, _ in script_items:
            mod = SCRIPT_REGISTRY[name]
            
            # 1. Force property layout to string-safe lowercase structure
            prop_dict = create_blender_props(mod.PARAMS)
            prop_cls_name = f"sr_props_{name.lower()}"
            
            # CRITICAL FIX: Modern Blender expects dynamic PropertyGroup properties 
            # to be injected into '__annotations__', NOT as direct class variables!
            class_dict = {
                '__annotations__': prop_dict
            }
            
            prop_cls = type(prop_cls_name, (bpy.types.PropertyGroup,), class_dict)
            bpy.utils.register_class(prop_cls)
            DYNAMIC_CLASSES.append(prop_cls)
            
            # Attach explicitly as a scene-level container pointer 
            setattr(bpy.types.Scene, prop_cls_name, bpy.props.PointerProperty(type=prop_cls))
            
            # 2. Register execution operator launcher
            op_cls = make_dynamic_operator(name, mod)
            bpy.utils.register_class(op_cls)
            DYNAMIC_CLASSES.append(op_cls)
            
        if getattr(context, "area", None) is not None:
            context.area.tag_redraw()
        return {'FINISHED'}


class OBJECT_PT_dynamic_script_runner(bpy.types.Panel):
    bl_label = "Script Automation Library"
    bl_idname = "OBJECT_PT_dynamic_script_runner"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Script Runner'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.dynamic_script_runner
        
        # Header selection dropdown array
        row = layout.row(align=True)
        row.prop(props, "selected_script", text="")
        row.operator("script_runner.reload_scripts", icon='FILE_REFRESH', text="")
        
        layout.separator()
        
        selected = props.selected_script
        if selected in SCRIPT_REGISTRY:
            op_idname = f"script_runner.dynamic_{selected.lower()}"
            print(op_idname)
            
            box = layout.box()
            nice_name = selected.replace('_', ' ').title()
            box.label(text=f"Ready: {nice_name}", icon='TEXT')
            
            # The panel ONLY draws the execution button launcher.
            # Clicking it calls `invoke()`, opening the pop-up options window natively.
            box.operator(op_idname, text="Configure & Run", icon='PLAY')

def _reload_scripts():
    if hasattr(bpy.ops, "script_runner") and hasattr(bpy.ops.script_runner, "reload_scripts"):
        print("Reloading scripts on startup.")
        bpy.ops.script_runner.reload_scripts()
    return None

def register():
    bpy.utils.register_class(DynamicScriptSettings)
    bpy.utils.register_class(SR_OT_reload_scripts)
    bpy.utils.register_class(OBJECT_PT_dynamic_script_runner)
    
    bpy.types.Scene.dynamic_script_runner = bpy.props.PointerProperty(type=DynamicScriptSettings)
    bpy.app.timers.register(_reload_scripts, first_interval=1.0)

def unregister():
    global DYNAMIC_CLASSES
    for cls in DYNAMIC_CLASSES:
        try:
            if issubclass(cls, bpy.types.PropertyGroup):
                prop_name = cls.__name__.lower()
                if hasattr(bpy.types.Scene, prop_name):
                    delattr(bpy.types.Scene, prop_name)
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    DYNAMIC_CLASSES.clear()
    
    bpy.utils.unregister_class(OBJECT_PT_dynamic_script_runner)
    bpy.utils.unregister_class(SR_OT_reload_scripts)
    bpy.utils.unregister_class(DynamicScriptSettings)
    del bpy.types.Scene.dynamic_script_runner

if __name__ == "__main__":
    register()
