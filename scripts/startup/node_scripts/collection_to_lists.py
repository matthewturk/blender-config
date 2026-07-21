NAME = "Collection to Lists"

PARAMS = {
    "input_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Collection",
        "description": "Collection whose objects' properties become outputs",
    },
    "node_group_name": {
        "type": "STRING",
        "default": "Collection to Lists",
        "name": "Node Group Name",
        "description": "Name for the output geometry node group",
    },
}


def build(tree, params):
    from nodebpy import geometry as g
    import bpy

    collection = params.get("input_collection")
    if collection is None:
        tree.outputs.geometry("Output") >> tree.inputs.geometry("Geometry")
        return

    # ── gather custom properties from every object ────────────────────
    all_keys = set()
    for obj in collection.objects:
        all_keys.update(obj.keys())

    string_values = {k: [] for k in sorted(all_keys)}
    for obj in collection.objects:
        for k in string_values:
            string_values[k].append(str(obj.get(k, "")))

    if not string_values:
        tree.outputs.geometry("Output") >> tree.inputs.geometry("Geometry")
        return

    # ── create output sockets (field-capable) and build nodes ─────────
    out_refs = {}
    for prop_name in string_values:
        ref = tree.outputs.string(prop_name)
        ref._interface_socket.force_non_field = False
        out_refs[prop_name] = ref

    y_offset = (len(string_values) // 2) * 240

    for prop_name, vals in string_values.items():
        string_node = tree.nodes.new("FunctionNodeInputString")
        string_node.name = f"DynamicString_{prop_name}"
        string_node.label = f"Prop: {prop_name[:10]}"
        string_node.string = "\n".join(vals)

        split_node = tree.nodes.new("FunctionNodeSplitString")
        special_node = tree.nodes.new("FunctionNodeInputSpecialCharacters")

        string_node.location = (0, y_offset)
        split_node.location = (200, y_offset)
        y_offset -= 120
        special_node.location = (0, y_offset)
        y_offset -= 120

        tree.link(string_node.outputs[0], split_node.inputs[0])
        tree.link(special_node.outputs[0], split_node.inputs[1])
        tree.link(split_node.outputs[0], out_refs[prop_name].socket)
