import bpy
import numpy as np
import databpy as db
from nodebpy import geometry as g

# Scrapes an HDF5 file from a given root group, building one combined Curves
# object: every immediate child group under the root becomes a single curve,
# and every dataset inside that group becomes a per-point attribute on it.
# Datasets within a group must all share the same length (raises otherwise).
# A CURVE-domain "group_name" attribute records which HDF5 group each curve
# came from, since Blender may rename/truncate object names on re-runs.
#
# Also (re)builds a freestanding "<object_name> Group Names" geometry node
# group exposing that same group order as a per-curve field - Geometry
# Nodes' Named Attribute node can't read STRING attributes, so this rebuilds
# the list fresh from Python instead. It isn't attached to any modifier;
# use_fake_user keeps it around to be added manually wherever it's needed.

PARAMS = {
    "hdf5_path": {
        "type": "FILE_PATH",
        "default": "//curves.h5",
        "name": "HDF5 File",
        "description": "Path to the HDF5 file to scrape",
    },
    "curves_root": {
        "type": "STRING",
        "default": "/",
        "name": "Root Group",
        "description": "Group whose immediate child groups each become one curve",
    },
    "position_dataset": {
        "type": "STRING",
        "default": "",
        "name": "Position Dataset",
        "description": (
            "Name of an (N, 3) dataset, or 'x,y,z' comma-separated scalar "
            "dataset names, resolved within each group. Leave blank to "
            "zero-fill positions"
        ),
    },
    "object_name": {
        "type": "STRING",
        "default": "HDF5_Curves",
        "name": "Object Name",
        "description": "Name for the created Curves object and data-block",
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection to link the new object into (defaults to scene collection)",
    },
}


def _group_sort_key(name):
    """Sort integer-valued group names numerically; fall back to string order otherwise."""
    try:
        return (0, int(name))
    except ValueError:
        return (1, name)


def _gather_group_datasets(group):
    """Return {dataset_name: array} for one HDF5 group, or None if it's empty.

    Raises ValueError if the group's datasets don't all share the same length.
    """
    import h5py

    datasets = {k: np.asarray(v) for k, v in group.items() if isinstance(v, h5py.Dataset)}
    if not datasets:
        return None

    lengths = {k: arr.shape[0] for k, arr in datasets.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"Group '{group.name}' has datasets of mismatched length: {lengths}")
    return datasets


def _write_string_attribute(obj_data, name, values, domain):
    """Write a STRING attribute directly through bpy's attributes API.

    databpy's `store_named_attribute` doesn't handle STRING attributes on
    every installed version (some route straight through `foreach_set`,
    which can't take a sequence of strings), so this is done by hand instead.
    """
    attr = obj_data.attributes.get(name)
    if attr is None or attr.data_type != "STRING" or attr.domain != domain:
        if attr is not None:
            obj_data.attributes.remove(attr)
        attr = obj_data.attributes.new(name=name, type="STRING", domain=domain)
    for item, value in zip(attr.data, values):
        item.value = str(value).encode("utf-8")


def _build_group_names_node_group(name, group_names):
    """(Re)build a freestanding node group exposing `group_names` as an ordered,
    per-curve field - the same string-join + Split String trick as
    collection_to_lists.py, since Named Attribute can't read STRING attributes.
    """
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        existing.interface.clear()
        existing.nodes.clear()

    with g.tree(existing or name) as tree:
        geometry = tree.inputs.geometry("Geometry")
        tree.outputs.geometry("Output") >> geometry

        group_name_out = tree.outputs.string("Group Name")
        group_name_out._interface_socket.force_non_field = False

        string_node = tree.nodes.new("FunctionNodeInputString")
        string_node.name = "Group Names"
        string_node.label = "Group Names"
        string_node.string = "\n".join(group_names)
        string_node.location = (-400, 0)

        special_chars = tree.nodes.new("FunctionNodeInputSpecialCharacters")
        special_chars.location = (-400, -150)

        split_node = tree.nodes.new("FunctionNodeSplitString")
        split_node.location = (-180, -50)
        tree.link(string_node.outputs[0], split_node.inputs[0])
        tree.link(special_chars.outputs[0], split_node.inputs[1])

        tree.link(split_node.outputs[0], group_name_out.socket)

    node_group = bpy.data.node_groups[name]
    node_group.use_fake_user = True
    return node_group


def _resolve_positions(container, spec, n_points):
    """Build an (n_points, 3) position array from `container`, or zero-fill."""
    if not spec:
        return np.zeros((n_points, 3), dtype=np.float32)

    names = [s.strip() for s in spec.split(",") if s.strip()]
    if len(names) not in (1, 3):
        raise ValueError(f"position_dataset must name 1 or 3 datasets, got {len(names)}")

    try:
        if len(names) == 1:
            return np.asarray(container[names[0]], dtype=np.float32).reshape(n_points, 3)
        return np.stack([np.asarray(container[n], dtype=np.float32) for n in names], axis=-1)
    except KeyError as e:
        print(f"Missing position dataset {e}; zero-filling")
        return np.zeros((n_points, 3), dtype=np.float32)


def execute(context, params):
    import h5py

    hdf5_path = bpy.path.abspath(params["hdf5_path"])
    curves_root = params["curves_root"]
    position_dataset = params["position_dataset"]
    object_name = params["object_name"]
    target_collection = params["target_collection"] or context.scene.collection

    with h5py.File(hdf5_path, "r") as f:
        root = f if curves_root in ("", "/") else f[curves_root]

        group_names = sorted(
            (k for k in root.keys() if isinstance(root[k], h5py.Group)), key=_group_sort_key
        )
        if not group_names:
            raise ValueError(f"No child groups found under '{curves_root}'")

        curves = []
        for name in group_names:
            datasets = _gather_group_datasets(root[name])
            if datasets is None:
                print(f"Skipping empty group '{name}'")
                continue
            n_points = next(iter(datasets.values())).shape[0]
            curves.append((name, n_points, datasets))

        if not curves:
            raise ValueError(f"No groups with datasets found under '{curves_root}'")

        curve_lengths = [n for _, n, _ in curves]
        positions = np.concatenate(
            [_resolve_positions(root[name], position_dataset, n) for name, n, _ in curves]
        )

        attr_names = sorted({key for _, _, datasets in curves for key in datasets})
        point_attrs = {
            attr_name: np.concatenate(
                [
                    datasets.get(attr_name, np.full(n, np.nan, dtype=np.float32))
                    for _, n, datasets in curves
                ]
            )
            for attr_name in attr_names
        }
        group_names_per_curve = np.array([name for name, _, _ in curves])

    # ── Build the Curves data-block ─────────────────────────────────────
    # Rebuilding from scratch each run is simplest for varying point counts;
    # reuse the existing object (rather than orphaning + renaming) if this
    # script re-runs against the same object_name.
    existing_data = bpy.data.hair_curves.get(object_name)
    if existing_data is not None:
        bpy.data.hair_curves.remove(existing_data)
    curves_data = bpy.data.hair_curves.new(name=object_name)
    curves_data.add_curves(curve_lengths)

    obj = bpy.data.objects.get(object_name)
    if obj is None:
        obj = bpy.data.objects.new(object_name, curves_data)
        target_collection.objects.link(obj)
    elif obj.data != curves_data:
        obj.data = curves_data

    db.store_named_attribute(
        obj,
        positions.astype(np.float32),
        "position",
        atype=db.AttributeTypes.FLOAT_VECTOR,
        domain=db.AttributeDomains.POINT,
    )
    for attr_name, arr in point_attrs.items():
        db.store_named_attribute(obj, arr, attr_name, domain=db.AttributeDomains.POINT)
    _write_string_attribute(curves_data, "group_name", group_names_per_curve, domain="CURVE")

    node_group_name = f"{object_name} Group Names"
    _build_group_names_node_group(node_group_name, group_names_per_curve.tolist())

    # Hundreds of thousands of curves - especially stacked at the origin
    # with zero-filled positions - can make the viewport unresponsive.
    # Stay hidden until you deliberately toggle visibility back on.
    obj.hide_viewport = True
    obj.hide_render = True

    print(
        f"Built '{object_name}': {len(curve_lengths)} curves, "
        f"{positions.shape[0]} points, "
        f"attributes={list(point_attrs) + ['group_name']}, "
        f"node_group='{node_group_name}'"
    )
    return {"FINISHED"}
