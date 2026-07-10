bl_info = {
    "name": "Dynamic Script Runner with Hot-Reload",
    "author": "Your Name",
    "version": (1, 2),
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
    return [("None", "", "")] + load_external_scripts()


class DynamicScriptSettings(bpy.types.PropertyGroup):
    selected_script: bpy.props.EnumProperty(
        name="Select Script",
        description="Choose a script from your automation folder",
        items=get_script_items
    )


def make_dynamic_operator(script_name, mod):
    bl_idname = f"script_runner.dynamic_{script_name.lower()}"
    bl_label = f"Run {script_name.replace('_', ' ').title()}"
    
    # Initialize base dictionary for properties and type annotations
    class_dict = {
        'bl_idname': bl_idname,
        'bl_label': bl_label,
        'bl_options': {'REGISTER', 'UNDO'},
        '__annotations__': {}  # CRITICAL: Modern Blender expects dynamic properties here
    }
    
    # Inject properties cleanly into the type annotation map
    for key, spec in mod.PARAMS.items():
        if key == "label":
            continue
        p_type = spec.get("type")
        p_name = spec.get("name", key)
        p_default = spec.get("default")
        
        if p_type == "INT":
            prop = bpy.props.IntProperty(
                name=p_name, default=p_default,
                min=spec.get("min", -2147483648), max=spec.get("max", 2147483647)
            )
        elif p_type == "FLOAT":
            prop = bpy.props.FloatProperty(
                name=p_name, default=p_default,
                min=spec.get("min", -1e10), max=spec.get("max", 1e10)
            )
        elif p_type == "BOOL":
            prop = bpy.props.BoolProperty(name=p_name, default=p_default)
        elif p_type == "STRING":
            prop = bpy.props.StringProperty(name=p_name, default=p_default)
        else:
            continue
            
        class_dict['__annotations__'][key] = prop

    def execute(self, context):
        # Pack the user inputs safely back out
        runtime_params = {}
        for key in mod.PARAMS.keys():
            if key != "label" and hasattr(self, key):
                runtime_params[key] = getattr(self, key)
        return mod.execute(context, runtime_params)

    def invoke(self, context, event):
        # Explicitly summon an interactive parameter prompt popup dialog
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        # Render the specific options safely inside the popup layout boundary
        for key in mod.PARAMS.keys():
            if key != "label" and key in self.__annotations__:
                layout.prop(self, key)

    class_dict['execute'] = execute
    class_dict['invoke'] = invoke
    class_dict['draw'] = draw

    return type(f"SR_OT_dynamic_{script_name}", (bpy.types.Operator,), class_dict)


class SR_OT_reload_scripts(bpy.types.Operator):
    """Scan scripts folder, wipe old operators, and generate new parameters"""
    bl_idname = "script_runner.reload_scripts"
    bl_label = "Refresh Script Library"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global DYNAMIC_CLASSES
        
        for cls in DYNAMIC_CLASSES:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
        DYNAMIC_CLASSES.clear()
        
        script_items = load_external_scripts()
        for name, _, _ in script_items:
            mod = SCRIPT_REGISTRY[name]
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
