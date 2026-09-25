"""Shared CSV-loading helpers for the halo-ancestry importers
(user_scripts/blender_halo_import.py and user_scripts/blender_halo_curves.py) -
kept here, one directory up from user_scripts/, following this repo's
established pattern for sharing code between scripts in user_scripts/ (see
e.g. _collection_to_lists_shared.py, _frame_stack_animation.py) since that
folder has no package context of its own.
"""


def column(header, name):
    """Find a column by its name without the "[units]" suffix."""
    for h in header:
        if h.split(" [")[0] == name:
            return h
    raise KeyError(f"No '{name}' column in CSV")


def load(path):
    import csv

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    cols = {k: column(header, k) for k in ("x", "y", "z", "mass", "time")}
    cols.update({f"desc_{k}": column(header, f"desc_{k}") for k in ("x", "y", "z", "mass", "time")})

    halos = []
    for r in rows:
        h = {
            "uid": int(r["uid"]),
            "branch_id": int(r["branch_id"]),
            "main_branch": r["main_branch"] == "1",
            "snapshot": int(r["snapshot"]),
            "desc_snapshot": int(r["desc_snapshot"]),
            "scale_factor": float(r["scale_factor"]),
            "desc_scale_factor": float(r["desc_scale_factor"]),
        }
        for k, c in cols.items():
            h[k] = float(r[c])
        halos.append(h)
    return halos
