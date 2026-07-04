import bpy

class WM_OT_CopyExtensionKeys(bpy.types.Operator):
    """Harvest active extension Package IDs and copy them to the clipboard"""
    bl_idname = "wm.copy_extension_keys"
    bl_label = "Harvest Extension Keys"
    bl_options = {'REGISTER', 'INTERNAL'}

    # Multi-line string property to display the output inside the popup dialog
    generated_json: bpy.props.StringProperty(
        name="JSON Array Output",
        description="Formatted array keys ready for config.json",
        default=""
    )

    def execute(self, context):
        keys = []
        # Harvest modern Blender 4.2+ extension entries
        for ext in bpy.utils.extensions.packages():
            if ext.is_enabled:
                pure_id = ext.module_name.split('.')[-1]
                keys.append(pure_id)

        # Format cleanly as a pretty indented JSON block snippet
        formatted_snippet = "[\n" + ",\n".join(f'    "{k}"' for k in keys) + "\n]"
        
        # 1. Automatically push directly to your OS system clipboard
        context.window_manager.clipboard = formatted_snippet
        self.report({'INFO'}, f"Copied {len(keys)} keys directly to system clipboard!")

        # 2. Store it inside the property to render in the Invoke dialog box
        self.generated_json = formatted_snippet
        return {'FINISHED'}

    def invoke(self, context, event):
        # Gather keys before drawing the interface window frame
        self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Keys copied to clipboard successfully!", icon='CHECKMARK')
        
        box = layout.box()
        # Render a text box. Setting expand=True handles multi-line formatting gracefully
        box.prop(self, "generated_json", text="", textarea=True)


def draw_preferences_button(self, context):
    """Injects our button design safely into the target view grid"""
    layout = self.layout
    row = layout.row(align=True)
    row.operator("wm.copy_extension_keys", text="Copy Chezmoi JSON Keys", icon='COPYDOWN')


def register():
    bpy.utils.register_class(WM_OT_CopyExtensionKeys)
    # Append the custom button into the main Preferences Extensions structural view layout
    bpy.types.USERPREF_PT_extensions.append(draw_preferences_button)

def unregister():
    bpy.types.USERPREF_PT_extensions.remove(draw_preferences_button)
    bpy.utils.unregister_class(WM_OT_CopyExtensionKeys)

if __name__ == "__main__":
    register()
