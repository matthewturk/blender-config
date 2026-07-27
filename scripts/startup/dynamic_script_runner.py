bl_info = {
    "name": "Dynamic Script & Node Runner with Hot-Reload",
    "author": "Matthew Turk",
    "version": (1, 6),
    "blender": (4, 2, 0),
    "category": "Development",
}

import bpy
import os
import sys
import importlib.util

DYNAMIC_CLASSES = []
SCRIPT_REGISTRY = {}
NODE_SCRIPT_REGISTRY = {}


# ---------------------------------------------------------------------------
#  Shared parameter helpers
# ---------------------------------------------------------------------------

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
        elif p_type == "COLOR":
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
        elif p_type == "FILE_PATH":
            props[key] = bpy.props.StringProperty(
                name=p_name,
                description=p_desc,
                default=spec.get("default", ""),
                subtype='FILE_PATH'
            )
        elif p_type == "DIR_PATH":
            props[key] = bpy.props.StringProperty(
                name=p_name,
                description=p_desc,
                default=spec.get("default", ""),
                subtype='DIR_PATH'
            )
        elif p_type == "POINTER":
            target_str = spec.get("target", "Object")
            target_cls = getattr(bpy.types, target_str, bpy.types.Object)
            props[key] = bpy.props.PointerProperty(
                name=p_name, description=p_desc, type=target_cls
            )
        elif p_type == "INT_VECTOR":
            default_val = spec.get("default", (0, 0, 0))
            props[key] = bpy.props.IntVectorProperty(
                name=p_name, description=p_desc,
                default=default_val, size=len(default_val)
            )
        elif p_type in {"FLOAT", "INT"} and "unit" in spec:
            prop_factory = bpy.props.FloatProperty if p_type == "FLOAT" else bpy.props.IntProperty
            props[key] = prop_factory(
                name=p_name, description=p_desc,
                default=spec.get("default", 0.0 if p_type == "FLOAT" else 0),
                unit=spec["unit"]
            )
        elif p_type == "ENUM":
            raw_options = spec.get("options", set())
            if isinstance(raw_options, (list, tuple)):
                options_set = set(raw_options)
            elif isinstance(raw_options, set):
                options_set = raw_options
            else:
                options_set = set()

            if "ENUM_FLAG" in options_set:
                raw_default = spec.get("default", set())
                if isinstance(raw_default, (list, tuple)):
                    default_val = set(raw_default)
                elif isinstance(raw_default, set):
                    default_val = raw_default
                else:
                    default_val = {str(raw_default)} if raw_default else set()

                props[key] = bpy.props.EnumProperty(
                    name=p_name,
                    description=p_desc,
                    items=spec.get("items", []),
                    options=options_set,
                    default=default_val
                )
            else:
                default_val = spec.get("default", "")
                if isinstance(default_val, (set, list, tuple)):
                    default_val = list(default_val)[0] if default_val else ""

                props[key] = bpy.props.EnumProperty(
                    name=p_name,
                    description=p_desc,
                    items=spec.get("items", []),
                    default=str(default_val)
                )
    return props


def register_prop_group(prefix, name, mod):
    """Create a PropertyGroup from mod.PARAMS and register it on Scene."""
    prop_dict = create_blender_props(mod.PARAMS)
    prop_cls_name = f"{prefix}_{name.lower()}"
    prop_cls = type(prop_cls_name, (bpy.types.PropertyGroup,), {
        '__annotations__': prop_dict
    })
    bpy.utils.register_class(prop_cls)
    DYNAMIC_CLASSES.append(prop_cls)
    setattr(bpy.types.Scene, prop_cls_name, bpy.props.PointerProperty(type=prop_cls))
    #print(f"[node_runner] registered {prop_cls_name} on Scene")
    return prop_cls_name


def collect_params_from_context(context, prefix, name, mod):
    """Read current values from the scene PropertyGroup for this script."""
    params = {}
    if not hasattr(mod, "PARAMS"):
        return params
    prop_attr = f"{prefix}_{name.lower()}"
    props_container = getattr(context.scene, prop_attr, None)
    for key, spec in mod.PARAMS.items():
        if key == "label":
            continue
        if props_container and hasattr(props_container, key):
            val = getattr(props_container, key)
            if spec["type"] in {"COLOR", "VECTOR"}:
                params[key] = tuple(val)
            else:
                params[key] = val
        else:
            params[key] = spec.get("default")
    return params


def draw_params_from_context(layout, context, prefix, name, mod):
    """Draw PARAMS properties from the scene PropertyGroup into a layout."""
    if not hasattr(mod, "PARAMS") or not mod.PARAMS:
        return
    prop_attr = f"{prefix}_{name.lower()}"
    props_container = getattr(context.scene, prop_attr, None)
    #print(f"[node_runner] draw: looking for {prop_attr} on scene -> {props_container}")
    if props_container:
        for key in mod.PARAMS.keys():
            if key != "label":
                layout.prop(props_container, key)
    else:
        layout.label(text="Error loading parameters.", icon='ERROR')


# ---------------------------------------------------------------------------
#  User Scripts (user_scripts/)
# ---------------------------------------------------------------------------

def load_external_scripts():
    global SCRIPT_REGISTRY
    SCRIPT_REGISTRY.clear()

    scripts_dir = os.path.join(os.path.dirname(__file__), "user_scripts")
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
        return []

    items = []
    for f in os.listdir(scripts_dir):
        if f.endswith(".py") and not f.startswith("__"):
            path = os.path.join(scripts_dir, f)
            module_name = f[:-3]

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


# ---------------------------------------------------------------------------
#  Node Scripts (node_scripts/)
# ---------------------------------------------------------------------------

def load_node_scripts():
    global NODE_SCRIPT_REGISTRY
    NODE_SCRIPT_REGISTRY.clear()

    scripts_dir = os.path.join(os.path.dirname(__file__), "node_scripts")
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
        return []

    items = []
    for f in os.listdir(scripts_dir):
        if f.endswith(".py") and not f.startswith("__"):
            path = os.path.join(scripts_dir, f)
            module_name = f[:-3]

            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, path)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                if hasattr(mod, "build"):
                    NODE_SCRIPT_REGISTRY[module_name] = mod
                    label = getattr(mod, "NAME", module_name.replace("_", " ").title())
                    items.append((module_name, label, f"Build {label} node tree"))
            except Exception as e:
                print(f"Failed to load node script {f}: {e}")
    return items


def get_node_script_items(self, context):
    return load_node_scripts()


# ---------------------------------------------------------------------------
#  Settings PropertyGroups
# ---------------------------------------------------------------------------

class DynamicScriptSettings(bpy.types.PropertyGroup):
    selected_script: bpy.props.EnumProperty(
        name="Select Script",
        description="Choose a script from your automation folder",
        items=get_script_items
    )

class NodeScriptSettings(bpy.types.PropertyGroup):
    selected_script: bpy.props.EnumProperty(
        name="Select Node Script",
        description="Choose a node tree generation script",
        items=get_node_script_items,
    )


# ---------------------------------------------------------------------------
#  User-script dynamic operators
# ---------------------------------------------------------------------------

def make_dynamic_operator(script_name, mod):
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
        runtime_params = collect_params_from_context(
            context, "sr_props", script_name, mod
        )
        return mod.execute(context, runtime_params)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        draw_params_from_context(self.layout, context, "sr_props", script_name, mod)

    class_dict['execute'] = execute
    class_dict['invoke'] = invoke
    class_dict['draw'] = draw

    return type(f"SR_OT_dynamic_{script_name}", (bpy.types.Operator,), class_dict)


# ---------------------------------------------------------------------------
#  Node-script build operator
# ---------------------------------------------------------------------------

class NODE_OT_run_script(bpy.types.Operator):
    """Build or rebuild the selected node tree"""
    bl_idname = "node_runner.run_script"
    bl_label = "Build Node Tree"
    bl_options = {"REGISTER", "UNDO"}

    script_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        mod = NODE_SCRIPT_REGISTRY.get(self.script_name)
        if mod and hasattr(mod, "PARAMS") and mod.PARAMS:
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, context):
        mod = NODE_SCRIPT_REGISTRY.get(self.script_name)
        if mod:
            draw_params_from_context(
                self.layout, context, "nsr_props", self.script_name, mod
            )

    def execute(self, context):
        name = self.script_name
        if name not in NODE_SCRIPT_REGISTRY:
            self.report({"ERROR"}, f"Script '{name}' not found")
            return {"CANCELLED"}

        mod = NODE_SCRIPT_REGISTRY[name]
        params = collect_params_from_context(context, "nsr_props", name, mod)

        tree_name = params.pop("node_group_name", None)
        if not tree_name:
            tree_name = getattr(mod, "NAME", name.replace("_", " ").title())

        existing = bpy.data.node_groups.get(tree_name)
        if existing is not None:
            existing.interface.clear()
            existing.nodes.clear()

        try:
            from nodebpy import geometry as g

            with g.tree(existing or tree_name) as tree:
                mod.build(tree, params)

                ng = bpy.data.node_groups[tree_name]
                if not any(
                    item.item_type == "SOCKET" and item.in_out == "OUTPUT"
                    for item in ng.interface.items_tree
                ):
                    tree.outputs.geometry("Output")

        except Exception as e:
            self.report({"ERROR"}, f"Failed to build '{tree_name}': {e}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Built node tree: {tree_name}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
#  Reload operators
# ---------------------------------------------------------------------------

class SR_OT_reload_scripts(bpy.types.Operator):
    """Scan scripts folder, wipe old operators/property groups, and generate new parameters"""
    bl_idname = "script_runner.reload_scripts"
    bl_label = "Refresh Script Library"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global DYNAMIC_CLASSES

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
            register_prop_group("sr_props", name, mod)

            op_cls = make_dynamic_operator(name, mod)
            bpy.utils.register_class(op_cls)
            DYNAMIC_CLASSES.append(op_cls)

        if getattr(context, "area", None) is not None:
            context.area.tag_redraw()
        return {'FINISHED'}


class NODE_OT_reload_node_scripts(bpy.types.Operator):
    """Scan node_scripts folder and refresh the dropdown list"""
    bl_idname = "node_runner.reload_scripts"
    bl_label = "Refresh Node Scripts"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        global DYNAMIC_CLASSES

        for cls in list(DYNAMIC_CLASSES):
            try:
                if issubclass(cls, bpy.types.PropertyGroup) and cls.__name__.startswith("nsr_props_"):
                    prop_name = cls.__name__
                    if hasattr(bpy.types.Scene, prop_name):
                        delattr(bpy.types.Scene, prop_name)
                    bpy.utils.unregister_class(cls)
                    DYNAMIC_CLASSES.remove(cls)
            except Exception:
                pass

        script_items = load_node_scripts()
        #print(f"[node_runner] reload: found {len(script_items)} node scripts: {[n for n,_,_ in script_items]}")
        for name, _, _ in script_items:
            mod = NODE_SCRIPT_REGISTRY[name]
            has_params = hasattr(mod, "PARAMS") and bool(mod.PARAMS)
            #print(f"[node_runner]   {name}: PARAMS={has_params}")
            if has_params:
                register_prop_group("nsr_props", name, mod)

        if getattr(context, "area", None) is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


# ---------------------------------------------------------------------------
#  Script Browser popup
# ---------------------------------------------------------------------------

class SCRIPT_OT_browser(bpy.types.Operator):
    """Open the script & node tree browser"""
    bl_idname = "script_runner.browser"
    bl_label = "Script Browser"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── User Scripts section ──────────────────────────────────────
        box = layout.box()
        box.label(text="Scripts", icon='TEXT')

        props = scene.dynamic_script_runner
        row = box.row(align=True)
        row.prop(props, "selected_script", text="")
        row.operator("script_runner.reload_scripts", icon='FILE_REFRESH', text="")

        selected = props.selected_script
        if selected in SCRIPT_REGISTRY:
            op_idname = f"script_runner.dynamic_{selected.lower()}"
            box.operator(op_idname, text="Configure & Run", icon='PLAY')

        # ── Node Trees section ───────────────────────────────────────
        box = layout.box()
        box.label(text="Node Trees", icon='NODETREE')

        node_props = scene.node_script_runner
        row = box.row(align=True)
        row.prop(node_props, "selected_script", text="")
        row.operator("node_runner.reload_scripts", icon='FILE_REFRESH', text="")

        selected_node = node_props.selected_script
        if selected_node in NODE_SCRIPT_REGISTRY:
            box.operator(
                "node_runner.run_script",
                text="Build Node Tree",
                icon='PLAY',
            ).script_name = selected_node

    def execute(self, context):
        return {'FINISHED'}


class OBJECT_PT_script_browser_button(bpy.types.Panel):
    """One-line sidebar entry point for the script browser popup"""
    bl_label = "Scripts"
    bl_idname = "OBJECT_PT_script_browser_button"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Script Runner'

    def draw(self, context):
        self.layout.operator("script_runner.browser", icon='WINDOW', text="Open Script Browser")


# ---------------------------------------------------------------------------
#  Startup timer
# ---------------------------------------------------------------------------

def _reload_all():
    if hasattr(bpy.ops, "script_runner") and hasattr(bpy.ops.script_runner, "reload_scripts"):
        print("Reloading scripts on startup.")
        bpy.ops.script_runner.reload_scripts()
    if hasattr(bpy.ops, "node_runner") and hasattr(bpy.ops.node_runner, "reload_scripts"):
        print("Reloading node scripts on startup.")
        bpy.ops.node_runner.reload_scripts()
    return None


# ---------------------------------------------------------------------------
#  Register / Unregister
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(DynamicScriptSettings)
    bpy.utils.register_class(NodeScriptSettings)
    bpy.utils.register_class(SR_OT_reload_scripts)
    bpy.utils.register_class(NODE_OT_reload_node_scripts)
    bpy.utils.register_class(NODE_OT_run_script)
    bpy.utils.register_class(SCRIPT_OT_browser)
    bpy.utils.register_class(OBJECT_PT_script_browser_button)

    bpy.types.Scene.dynamic_script_runner = bpy.props.PointerProperty(type=DynamicScriptSettings)
    bpy.types.Scene.node_script_runner = bpy.props.PointerProperty(type=NodeScriptSettings)
    bpy.app.timers.register(_reload_all, first_interval=1.0)

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

    bpy.utils.unregister_class(OBJECT_PT_script_browser_button)
    bpy.utils.unregister_class(SCRIPT_OT_browser)
    bpy.utils.unregister_class(NODE_OT_run_script)
    bpy.utils.unregister_class(NODE_OT_reload_node_scripts)
    bpy.utils.unregister_class(SR_OT_reload_scripts)
    bpy.utils.unregister_class(NodeScriptSettings)
    bpy.utils.unregister_class(DynamicScriptSettings)
    del bpy.types.Scene.dynamic_script_runner
    del bpy.types.Scene.node_script_runner

if __name__ == "__main__":
    register()
