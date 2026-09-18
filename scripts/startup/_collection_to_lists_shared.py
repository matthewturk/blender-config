# Shared logic behind user_scripts/collection_to_lists.py and
# node_scripts/collection_to_lists.py - same underlying tool (turn a
# collection's objects' custom properties into name-sorted, per-object
# lists of string values) wired into two different registries. Import this
# via the repo's usual "_load_sibling" pattern (see
# user_scripts/constant_mass_emission_times.py) rather than a package-
# relative import: user_scripts/ and node_scripts/ files are loaded one at
# a time by dynamic_script_runner.py via importlib.util.spec_from_file_
# location, with no parent package context, so `from . import x` doesn't
# work from inside them.
#
# Kept out of user_scripts/ and node_scripts/ themselves (one directory up,
# in scripts/startup/) so dynamic_script_runner.py's directory scans (which
# only look for a PARAMS+execute pair or a build() function) never mistake
# this for a runnable script/node-tree entry of its own.


def natural_sort_key(name):
    """Case-insensitive, natural (numeric-aware) sort key approximating
    Blender's own BLI_strcasecmp_natural - what Collection Info's "sort
    alphabetically" (Separate Children checked) actually uses, NOT Python's
    plain sorted()/str comparison. Plain sorted() is case-SENSITIVE ordinal
    comparison, which puts every capitalized name before every lowercase one
    (in ASCII, 'Z' < 'a') - a real, confirmed bug: mixed-case object names
    desynchronized this tool's row order from Collection Info's actual
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


def order_collection_objects(collection):
    """Collection's objects, sorted with natural_sort_key - NOT
    collection.objects' own iteration order (link order, unrelated to
    name), and NOT plain sorted()/o.name either (case-sensitive, see
    natural_sort_key's docstring for the real bug that caused). Geometry
    Nodes' Collection Info node (with Separate Children checked) always
    outputs its children in Blender's own case-insensitive natural sort
    order - documented, fixed behavior on that side, not something this
    tool can change. If these lists are meant to be indexed with the same
    index Collection Info/Get List Item produces, they need the SAME order
    GN uses, or every index silently points at the wrong object.
    """
    return sorted(collection.objects, key=lambda o: natural_sort_key(o.name))


def gather_property_lists(collection, debug=False, log_prefix="[collection_to_lists]"):
    """Walk `collection`'s objects (in `order_collection_objects` order) and
    gather their custom properties into name-sorted, per-object-ordered
    lists of stringified values.

    Keys starting with "_" are skipped - Blender stores id-property UI
    metadata (e.g. "_RNA_UI") as a custom property key right alongside real
    ones, and its value is a stringified dict repr, not real data; keeping
    it would pollute every output list with that noise.

    Returns (ordered_objects, string_values) where string_values is
    {property_name: [str(value) for each object in ordered_objects]},
    keyed in sorted (deterministic) order - NOT a plain set()'s iteration
    order, which varies run to run.
    """
    ordered_objects = order_collection_objects(collection)

    all_keys = set()
    for obj in ordered_objects:
        all_keys.update(key for key in obj.keys() if not key.startswith("_"))

    string_values = {key: [] for key in sorted(all_keys)}
    for obj in ordered_objects:
        for key in string_values:
            string_values[key].append(str(obj.get(key, "")))
        if debug:
            print(f"{log_prefix} {obj.name}: " + ", ".join(
                f"{key}={obj.get(key, '')!r}" for key in string_values
            ))

    return ordered_objects, string_values
