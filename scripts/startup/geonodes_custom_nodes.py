import bpy

GROUP_WARP = "GN Vector Field Warp"
GROUP_PROJECT_TWIST = "GN Vector Field Project Twist"
_MENU_APPENDED = False


def _input_socket(node, name, fallback_index=0):
    sock = node.inputs.get(name)
    if sock is not None:
        return sock
    return node.inputs[fallback_index]


def _output_socket(node, name, fallback_index=0):
    sock = node.outputs.get(name)
    if sock is not None:
        return sock
    return node.outputs[fallback_index]


def _connect(links, from_socket, to_socket):
    links.new(from_socket, to_socket)


def _ensure_interface_socket(node_tree, name, in_out, socket_type):
    if hasattr(node_tree, "interface"):
        for item in node_tree.interface.items_tree:
            if (
                getattr(item, "item_type", None) == "SOCKET"
                and item.in_out == in_out
                and item.name == name
            ):
                return
        node_tree.interface.new_socket(
            name=name,
            in_out=in_out,
            socket_type=socket_type,
        )
        return

    sockets = node_tree.inputs if in_out == "INPUT" else node_tree.outputs
    if sockets.get(name) is None:
        sockets.new(socket_type, name)


def _clear_tree(node_tree):
    node_tree.nodes.clear()
    node_tree.links.clear()


def _new_math(tree, operation, location):
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.location = location
    return node


def _new_vector_math(tree, operation, location):
    node = tree.nodes.new("ShaderNodeVectorMath")
    node.operation = operation
    node.location = location
    return node


def _build_vector_field_warp(node_tree):
    _clear_tree(node_tree)

    _ensure_interface_socket(node_tree, "Field", "INPUT", "NodeSocketVector")
    _ensure_interface_socket(
        node_tree,
        "Direction",
        "INPUT",
        "NodeSocketVector",
    )
    _ensure_interface_socket(node_tree, "Strength", "INPUT", "NodeSocketFloat")
    _ensure_interface_socket(node_tree, "Bias", "INPUT", "NodeSocketFloat")
    _ensure_interface_socket(
        node_tree,
        "Warped Field",
        "OUTPUT",
        "NodeSocketVector",
    )
    _ensure_interface_socket(
        node_tree,
        "Magnitude",
        "OUTPUT",
        "NodeSocketFloat",
    )

    group_in = node_tree.nodes.new("NodeGroupInput")
    group_in.location = (-900, 0)

    group_out = node_tree.nodes.new("NodeGroupOutput")
    group_out.location = (700, 0)

    normalize_dir = _new_vector_math(node_tree, "NORMALIZE", (-650, -200))
    scale_dir = _new_vector_math(node_tree, "SCALE", (-430, -200))
    add_vec = _new_vector_math(node_tree, "ADD", (-200, 0))
    length_vec = _new_vector_math(node_tree, "LENGTH", (20, 160))
    max_mag = _new_math(node_tree, "MAXIMUM", (220, 160))
    power_mag = _new_math(node_tree, "POWER", (420, 160))
    scale_by_mag = _new_vector_math(node_tree, "SCALE", (220, 0))

    max_mag.inputs[1].default_value = 0.0001

    links = node_tree.links
    _connect(
        links,
        _output_socket(group_in, "Direction"),
        _input_socket(normalize_dir, "Vector"),
    )

    _connect(
        links,
        _output_socket(normalize_dir, "Vector"),
        _input_socket(scale_dir, "Vector"),
    )
    _connect(
        links,
        _output_socket(group_in, "Strength"),
        _input_socket(scale_dir, "Scale", 1),
    )

    _connect(
        links,
        _output_socket(group_in, "Field"),
        _input_socket(add_vec, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(scale_dir, "Vector"),
        _input_socket(add_vec, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(add_vec, "Vector"),
        _input_socket(length_vec, "Vector"),
    )
    _connect(
        links,
        _output_socket(length_vec, "Value"),
        _input_socket(max_mag, "Value", 0),
    )
    _connect(
        links,
        _output_socket(max_mag, "Value"),
        _input_socket(power_mag, "Value", 0),
    )
    _connect(
        links,
        _output_socket(group_in, "Bias"),
        _input_socket(power_mag, "Value", 1),
    )

    _connect(
        links,
        _output_socket(add_vec, "Vector"),
        _input_socket(scale_by_mag, "Vector"),
    )
    _connect(
        links,
        _output_socket(power_mag, "Value"),
        _input_socket(scale_by_mag, "Scale", 1),
    )

    _connect(
        links,
        _output_socket(scale_by_mag, "Vector"),
        _input_socket(group_out, "Warped Field"),
    )
    _connect(
        links,
        _output_socket(length_vec, "Value"),
        _input_socket(group_out, "Magnitude"),
    )


def _build_vector_field_project_twist(node_tree):
    _clear_tree(node_tree)

    _ensure_interface_socket(node_tree, "Field", "INPUT", "NodeSocketVector")
    _ensure_interface_socket(node_tree, "Axis", "INPUT", "NodeSocketVector")
    _ensure_interface_socket(
        node_tree,
        "Twist Strength",
        "INPUT",
        "NodeSocketFloat",
    )
    _ensure_interface_socket(node_tree, "Blend", "INPUT", "NodeSocketFloat")
    _ensure_interface_socket(
        node_tree,
        "Result Field",
        "OUTPUT",
        "NodeSocketVector",
    )
    _ensure_interface_socket(
        node_tree,
        "Projected",
        "OUTPUT",
        "NodeSocketVector",
    )
    _ensure_interface_socket(
        node_tree,
        "Twist Component",
        "OUTPUT",
        "NodeSocketVector",
    )

    group_in = node_tree.nodes.new("NodeGroupInput")
    group_in.location = (-1100, -40)

    group_out = node_tree.nodes.new("NodeGroupOutput")
    group_out.location = (750, 20)

    normalize_axis = _new_vector_math(node_tree, "NORMALIZE", (-860, -250))
    dot_proj = _new_vector_math(node_tree, "DOT_PRODUCT", (-650, -40))
    scale_proj = _new_vector_math(node_tree, "SCALE", (-450, -250))
    reject_vec = _new_vector_math(node_tree, "SUBTRACT", (-250, -40))
    cross_twist = _new_vector_math(node_tree, "CROSS_PRODUCT", (-40, -220))
    scale_twist = _new_vector_math(node_tree, "SCALE", (180, -220))
    add_twist = _new_vector_math(node_tree, "ADD", (180, -40))
    recombine = _new_vector_math(node_tree, "ADD", (380, -40))
    lerp_final = _new_vector_math(node_tree, "LERP", (560, 80))

    links = node_tree.links
    _connect(
        links,
        _output_socket(group_in, "Axis"),
        _input_socket(normalize_axis, "Vector"),
    )

    _connect(
        links,
        _output_socket(group_in, "Field"),
        _input_socket(dot_proj, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(normalize_axis, "Vector"),
        _input_socket(dot_proj, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(normalize_axis, "Vector"),
        _input_socket(scale_proj, "Vector"),
    )
    _connect(
        links,
        _output_socket(dot_proj, "Value"),
        _input_socket(scale_proj, "Scale", 1),
    )

    _connect(
        links,
        _output_socket(group_in, "Field"),
        _input_socket(reject_vec, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(scale_proj, "Vector"),
        _input_socket(reject_vec, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(reject_vec, "Vector"),
        _input_socket(cross_twist, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(normalize_axis, "Vector"),
        _input_socket(cross_twist, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(cross_twist, "Vector"),
        _input_socket(scale_twist, "Vector"),
    )
    _connect(
        links,
        _output_socket(group_in, "Twist Strength"),
        _input_socket(scale_twist, "Scale", 1),
    )

    _connect(
        links,
        _output_socket(reject_vec, "Vector"),
        _input_socket(add_twist, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(scale_twist, "Vector"),
        _input_socket(add_twist, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(add_twist, "Vector"),
        _input_socket(recombine, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(scale_proj, "Vector"),
        _input_socket(recombine, "Vector", 1),
    )

    _connect(
        links,
        _output_socket(group_in, "Field"),
        _input_socket(lerp_final, "Vector", 0),
    )
    _connect(
        links,
        _output_socket(recombine, "Vector"),
        _input_socket(lerp_final, "Vector", 1),
    )
    _connect(
        links,
        _output_socket(group_in, "Blend"),
        _input_socket(lerp_final, "Scale", 2),
    )

    _connect(
        links,
        _output_socket(lerp_final, "Vector"),
        _input_socket(group_out, "Result Field"),
    )
    _connect(
        links,
        _output_socket(scale_proj, "Vector"),
        _input_socket(group_out, "Projected"),
    )
    _connect(
        links,
        _output_socket(scale_twist, "Vector"),
        _input_socket(group_out, "Twist Component"),
    )


def _ensure_group(name, build_fn):
    node_tree = bpy.data.node_groups.get(name)
    if node_tree is None or node_tree.bl_idname != "GeometryNodeTree":
        node_tree = bpy.data.node_groups.new(
            name=name,
            type="GeometryNodeTree",
        )

    build_fn(node_tree)
    return node_tree


def ensure_custom_groups():
    _ensure_group(GROUP_WARP, _build_vector_field_warp)
    _ensure_group(GROUP_PROJECT_TWIST, _build_vector_field_project_twist)


class NODE_OT_ensure_gn_custom_groups(bpy.types.Operator):
    bl_idname = "node.ensure_gn_custom_groups"
    bl_label = "Ensure GN Custom Vector Field Groups"
    bl_description = "Create or refresh custom Geometry Nodes " "vector-field groups"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_custom_groups()
        self.report({"INFO"}, "Custom vector-field groups are ready.")
        return {"FINISHED"}


class NODE_OT_add_gn_custom_group(bpy.types.Operator):
    bl_idname = "node.add_gn_custom_group"
    bl_label = "Add GN Custom Vector Field Node"
    bl_description = "Insert a custom Geometry Nodes vector-field group node"
    bl_options = {"REGISTER", "UNDO"}

    group_name = bpy.props.EnumProperty(
        name="Group",
        items=(
            (
                GROUP_WARP,
                "Vector Field Warp",
                "Warp and amplify a vector field",
            ),
            (
                GROUP_PROJECT_TWIST,
                "Vector Field Project Twist",
                "Project field on an axis, add twist, and blend",
            ),
        ),
    )

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if space is None or space.type != "NODE_EDITOR":
            return False
        tree = space.edit_tree
        return tree is not None and tree.bl_idname == "GeometryNodeTree"

    def execute(self, context):
        ensure_custom_groups()

        tree = context.space_data.edit_tree
        group = bpy.data.node_groups.get(self.group_name)
        if group is None:
            self.report({"WARNING"}, "Could not find requested custom group.")
            return {"CANCELLED"}

        node = tree.nodes.new("GeometryNodeGroup")
        node.node_tree = group

        space = context.space_data
        if hasattr(space, "cursor_location"):
            node.location = space.cursor_location

        self.report({"INFO"}, f"Inserted {group.name}.")
        return {"FINISHED"}


def _draw_node_add_menu(self, context):
    space = context.space_data
    tree = getattr(space, "edit_tree", None)
    if tree is None or tree.bl_idname != "GeometryNodeTree":
        return

    layout = self.layout
    layout.separator()
    layout.operator(
        "node.add_gn_custom_group",
        text="Vector Field Warp",
        icon="NODETREE",
    ).group_name = GROUP_WARP
    layout.operator(
        "node.add_gn_custom_group",
        text="Vector Field Project Twist",
        icon="NODETREE",
    ).group_name = GROUP_PROJECT_TWIST


CLASSES = (
    NODE_OT_ensure_gn_custom_groups,
    NODE_OT_add_gn_custom_group,
)


def register():
    global _MENU_APPENDED

    for cls in CLASSES:
        bpy.utils.register_class(cls)

    if not _MENU_APPENDED:
        bpy.types.NODE_MT_add.append(_draw_node_add_menu)
        _MENU_APPENDED = True

    ensure_custom_groups()


def unregister():
    global _MENU_APPENDED

    if _MENU_APPENDED:
        bpy.types.NODE_MT_add.remove(_draw_node_add_menu)
        _MENU_APPENDED = False

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
