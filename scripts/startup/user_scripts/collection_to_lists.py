import bpy

PARAMS = {
    "input_collection": {
        "type": "COLLECTION", 
        "default": None, 
        "name": "Collection to Iterate Over",
        "description": "The scene collection where properties will be queried"
    },
    "node_group_name": {
        "type": "STRING",
        "default": "Property List",
        "name": "Output Geonode Group Name",
        "description": "The geonode group name to put the outputs into"
    }
}

def smart_refresh_and_sort_outputs(tree, target_strings):
    """
    Directly updates a node tree interface in Blender 5.1+:
    1. Removes obsolete outputs safely using items_tree.
    2. Adds missing outputs as string fields.
    3. Sorts all outputs to exactly match the order of target_strings.
    """
    target_set = set(target_strings)
    existing_outputs = set()

    # Step 1: Create a detached snapshot list from items_tree to avoid API crashes
    interface_list = list(tree.interface.items_tree)

    # Loop backwards to prevent index-shift evaluation issues during deletion
    for i in range(len(interface_list) - 1, -1, -1):
        item = interface_list[i]
        
        # Safely verify it's a valid socket interface block acting as an output channel
        if hasattr(item, 'item_type') and item.item_type == 'SOCKET' and item.in_out == 'OUTPUT':
            if item.name not in target_set:
                tree.interface.remove(item)
            else:
                existing_outputs.add(item.name)

    # Step 2: Add missing sockets
    for name in target_strings:
        if name not in existing_outputs:
            socket_interface = tree.interface.new_socket(
                name=name, 
                in_out='OUTPUT', 
                socket_type='NodeSocketString'
            )
            # Sockets default to passing Field arrays. 
            # We explicitly ensure force_non_field is False to keep them as fields.
            socket_interface.force_non_field = False

    # Step 3: Enforce precise top-to-bottom visual sorting order
    # Count how many INPUT sockets are positioned before our output blocks
    input_offset = sum(
        1 for item in tree.interface.items_tree 
        if hasattr(item, 'item_type') and item.item_type == 'SOCKET' and item.in_out == 'INPUT'
    )

    # Re-order the outputs sequentially matching target_strings order
    for target_index, name in enumerate(target_strings):
        # Dynamically evaluate where this item currently sits in the items_tree stack
        current_index = next(
            i for i, item in enumerate(tree.interface.items_tree) 
            if hasattr(item, 'item_type') and item.item_type == 'SOCKET' and item.in_out == 'OUTPUT' and item.name == name
        )
        
        # Calculate its target destination slot relative to your input offset boundary
        desired_index = input_offset + target_index
        
        if current_index != desired_index:
            tree.interface.move(current_index, desired_index)

    # Force a viewport/UI redraw to instantly show layout updates
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

def execute(context, params):
    collection = params["input_collection"]
    node_group_name = params["node_group_name"]
    
    # 3. Gather properties from the collection's objects
    # We will grab a custom property called 'my_custom_prop'. 
    # If it doesn't exist, we'll fall back to the object's name.
    string_values = {_: [] for _ in list(set([item for o in collection.objects
                                              for item in o.keys()]))}
    for obj in collection.objects:
        for prop in string_values:
            prop_value = obj.get(prop, "")
            string_values[prop].append(str(prop_value))
        
    print(f"Found {len(string_values)} items to convert into nodes.")

    # 4. Get or create the Geometry Nodes modifier on the target object
    # 5. Get or create the node group tree
    node_tree = bpy.data.node_groups.get(node_group_name)
    if not node_tree:
        node_tree = bpy.data.node_groups.new(name=node_group_name, type='GeometryNodeTree')
        node_tree.use_fake_user = True

    # 1. Filter out only the nodes you want to keep
    # This leaves the base boundary nodes intact, along with their interface wires
    nodes_to_delete = [
        node for node in node_tree.nodes 
        if node.type not in ('GROUP_INPUT', 'GROUP_OUTPUT')
    ]

    # 2. Safely remove only the internal calculation nodes
    for node in nodes_to_delete:
        node_tree.nodes.remove(node)

    smart_refresh_and_sort_outputs(node_tree, sorted(string_values.keys()))
        
    # Create standard input/output nodes
    nodes = node_tree.nodes
    group_output = None
    for node in node_tree.nodes:
        if node.type == "GROUP_OUTPUT":
            group_output = node
            break
    if group_output is None:
        group_output = nodes.new(type='NodeGroupOutput')
    
    # Position input and output
    group_output.location = (400, 0)
    
    # Ensure Group Output has a Geometry socket (if it's a fresh tree)
    # if not node_tree.outputs.get("Geometry"):
    #     node_tree.outputs.new('NodeSocketGeometry', "Geometry")
    #     
    # # Link input geometry straight to output geometry as a baseline
    # node_tree.links.new(group_input.outputs[0], group_output.inputs[0])

    # 7. Dynamically create "String" nodes for each property value collected
    y_offset = (len(string_values) // 2) * 240
    for i, prop_name in enumerate(string_values):
        # Create a String node (Node type: 'FunctionNodeInputString')
        string_node = nodes.new(type='FunctionNodeInputString')
        string_node.name = f"DynamicString_{prop_name}"
        string_node.label = f"Prop: {prop_name[:10]}" # Truncate label for UI neatness

        split_string = nodes.new(type="FunctionNodeSplitString")
        special_characters = nodes.new(type="FunctionNodeInputSpecialCharacters")
        
        # Assign the retrieved property value to the node's string property
        string_node.string = "\n".join(string_values[prop_name])
        
        # Cascade their layout locations cleanly so they don't stack on top of each other
        string_node.location = (0, y_offset)
        split_string.location = (200, y_offset)
        y_offset -= 120
        special_characters.location = (0, y_offset)
        y_offset -= 120
        # We make new ones of these just so we can avoid the weird topology
        node_tree.links.new(string_node.outputs[0], split_string.inputs[0])
        node_tree.links.new(special_characters.outputs[0], split_string.inputs[1])

        node_tree.links.new(split_string.outputs[0], group_output.inputs[prop_name])
        
        # 3. Optional verification layout check
        print(f"Linked Field Output: {group_output.inputs[prop_name]}")

    return {'FINISHED'}
