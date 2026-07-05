import bpy
from bpy.app.handlers import persistent


def _build_evaluated_mesh(obj, depsgraph):
    return bpy.data.meshes.new_from_object(
        obj.evaluated_get(depsgraph),
        preserve_all_data_layers=True,
        depsgraph=depsgraph,
    )


def _iter_candidate_attributes(mesh, name_filter):
    requested_names = {name.strip() for name in name_filter.split(",") if name.strip()}

    for attribute in mesh.attributes:
        if attribute.domain != "POINT":
            continue
        if attribute.data_type not in {"FLOAT", "INT", "BOOLEAN"}:
            continue
        if attribute.name.startswith("."):
            continue
        if requested_names and attribute.name not in requested_names:
            continue
        yield attribute


def _attribute_value(data_item, data_type):
    if data_type == "BOOLEAN":
        return 1.0 if data_item.value else 0.0
    return float(data_item.value)


def _apply_attributes_to_vertex_groups(obj, mesh, name_filter):
    if len(obj.data.vertices) != len(mesh.vertices):
        raise ValueError("vertex-count mismatch")

    synced_groups = 0
    for attribute in _iter_candidate_attributes(mesh, name_filter):
        vertex_group = obj.vertex_groups.get(attribute.name)
        if vertex_group is None:
            vertex_group = obj.vertex_groups.new(name=attribute.name)

        for index, data_item in enumerate(attribute.data):
            vertex_group.add(
                [index],
                _attribute_value(data_item, attribute.data_type),
                "REPLACE",
            )
        synced_groups += 1

    if synced_groups:
        obj.data.update()
    return synced_groups


def _sync_object_vertex_groups(obj, depsgraph):
    settings = obj.gn_vertex_group_sync
    if not settings.enabled:
        return 0

    temp_mesh = _build_evaluated_mesh(obj, depsgraph)
    if temp_mesh is None:
        return 0

    try:
        return _apply_attributes_to_vertex_groups(
            obj, temp_mesh, settings.attribute_filter
        )
    finally:
        bpy.data.meshes.remove(temp_mesh)


class GNVertexGroupSyncSettings(bpy.types.PropertyGroup):
    enabled = bpy.props.BoolProperty(
        name="Enable Sync",
        description=(
            "Mirror evaluated Geometry Nodes point attributes back into "
            "vertex groups"
        ),
        default=False,
    )
    auto_sync = bpy.props.BoolProperty(
        name="Auto Sync",
        description=(
            "Refresh vertex groups automatically after dependency graph" " updates"
        ),
        default=False,
    )
    attribute_filter = bpy.props.StringProperty(
        name="Attribute Names",
        description=(
            "Comma-separated attribute names to sync; leave empty to sync "
            "every scalar point attribute"
        ),
        default="",
    )


class OBJECT_OT_sync_geonodes_vertex_groups(bpy.types.Operator):
    bl_idname = "object.sync_geonodes_vertex_groups"
    bl_label = "Sync Geometry Nodes Vertex Groups"
    bl_description = (
        "Copy evaluated Geometry Nodes point attributes onto this mesh "
        "as real vertex groups"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.object
        try:
            synced_groups = _sync_object_vertex_groups(
                obj, context.evaluated_depsgraph_get()
            )
        except ValueError:
            self.report(
                {"WARNING"},
                "Evaluated mesh has different topology; use Bake Evaluated " "Copy.",
            )
            return {"CANCELLED"}

        if synced_groups:
            self.report({"INFO"}, f"Synced {synced_groups} vertex group(s).")
            return {"FINISHED"}

        self.report({"WARNING"}, "No matching scalar point attributes were found.")
        return {"CANCELLED"}


class OBJECT_OT_bake_geonodes_vertex_groups(bpy.types.Operator):
    bl_idname = "object.bake_geonodes_vertex_groups"
    bl_label = "Bake Evaluated Copy"
    bl_description = (
        "Create a new mesh object from the evaluated Geometry Nodes result "
        "and rebuild matching vertex groups on that baked copy"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        source_obj = context.object
        settings = source_obj.gn_vertex_group_sync
        depsgraph = context.evaluated_depsgraph_get()
        baked_mesh = _build_evaluated_mesh(source_obj, depsgraph)
        if baked_mesh is None:
            self.report({"WARNING"}, "Could not evaluate mesh output.")
            return {"CANCELLED"}

        baked_obj = bpy.data.objects.new(f"{source_obj.name}_baked", baked_mesh)
        baked_obj.matrix_world = source_obj.matrix_world.copy()

        linked = False
        for collection in source_obj.users_collection:
            collection.objects.link(baked_obj)
            linked = True
        if not linked:
            context.collection.objects.link(baked_obj)

        synced_groups = _apply_attributes_to_vertex_groups(
            baked_obj, baked_mesh, settings.attribute_filter
        )
        if not synced_groups:
            for collection in tuple(baked_obj.users_collection):
                collection.objects.unlink(baked_obj)
            bpy.data.objects.remove(baked_obj)
            bpy.data.meshes.remove(baked_mesh)
            self.report({"WARNING"}, "No matching scalar point attributes were found.")
            return {"CANCELLED"}

        context.view_layer.objects.active = baked_obj
        baked_obj.select_set(True)
        self.report(
            {"INFO"},
            f"Created {baked_obj.name} with {synced_groups} vertex group(s).",
        )
        return {"FINISHED"}


class DATA_PT_geonodes_vertex_group_sync(bpy.types.Panel):
    bl_label = "Geometry Nodes Vertex Groups"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        layout = self.layout
        settings = context.object.gn_vertex_group_sync

        layout.prop(settings, "enabled")

        column = layout.column()
        column.enabled = settings.enabled
        column.prop(settings, "auto_sync")
        column.prop(settings, "attribute_filter")
        column.operator("object.sync_geonodes_vertex_groups", icon="GROUP_VERTEX")
        column.operator("object.bake_geonodes_vertex_groups", icon="DUPLICATE")


@persistent
def _depsgraph_sync_handler(scene, depsgraph):
    for update in depsgraph.updates:
        id_data = update.id
        if not isinstance(id_data, bpy.types.Object):
            continue
        if id_data.type != "MESH":
            continue

        settings = id_data.gn_vertex_group_sync
        if not (settings.enabled and settings.auto_sync):
            continue

        try:
            _sync_object_vertex_groups(id_data, depsgraph)
        except ValueError:
            continue


CLASSES = (
    GNVertexGroupSyncSettings,
    OBJECT_OT_sync_geonodes_vertex_groups,
    OBJECT_OT_bake_geonodes_vertex_groups,
    DATA_PT_geonodes_vertex_group_sync,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Object.gn_vertex_group_sync = bpy.props.PointerProperty(
        type=GNVertexGroupSyncSettings
    )

    if _depsgraph_sync_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_sync_handler)


def unregister():
    if _depsgraph_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_sync_handler)

    del bpy.types.Object.gn_vertex_group_sync

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
