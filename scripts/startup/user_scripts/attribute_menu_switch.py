import bpy

# Skeleton: like `collection_to_lists.py`, this hand-builds a geometry node
# group by clearing everything but the boundary nodes and regenerating it.
# Instead of one output socket per property, it lists a source object's data
# attributes as items on a Menu Switch node, each wired to a Named Attribute
# node. The menu socket is promoted to a group input, so it shows up as an
# actual dropdown in the modifier panel.

VALUE_SOCKET_TYPE = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOLEAN": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "RGBA": "NodeSocketColor",
}

# GeometryNodeMenuSwitch.data_type spelling -> GeometryNodeInputNamedAttribute.data_type spelling
NAMED_ATTRIBUTE_TYPE = {
    "FLOAT": "FLOAT",
    "INT": "INT",
    "BOOLEAN": "BOOLEAN",
    "VECTOR": "FLOAT_VECTOR",
    "RGBA": "FLOAT_COLOR",
}

PARAMS = {
    "source_object": {
        "type": "OBJECT",
        "default": None,
        "name": "Source Object",
        "description": "Object whose data attributes populate the dropdown",
    },
    "node_group_name": {
        "type": "STRING",
        "default": "Attribute Menu Switch",
        "name": "Node Group Name",
        "description": "Name for the output geometry node group",
    },
    "output_type": {
        "type": "ENUM",
        "default": "FLOAT",
        "items": [
            ("FLOAT", "Float", "Read attributes as float values"),
            ("INT", "Integer", "Read attributes as integer values"),
            ("BOOLEAN", "Boolean", "Read attributes as boolean values"),
            ("VECTOR", "Vector", "Read attributes as vectors"),
            ("RGBA", "Color", "Read attributes as colors"),
        ],
        "name": "Value Type",
        "description": "Data type for the Menu Switch output and Named Attribute reads",
    },
}


def ensure_socket(tree, in_out, name, socket_type):
    for item in tree.interface.items_tree:
        if (
            getattr(item, "item_type", None) == "SOCKET"
            and item.in_out == in_out
            and item.name == name
        ):
            return item
    return tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)


def execute(context, params):
    source_object = params["source_object"]
    node_group_name = params["node_group_name"]
    output_type = params["output_type"]

    if source_object is None or source_object.data is None:
        print("No source object selected")
        return {"CANCELLED"}

    # TODO: adjust which attributes are worth exposing — this skips the
    # built-in "position" attribute but you may want to filter by domain
    # or data_type too.
    attr_names = sorted(
        a.name for a in source_object.data.attributes if a.name != "position"
    )
    if not attr_names:
        print(f"No attributes found on '{source_object.name}'")
        return {"CANCELLED"}

    # ── get/create the node group, wipe everything but the boundary nodes ──
    node_tree = bpy.data.node_groups.get(node_group_name)
    if node_tree is None:
        node_tree = bpy.data.node_groups.new(name=node_group_name, type="GeometryNodeTree")
        node_tree.use_fake_user = True

    for node in [n for n in node_tree.nodes if n.type not in ("GROUP_INPUT", "GROUP_OUTPUT")]:
        node_tree.nodes.remove(node)

    nodes = node_tree.nodes
    group_input = next((n for n in nodes if n.type == "GROUP_INPUT"), None) or nodes.new("NodeGroupInput")
    group_output = next((n for n in nodes if n.type == "GROUP_OUTPUT"), None) or nodes.new("NodeGroupOutput")
    group_input.location = (-400, 0)
    group_output.location = (400, 0)

    # ── interface: Geometry passthrough + the Menu dropdown + typed output ──
    ensure_socket(node_tree, "INPUT", "Geometry", "NodeSocketGeometry")
    ensure_socket(node_tree, "OUTPUT", "Geometry", "NodeSocketGeometry")
    ensure_socket(node_tree, "INPUT", "Attribute", "NodeSocketMenu")
    ensure_socket(node_tree, "OUTPUT", "Value", VALUE_SOCKET_TYPE[output_type])

    # ── Menu Switch node, with one enum item + Named Attribute per attribute ──
    switch = nodes.new("GeometryNodeMenuSwitch")
    switch.data_type = output_type
    switch.enum_items.clear()
    switch.location = (0, 0)

    named_type = NAMED_ATTRIBUTE_TYPE[output_type]
    y_offset = (len(attr_names) // 2) * 150
    for name in attr_names:
        switch.enum_items.new(name)  # also creates a same-named input socket on `switch`

        named_attr = nodes.new("GeometryNodeInputNamedAttribute")
        named_attr.data_type = named_type
        named_attr.inputs["Name"].default_value = name
        named_attr.label = name
        named_attr.location = (-250, y_offset)
        y_offset -= 150

        node_tree.links.new(named_attr.outputs[0], switch.inputs[name])

    node_tree.links.new(group_input.outputs["Attribute"], switch.inputs["Menu"])
    node_tree.links.new(group_input.outputs["Geometry"], group_output.inputs["Geometry"])
    node_tree.links.new(switch.outputs[0], group_output.inputs["Value"])

    print(f"Built '{node_group_name}' with {len(attr_names)} attribute menu items")
    return {"FINISHED"}
