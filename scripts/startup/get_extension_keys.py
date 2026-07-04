import bpy

class WM_OT_CopyExtensionKeys(bpy.types.Operator):
    """Harvest active extension Package IDs and copy them to the clipboard"""
    bl_idname = "wm.copy_extension_keys"
    bl_label = "Harvest Extension Keys"
    bl_options = {'REGISTER', 'INTERNAL'}

    generated_json: bpy.props.StringProperty(
        name="JSON Array Output",
        description="Formatted array keys ready for config.json"
    )

    def execute(self, context):
        # Directly gather and clean active extensions namespaced under 'bl_ext.'
        keys = [
            addon_name.split('.')[-1]
            for addon_name in context.preferences.addons.keys()
            if addon_name.startswith("bl_ext.")
        ]

        # Format as a clean JSON block snippet
        formatted_snippet = "[\n" + ",\n".join(f'    "{k}"' for k in keys) + "\n]"
        
        # Instantly copy to the clipboard and save to property
        context.window_manager.clipboard = formatted_snippet
        self.generated_json = formatted_snippet
        
        self.report({'INFO'}, f"Copied {len(keys)} extension keys to clipboard!")
        return {'FINISHED'}

    def invoke(self, context, event):
        self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Keys copied to clipboard successfully!", icon='CHECKMARK')
        layout.separator()
        
        # Modern Blender layout engines natively format multi-line text boxes smoothly
        layout.prop(self, "generated_json", text="")


def draw_preferences_button(self, context):
    self.layout.operator("wm.copy_extension_keys", text="Copy Chezmoi JSON Keys", icon='COPYDOWN')


def register():
    bpy.utils.register_class(WM_OT_CopyExtensionKeys)
    bpy.types.USERPREF_PT_extensions.append(draw_preferences_button)

def unregister():
    bpy.types.USERPREF_PT_extensions.remove(draw_preferences_button)
    bpy.utils.unregister_class(WM_OT_CopyExtensionKeys)

if __name__ == "__main__":
    register()
