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
    "debug": {
        "type": "BOOL",
        "default": False,
        "name": "Debug Output",
        "description": "Print each object's name and every gathered property value, in the exact order they're written into the node group, to the system console",
    },
}


def _natural_sort_key(name):
    """Case-insensitive, natural (numeric-aware) sort key approximating
    Blender's own BLI_strcasecmp_natural - what Collection Info's "sort
    alphabetically" (Separate Children checked) actually uses, NOT Python's
    plain sorted()/str comparison. Plain sorted() is case-SENSITIVE ordinal
    comparison, which puts every capitalized name before every lowercase one
    (in ASCII, 'Z' < 'a') - a real, confirmed bug: mixed-case object names
    desynchronized this script's row order from Collection Info's actual
    children order starting at the first lowercase name, silently pointing
    indices at the wrong object from then on.

    Each chunk is tagged (0, text) or (1, number) so chunks never compare
    across types at the same position - avoiding any TypeError from
    comparing an int to a str.
    """
    import re
    return [
        (1, int(chunk)) if chunk.isdigit() else (0, chunk.lower())
        for chunk in re.split(r"(\d+)", name) if chunk
    ]


def build(tree, params):
    from nodebpy import geometry as g
    import bpy

    collection = params.get("input_collection")
    if collection is None:
        tree.outputs.geometry("Output") >> tree.inputs.geometry("Geometry")
        return

    debug = params.get("debug", False)

    # Sorted with _natural_sort_key - NOT collection.objects' own iteration
    # order (link order, unrelated to name), and NOT plain sorted()/o.name
    # either (case-sensitive, see _natural_sort_key's docstring for the real
    # bug that caused). Geometry Nodes' Collection Info node (with Separate
    # Children checked) always outputs its children in Blender's own
    # case-insensitive natural sort order - documented, fixed behavior on
    # that side, not something this script can change. If these lists are
    # meant to be indexed with the same index Collection Info/Get List Item
    # produces, they need the SAME order GN uses, or every index silently
    # points at the wrong object.
    ordered_objects = sorted(collection.objects, key=lambda o: _natural_sort_key(o.name))

    # ── gather custom properties from every object ────────────────────
    all_keys = set()
    for obj in ordered_objects:
        all_keys.update(obj.keys())

    string_values = {k: [] for k in sorted(all_keys)}
    for obj in ordered_objects:
        for k in string_values:
            string_values[k].append(str(obj.get(k, "")))
        if debug:
            print(f"[collection_to_lists] {obj.name}: " + ", ".join(
                f"{k}={obj.get(k, '')!r}" for k in string_values
            ))

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
