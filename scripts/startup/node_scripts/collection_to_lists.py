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


def _load_sibling(module_name):
    """Load a module from scripts/startup/ (one directory up from
    node_scripts/) by file path - node_scripts/ files are loaded
    standalone by dynamic_script_runner.py (no parent package context),
    so a package-relative import doesn't work here. Same pattern as
    user_scripts/constant_mass_emission_times.py's _load_sibling.
    """
    import os
    import importlib.util

    path = os.path.join(os.path.dirname(__file__), "..", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_shared = _load_sibling("_collection_to_lists_shared")


def build(tree, params):
    from nodebpy import geometry as g

    collection = params.get("input_collection")
    if collection is None:
        tree.outputs.geometry("Output") >> tree.inputs.geometry("Geometry")
        return

    debug = params.get("debug", False)

    # See _collection_to_lists_shared.gather_property_lists: objects are
    # walked in Blender's own case-insensitive natural sort order (matching
    # Collection Info's "Separate Children" output order, so indices stay
    # aligned with it), and property keys come back sorted and with
    # underscore-prefixed id-property metadata (e.g. "_RNA_UI") filtered out.
    _ordered_objects, string_values = _shared.gather_property_lists(collection, debug=debug)

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
