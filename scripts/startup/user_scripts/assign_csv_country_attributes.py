import bpy
import csv

# Tags country wireframe objects (built by country_wireframes.py, which now
# stamps each one with geo_m49 at creation time) with attributes pulled from
# an arbitrary CSV keyed by UN M49 country code. Matching is a direct M49
# comparison - no ISO3 bridging or fuzzy name comparison needed, since the
# wireframes already carry M49 natively. Rows that don't resolve (e.g. FAO's
# region/continent aggregates, which have no single matching country) fall
# back to a name match if name_column is given, otherwise they're just
# reported as unmatched.

PARAMS = {
    "csv_path": {
        "type": "FILE_PATH",
        "default": "//Trade_DetailedTradeMatrix_E_PartnerCountries.csv",
        "name": "CSV File",
        "description": "CSV with an M49 code column and one or more value columns",
    },
    "m49_column": {
        "type": "STRING",
        "default": "M49 Code",
        "name": "M49 Column",
        "description": "Column holding the UN M49 numeric code (leading quote is stripped automatically)",
    },
    "name_column": {
        "type": "STRING",
        "default": "",
        "name": "Name Column (fallback)",
        "description": (
            "Column holding the country name, used to match rows whose M49 code "
            "doesn't resolve to a country (e.g. region aggregates). Leave blank to skip"
        ),
    },
    "value_columns": {
        "type": "STRING",
        "default": "",
        "name": "Value Columns",
        "description": (
            "Comma-separated column names to copy onto matching objects as "
            "attributes. Leave blank to copy every column except the M49 column"
        ),
    },
    "target_collection": {
        "type": "COLLECTION",
        "default": None,
        "name": "Target Collection",
        "description": "Collection of country wireframe objects to match against (defaults to 'Geo Countries')",
    },
}


def _sanitize_attr_name(column_name):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in column_name.strip().lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _coerce_value(raw):
    raw = raw.strip()
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _m49_to_int(raw):
    digits = str(raw).strip().lstrip("'").strip()
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def execute(context, params):
    csv_path = bpy.path.abspath(params["csv_path"])
    m49_column = params["m49_column"]
    name_column = params["name_column"].strip()
    target_collection = params["target_collection"] or bpy.data.collections.get("Geo Countries")

    if target_collection is None:
        raise ValueError("No target collection given, and no 'Geo Countries' collection found")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No rows found in '{csv_path}'")

    value_columns = [c.strip() for c in params["value_columns"].split(",") if c.strip()]
    if not value_columns:
        value_columns = [c for c in rows[0].keys() if c != m49_column]

    by_m49 = {}
    by_name = {}
    for obj in target_collection.all_objects:
        m49 = _m49_to_int(obj.get("geo_m49", ""))
        if m49 is not None:
            by_m49.setdefault(m49, []).append(obj)
        name = str(obj.get("geo_name", "")).strip().lower()
        if name:
            by_name.setdefault(name, []).append(obj)

    matched = 0
    unmatched_rows = []
    for row in rows:
        m49 = _m49_to_int(row.get(m49_column, ""))

        objects = by_m49.get(m49, []) if m49 is not None else []
        if not objects and name_column:
            row_name = row.get(name_column, "").strip().lower()
            objects = by_name.get(row_name, [])

        if not objects:
            unmatched_rows.append(row.get(name_column, "") or row.get(m49_column, ""))
            continue

        for obj in objects:
            for column in value_columns:
                obj[_sanitize_attr_name(column)] = _coerce_value(row.get(column, ""))
        matched += 1

    print(
        f"Matched {matched}/{len(rows)} CSV rows to objects in '{target_collection.name}'; "
        f"attributes={[_sanitize_attr_name(c) for c in value_columns]}; "
        f"{len(unmatched_rows)} unmatched: {unmatched_rows[:15]}{'...' if len(unmatched_rows) > 15 else ''}"
    )
    return {"FINISHED"}
