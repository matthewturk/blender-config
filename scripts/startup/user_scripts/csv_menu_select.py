import bpy
import csv

# Builds (or updates) a standalone geometry node group: a Menu Switch driven
# by a CSV's name column, returning a value from another column. The return
# type (INT/FLOAT/STRING) is inferred from that column's actual values.
#
# Safe to rerun against changed data: only the internal implementation nodes
# (the Menu Switch itself) get rebuilt from scratch each time. The group's
# interface sockets ("Menu" in, "Value" out) are only created if missing and
# otherwise left alone, so any links made to this group from other node
# trees survive a rerun - they're stored against the interface socket, not
# the internal nodes. The one exception: if a rerun's value column has a
# different inferred type than last time, the "Value" socket's type has to
# change too, which does invalidate existing links to it - unavoidable,
# since a socket can't change type in place while staying connected to
# something expecting the old one.

PARAMS = {
    "csv_path": {
        "type": "FILE_PATH",
        "default": "",
        "name": "CSV File",
        "description": "CSV file to build the menu from",
    },
    "name_column": {
        "type": "STRING",
        "default": "",
        "name": "Name Column",
        "description": "Column providing the dropdown's display names",
    },
    "value_column": {
        "type": "STRING",
        "default": "",
        "name": "Value Column",
        "description": "Column providing the value returned for the selected item",
    },
    "node_group_name": {
        "type": "STRING",
        "default": "CSV Menu Select",
        "name": "Node Group Name",
        "description": "Name of the node group to create or update",
    },
}

VALUE_SOCKET_TYPE = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "STRING": "NodeSocketString",
}

MAX_NAME_BYTES = 63  # Blender's name-length ceiling is a UTF-8 BYTE limit, not a character count


def _truncate_utf8(name, max_bytes):
    encoded = name.encode("utf-8")
    if len(encoded) <= max_bytes:
        return name
    # A byte-level slice can land mid-character; errors="ignore" drops
    # whatever incomplete trailing bytes that leaves instead of raising.
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _sanitize_menu_name(raw_name, max_bytes=MAX_NAME_BYTES):
    """Collapse stray whitespace and truncate to Blender's name-length limit.

    enum_items.new() silently truncates a too-long name internally, but the
    matching input socket it creates only exists under that truncated name -
    looking it up with the original, untruncated string then fails. Doing
    the truncation ourselves first keeps the two in sync. The limit is
    counted in UTF-8 bytes (Blender's real internal limit), not Python
    characters - a name can be under the character count and still be too
    long in bytes once it has any non-ASCII characters, or once a
    multi-byte marker like an ellipsis is appended.
    """
    name = " ".join(raw_name.split())
    if len(name.encode("utf-8")) <= max_bytes:
        return name
    marker = "..."
    budget = max_bytes - len(marker.encode("utf-8"))
    return _truncate_utf8(name, budget).rstrip() + marker


def _dedupe_menu_name(name, existing, max_bytes=MAX_NAME_BYTES):
    """Disambiguate `name` against `existing` with a ' (2)', ' (3)', ... suffix.

    Needed for both genuine duplicate labels in the source data and the
    truncation above accidentally making two originally-distinct names
    collide once cut down to the byte limit.
    """
    if name not in existing:
        return name
    n = 2
    while True:
        suffix = f" ({n})"
        budget = max_bytes - len(suffix.encode("utf-8"))
        candidate = _truncate_utf8(name, budget).rstrip() + suffix
        if candidate not in existing:
            return candidate
        n += 1


def _is_int(raw):
    try:
        int(raw)
        return True
    except ValueError:
        return False


def _is_float(raw):
    try:
        float(raw)
        return True
    except ValueError:
        return False


def _infer_value_type(raw_values):
    if all(_is_int(v) for v in raw_values):
        return "INT"
    if all(_is_float(v) for v in raw_values):
        return "FLOAT"
    return "STRING"


def _coerce(raw, value_type):
    if value_type == "INT":
        return int(raw)
    if value_type == "FLOAT":
        return float(raw)
    return raw


def ensure_socket(tree, in_out, name, socket_type):
    for item in tree.interface.items_tree:
        if (
            getattr(item, "item_type", None) == "SOCKET"
            and item.in_out == in_out
            and item.name == name
        ):
            if item.socket_type == socket_type:
                return item
            # Type changed since the last run - has to be replaced, which
            # breaks any existing link to it (a socket can't change type
            # while staying connected to something expecting the old one).
            tree.interface.remove(item)
            break
    return tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)


def execute(context, params):
    csv_path = bpy.path.abspath(params["csv_path"])
    name_column = params["name_column"]
    value_column = params["value_column"]
    node_group_name = params["node_group_name"]

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No rows found in '{csv_path}'")

    if name_column not in rows[0]:
        raise ValueError(f"Name column '{name_column}' not found. Available: {list(rows[0].keys())}")
    if value_column not in rows[0]:
        raise ValueError(f"Value column '{value_column}' not found. Available: {list(rows[0].keys())}")

    value_type = _infer_value_type([row[value_column] for row in rows])
    socket_type = VALUE_SOCKET_TYPE[value_type]

    items = {}
    for row in rows:
        raw_name = row[name_column].strip()
        if not raw_name:
            continue
        name = _sanitize_menu_name(raw_name)
        if name in items:
            deduped = _dedupe_menu_name(name, items)
            print(f"Menu name collision ('{raw_name}' -> '{name}'); using '{deduped}' instead")
            name = deduped
        items[name] = _coerce(row[value_column].strip(), value_type)

    if not items:
        raise ValueError("No usable rows (every name was blank)")

    # ── get/create the node group, wipe only the internal implementation
    # nodes - the boundary nodes and interface sockets stay put so links
    # made to this group from other trees survive a rerun ──
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

    ensure_socket(node_tree, "INPUT", "Menu", "NodeSocketMenu")
    ensure_socket(node_tree, "OUTPUT", "Value", socket_type)

    switch = nodes.new("GeometryNodeMenuSwitch")
    switch.data_type = value_type
    switch.enum_items.clear()
    switch.location = (0, 0)

    for name, value in items.items():
        switch.enum_items.new(name)  # also creates a same-named input socket on `switch`
        switch.inputs[name].default_value = value

    node_tree.links.new(group_input.outputs["Menu"], switch.inputs["Menu"])
    node_tree.links.new(switch.outputs[0], group_output.inputs["Value"])

    print(f"Built '{node_group_name}': {len(items)} items, value type={value_type}")
    return {"FINISHED"}
