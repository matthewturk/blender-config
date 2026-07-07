import math

import bpy
import bmesh


def _as_text(value):
    if isinstance(value, str):
        return value
    return ""


def _tokenize_values(raw_text):
    separators = [",", ";", "\n", "\t"]
    normalized = _as_text(raw_text)
    for sep in separators[1:]:
        normalized = normalized.replace(sep, separators[0])
    return [token.strip() for token in normalized.split(separators[0]) if token.strip()]


def _load_world_dataset(gpd):
    # geopandas < 1.0 ships naturalearth_lowres; newer versions removed it.
    try:
        return gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    except Exception:
        pass

    # Fallback: read countries directly from Natural Earth.
    url = (
        "https://naturalearth.s3.amazonaws.com/"
        "110m_cultural/ne_110m_admin_0_countries.zip"
    )
    try:
        return gpd.read_file(url)
    except Exception as exc:
        raise RuntimeError(
            "Could not load world boundaries from geopandas built-ins or "
            "Natural Earth URL. If you are offline, use geopandas with "
            "bundled "
            "datasets or pre-download the Natural Earth countries ZIP. "
            f"Last error: {exc}"
        ) from exc


def _pick_column(columns, candidates):
    lower_map = {str(col).lower(): col for col in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        lowered = str(candidate).lower()
        if lowered in lower_map:
            return lower_map[lowered]
    return None


def _normalize_world_columns(gpd, world):
    geometry_series = world.geometry

    name_col = _pick_column(
        world.columns,
        ["name", "name_en", "admin", "formal_en", "sovereignt"],
    )
    iso2_col = _pick_column(
        world.columns,
        ["iso_a2", "iso_a2_eh", "wb_a2", "adm0_a2"],
    )
    iso3_col = _pick_column(
        world.columns,
        ["iso_a3", "iso_a3_eh", "adm0_a3", "wb_a3", "gu_a3"],
    )
    continent_col = _pick_column(
        world.columns,
        ["continent", "region_un", "region_wb"],
    )

    if name_col is None:
        name_series = ["Unknown"] * len(world)
    else:
        name_series = world[name_col].fillna("Unknown").astype(str)

    if iso2_col is None:
        iso2_series = [""] * len(world)
    else:
        iso2_series = world[iso2_col].fillna("").astype(str)

    if iso3_col is None:
        iso3_series = [""] * len(world)
    else:
        iso3_series = world[iso3_col].fillna("").astype(str)

    if continent_col is None:
        continent_series = ["Unknown"] * len(world)
    else:
        continent_series = world[continent_col].fillna("Unknown").astype(str)

    normalized = gpd.GeoDataFrame(
        {
            "name": name_series,
            "iso_a2": iso2_series,
            "iso_a3": iso3_series,
            "continent": continent_series,
            "geometry": geometry_series,
        },
        geometry="geometry",
        crs=world.crs,
    )
    return normalized


def _load_geo_data():
    try:
        import geopandas as gpd
    except Exception as exc:
        raise RuntimeError(f"Could not import geopandas: {exc}") from exc

    try:
        from geonamescache import GeonamesCache
    except Exception as exc:
        raise RuntimeError(f"Could not import geonamescache: {exc}") from exc

    world = _load_world_dataset(gpd)
    world = _normalize_world_columns(gpd, world)
    world = world.dropna(subset=["geometry"])

    # Canonical lookup from Natural Earth names/codes
    countries_by_key = {}
    for _, row in world.iterrows():
        name = str(row["name"])
        iso2 = str(row["iso_a2"]).upper()
        iso3 = str(row["iso_a3"]).upper()
        countries_by_key[name.lower()] = row
        if iso2 and iso2 != "-99":
            countries_by_key[iso2.lower()] = row
        if iso3 and iso3 != "-99":
            countries_by_key[iso3.lower()] = row

    # Alias lookup from geonamescache to map common ISO/name variants.
    gc = GeonamesCache()
    for iso2, info in gc.get_countries().items():
        iso2_key = str(iso2).upper()
        iso3_key = str(info.get("iso3", "")).upper()
        name_key = str(info.get("name", "")).strip().lower()

        row = None
        if iso2_key and iso2_key.lower() in countries_by_key:
            row = countries_by_key[iso2_key.lower()]
        elif iso3_key and iso3_key.lower() in countries_by_key:
            row = countries_by_key[iso3_key.lower()]

        if row is None:
            continue

        if name_key:
            countries_by_key[name_key] = row
        if iso2_key:
            countries_by_key[iso2_key.lower()] = row
        if iso3_key:
            countries_by_key[iso3_key.lower()] = row

    # Build continent centroids from unioned geometries.
    continents = {}
    grouped = world.groupby("continent")
    for continent, subset in grouped:
        continent_name = str(continent)
        if continent_name.lower() == "seven seas (open ocean)":
            continue
        unioned = subset.unary_union
        point = unioned.representative_point()
        continents[continent_name.lower()] = {
            "name": continent_name,
            "point": point,
            "geometry": unioned,
        }

    return world, countries_by_key, continents


def _latlon_to_xyz(lat_deg, lon_deg, radius):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    x = radius * cos_lat * math.cos(lon)
    y = radius * cos_lat * math.sin(lon)
    z = radius * math.sin(lat)
    return (x, y, z)


def _to_uv(lat_deg, lon_deg):
    u = (lon_deg + 180.0) / 360.0
    v = (lat_deg + 90.0) / 180.0
    return (u, v)


def _get_or_create_collection(parent, name):
    existing = bpy.data.collections.get(name)
    if existing is None:
        existing = bpy.data.collections.new(name)
        parent.children.link(existing)
    elif existing.name not in parent.children:
        parent.children.link(existing)
    return existing


def _build_sphere_mesh(
    mesh_name,
    radius,
    resolution,
    add_surface,
):
    mesh = bpy.data.meshes.new(mesh_name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=resolution,
        v_segments=max(3, resolution // 2),
        radius=radius,
    )
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    uv_layer = mesh.uv_layers.new(name="GeoUV")
    if uv_layer is not None:
        uv_data = uv_layer.data
        loops = mesh.loops
        vertices = mesh.vertices
        for i, loop in enumerate(loops):
            coord = vertices[loop.vertex_index].co
            length = max(coord.length, 1e-8)
            z_ratio = coord.z / length
            z_ratio = max(-1.0, min(1.0, z_ratio))
            lat = math.degrees(math.asin(z_ratio))
            lon = math.degrees(math.atan2(coord.y, coord.x))
            uv_data[i].uv = _to_uv(lat, lon)

    if not add_surface:
        mesh.polygons.foreach_set("hide", [True] * len(mesh.polygons))

    return mesh


def _iter_line_coords(geom):
    if geom is None:
        return

    gtype = getattr(geom, "geom_type", "")
    if gtype == "LineString":
        yield list(geom.coords)
        return

    if gtype in {"MultiLineString", "GeometryCollection"}:
        for sub in geom.geoms:
            yield from _iter_line_coords(sub)
        return

    if gtype in {"Polygon", "MultiPolygon"}:
        yield from _iter_line_coords(geom.boundary)


def _create_boundary_wire_object(
    collection,
    obj_name,
    geometry,
    globe_radius,
    kind,
    geo_name,
    continent_name,
    iso2,
    iso3,
):
    vertices = []
    edges = []
    offset = 0

    for coords in _iter_line_coords(geometry):
        if len(coords) < 2:
            continue

        local_points = []
        for lon, lat, *_rest in coords:
            local_points.append(_latlon_to_xyz(lat, lon, globe_radius))

        vertices.extend(local_points)
        for i in range(len(local_points) - 1):
            edges.append((offset + i, offset + i + 1))
        offset += len(local_points)

    if not vertices or not edges:
        return None

    mesh = bpy.data.meshes.new(f"{obj_name}_Mesh")
    mesh.from_pydata(vertices, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(obj_name, mesh)
    obj.display_type = "WIRE"
    obj["geo_kind"] = kind
    obj["geo_name"] = geo_name
    obj["geo_continent"] = continent_name
    obj["geo_iso2"] = iso2
    obj["geo_iso3"] = iso3
    collection.objects.link(obj)
    return obj


def _create_reference_globe(collection, radius, resolution):
    mesh = _build_sphere_mesh(
        "GeoReferenceGlobeMesh",
        radius,
        max(8, resolution),
        add_surface=True,
    )
    obj = bpy.data.objects.new("GeoReferenceGlobe", mesh)
    obj.display_type = "SOLID"
    obj["geo_kind"] = "reference_globe"
    obj["geo_name"] = "reference_globe"
    obj["geo_continent"] = ""
    obj["geo_iso2"] = ""
    obj["geo_iso3"] = ""
    for poly in mesh.polygons:
        poly.use_smooth = True
    collection.objects.link(obj)
    return obj


def _sync_country_items_from_world(settings, world):
    selected_by_name = {item.name: item.selected for item in settings.country_items}
    settings.country_items.clear()

    seen = set()
    sorted_world = world.sort_values(by="name")
    for _, row in sorted_world.iterrows():
        name = str(row["name"]).strip()
        if not name:
            continue

        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)

        item = settings.country_items.add()
        item.name = name
        item.iso2 = str(row["iso_a2"]).upper()
        item.iso3 = str(row["iso_a3"]).upper()
        item.continent = str(row["continent"])
        item.selected = bool(selected_by_name.get(name, False))


def _make_linked_instance(
    name,
    source_mesh,
    location,
    collection,
    kind,
    geo_name,
    continent_name,
    iso2,
    iso3,
):
    obj = bpy.data.objects.new(name, source_mesh)
    obj.location = location
    obj.display_type = "WIRE"
    obj["geo_kind"] = kind
    obj["geo_name"] = geo_name
    obj["geo_continent"] = continent_name
    obj["geo_iso2"] = iso2
    obj["geo_iso3"] = iso3
    collection.objects.link(obj)
    return obj


def _write_anchor_attributes(anchor_obj, items):
    mesh = anchor_obj.data
    if len(mesh.vertices) != len(items):
        return

    try:
        attr_kind = mesh.attributes.get("geo_kind")
        if attr_kind is None:
            attr_kind = mesh.attributes.new("geo_kind", "STRING", "POINT")

        attr_name = mesh.attributes.get("geo_name")
        if attr_name is None:
            attr_name = mesh.attributes.new("geo_name", "STRING", "POINT")

        attr_cont = mesh.attributes.get("geo_continent")
        if attr_cont is None:
            attr_cont = mesh.attributes.new("geo_continent", "STRING", "POINT")

        attr_iso2 = mesh.attributes.get("geo_iso2")
        if attr_iso2 is None:
            attr_iso2 = mesh.attributes.new("geo_iso2", "STRING", "POINT")

        attr_iso3 = mesh.attributes.get("geo_iso3")
        if attr_iso3 is None:
            attr_iso3 = mesh.attributes.new("geo_iso3", "STRING", "POINT")

        attr_index = mesh.attributes.get("geo_index")
        if attr_index is None:
            attr_index = mesh.attributes.new("geo_index", "INT", "POINT")

        attr_uv = mesh.attributes.get("geo_uv")
        if attr_uv is None:
            attr_uv = mesh.attributes.new("geo_uv", "FLOAT2", "POINT")
    except Exception as exc:
        print(f"[Geo Wireframes] Could not create anchor attributes: {exc}")
        return

    def _as_attr_bytes(value):
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    for i, item in enumerate(items):
        attr_kind.data[i].value = _as_attr_bytes(item["kind"])
        attr_name.data[i].value = _as_attr_bytes(item["name"])
        attr_cont.data[i].value = _as_attr_bytes(item["continent"])
        attr_iso2.data[i].value = _as_attr_bytes(item["iso2"])
        attr_iso3.data[i].value = _as_attr_bytes(item["iso3"])
        attr_index.data[i].value = i
        attr_uv.data[i].vector = item["uv"]


def _create_anchor_object(context, name, points, items, collection):
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(points, [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.hide_render = True
    obj.display_type = "BOUNDS"
    obj["geo_description"] = (
        "Use this point mesh in Geometry Nodes; it stores string IDs and "
        "UV-like "
        "lat/lon coordinates in attributes."
    )
    collection.objects.link(obj)
    _write_anchor_attributes(obj, items)
    return obj


def _socket_by_name(sockets, name):
    for socket in sockets:
        if socket.name == name:
            return socket
    return None


def _clear_group_interface(node_group):
    if not hasattr(node_group, "interface"):
        if hasattr(node_group, "inputs"):
            while node_group.inputs:
                node_group.inputs.remove(node_group.inputs[-1])
        if hasattr(node_group, "outputs"):
            while node_group.outputs:
                node_group.outputs.remove(node_group.outputs[-1])
        return

    items = list(node_group.interface.items_tree)
    for item in items:
        try:
            node_group.interface.remove(item)
        except Exception:
            pass


def _create_group_socket(node_group, name, in_out, socket_type):
    if hasattr(node_group, "interface"):
        return node_group.interface.new_socket(
            name=name,
            in_out=in_out,
            socket_type=socket_type,
        )

    if in_out == "INPUT":
        return node_group.inputs.new(socket_type, name)
    return node_group.outputs.new(socket_type, name)


def _set_group_input_default(node_group, socket_name, value):
    if hasattr(node_group, "interface"):
        for item in node_group.interface.items_tree:
            if getattr(item, "item_type", None) != "SOCKET":
                continue
            if item.in_out != "INPUT" or item.name != socket_name:
                continue
            try:
                item.default_value = value
            except Exception:
                pass
            return

    if hasattr(node_group, "inputs"):
        socket = node_group.inputs.get(socket_name)
        if socket is None:
            return
        try:
            socket.default_value = value
        except Exception:
            pass


def _ensure_geo_source_group(anchor_object):
    group_name = "Geo Source From Anchors"
    group = bpy.data.node_groups.get(group_name)
    if group is None or group.bl_idname != "GeometryNodeTree":
        group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")

    group.nodes.clear()
    group.links.clear()
    _clear_group_interface(group)

    _create_group_socket(group, "Anchor Object", "INPUT", "NodeSocketObject")
    _create_group_socket(group, "As Instance", "INPUT", "NodeSocketBool")
    _create_group_socket(group, "Geometry", "OUTPUT", "NodeSocketGeometry")

    _set_group_input_default(group, "Anchor Object", anchor_object)
    _set_group_input_default(group, "As Instance", True)

    nodes = group.nodes
    links = group.links

    group_in = nodes.new("NodeGroupInput")
    group_in.location = (-760, 0)

    obj_info = nodes.new("GeometryNodeObjectInfo")
    obj_info.location = (-420, 0)

    group_out = nodes.new("NodeGroupOutput")
    group_out.location = (-80, 0)

    in_anchor = _socket_by_name(group_in.outputs, "Anchor Object")
    in_instance = _socket_by_name(group_in.outputs, "As Instance")
    info_object = _socket_by_name(obj_info.inputs, "Object")
    info_instance = _socket_by_name(obj_info.inputs, "As Instance")
    info_geo = _socket_by_name(obj_info.outputs, "Geometry")
    out_geo = _socket_by_name(group_out.inputs, "Geometry")

    if in_anchor is not None and info_object is not None:
        links.new(in_anchor, info_object)
    if in_instance is not None and info_instance is not None:
        links.new(in_instance, info_instance)
    if info_geo is not None and out_geo is not None:
        links.new(info_geo, out_geo)

    frame = nodes.new("NodeFrame")
    frame.label = "Named attributes on incoming points"
    frame.location = (-420, -380)

    attrs = [
        ("geo_kind", "STRING"),
        ("geo_name", "STRING"),
        ("geo_continent", "STRING"),
        ("geo_iso2", "STRING"),
        ("geo_iso3", "STRING"),
        ("geo_uv", "FLOAT_VECTOR"),
        ("geo_index", "INT"),
    ]
    y = -420
    for attr_name, data_type in attrs:
        node = nodes.new("GeometryNodeInputNamedAttribute")
        node.label = attr_name
        node.location = (-760, y)
        node.parent = frame
        if hasattr(node, "data_type"):
            try:
                node.data_type = data_type
            except Exception:
                pass
        name_input = _socket_by_name(node.inputs, "Name")
        if name_input is not None:
            name_input.default_value = attr_name
        y -= 160

    return group


def _ensure_geo_source_host(context):
    host = bpy.data.objects.get("GeoSourceHost")
    if host is not None:
        return host

    mesh = bpy.data.meshes.new("GeoSourceHostMesh")
    mesh.from_pydata([], [], [])
    mesh.update()
    host = bpy.data.objects.new("GeoSourceHost", mesh)
    context.scene.collection.objects.link(host)
    return host


def _find_geo_anchor_object():
    anchor = bpy.data.objects.get("GeoAnchorPoints")
    if anchor is not None:
        return anchor

    for obj in bpy.data.objects:
        if obj.name.startswith("GeoAnchorPoints"):
            return obj
    return None


def _apply_node_group_input_defaults(modifier, node_group, values):
    if not hasattr(node_group, "interface"):
        return

    for item in node_group.interface.items_tree:
        if getattr(item, "item_type", None) != "SOCKET":
            continue
        if item.in_out != "INPUT":
            continue
        value = values.get(item.name)
        if value is None:
            continue
        try:
            modifier[item.identifier] = value
        except Exception:
            pass


class GeoCountryListItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="")
    iso2: bpy.props.StringProperty(name="ISO2", default="")
    iso3: bpy.props.StringProperty(name="ISO3", default="")
    continent: bpy.props.StringProperty(name="Continent", default="")
    selected: bpy.props.BoolProperty(name="Selected", default=False)


class VIEW3D_UL_geo_country_list(bpy.types.UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name)
        row.label(text=item.continent)


class OBJECT_OT_refresh_geo_country_list(bpy.types.Operator):
    bl_idname = "object.refresh_geo_country_list"
    bl_label = "Refresh Countries"
    bl_description = "Load countries into the selectable list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.country_wireframe_settings
        try:
            world, _country_lookup, _continents_lookup = _load_geo_data()
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        _sync_country_items_from_world(settings, world)
        self.report({"INFO"}, f"Loaded {len(settings.country_items)} countries.")
        return {"FINISHED"}


class OBJECT_OT_select_all_geo_countries(bpy.types.Operator):
    bl_idname = "object.select_all_geo_countries"
    bl_label = "Select All Countries"
    bl_description = "Select all countries in the list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.country_wireframe_settings
        for item in settings.country_items:
            item.selected = True
        self.report({"INFO"}, "Selected all countries.")
        return {"FINISHED"}


class OBJECT_OT_select_none_geo_countries(bpy.types.Operator):
    bl_idname = "object.select_none_geo_countries"
    bl_label = "Select No Countries"
    bl_description = "Unselect all countries in the list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.country_wireframe_settings
        for item in settings.country_items:
            item.selected = False
        self.report({"INFO"}, "Cleared country selection.")
        return {"FINISHED"}


class CountryWireframeSettings(bpy.types.PropertyGroup):
    generation_mode: bpy.props.EnumProperty(
        name="Mode",
        description="Generate true boundary wireframes or marker spheres",
        items=(
            ("BOUNDARY", "Boundary Wireframes", "Country/continent outlines"),
            ("MARKER", "Marker Spheres", "Centroid markers as spheres"),
        ),
        default="BOUNDARY",
    )
    clear_existing: bpy.props.BoolProperty(
        name="Clear Existing",
        description="Remove previously generated geo wireframe objects first",
        default=True,
    )
    countries_enabled: bpy.props.BoolProperty(
        name="Countries",
        description="Generate country instances",
        default=True,
    )
    continents_enabled: bpy.props.BoolProperty(
        name="Continents",
        description="Generate continent instances",
        default=True,
    )
    countries: bpy.props.StringProperty(
        name="Countries",
        description=(
            "Comma-separated country names or ISO codes " "(e.g. France, JP, BRA)"
        ),
        default="France, Japan",
    )
    continents: bpy.props.StringProperty(
        name="Continents",
        description=(
            "Optional comma-separated continent names. "
            "Leave empty to include all continents."
        ),
        default="",
    )
    globe_radius: bpy.props.FloatProperty(
        name="Radius",
        description="Radius of the globe used to position country spheres",
        default=10.0,
        min=0.001,
        soft_max=1000.0,
    )
    resolution: bpy.props.IntProperty(
        name="Resolution",
        description="Segments for the generated UV spheres",
        default=24,
        min=6,
        max=256,
    )
    marker_scale: bpy.props.FloatProperty(
        name="Country Scale",
        description="Country sphere size relative to globe radius",
        default=0.03,
        min=0.0001,
        max=1.0,
        subtype="FACTOR",
    )
    continent_scale: bpy.props.FloatProperty(
        name="Continent Scale",
        description="Continent sphere size relative to globe radius",
        default=0.06,
        min=0.0001,
        max=1.0,
        subtype="FACTOR",
    )
    add_surface_mesh: bpy.props.BoolProperty(
        name="Mesh Surface + UV",
        description=(
            "If enabled, instances keep visible faces and GeoUVs for shading; "
            "otherwise they are wireframe-only"
        ),
        default=True,
    )
    create_reference_globe: bpy.props.BoolProperty(
        name="Reference Globe",
        description="Create a reference globe under the overlays",
        default=True,
    )
    overlay_offset: bpy.props.FloatProperty(
        name="Overlay Offset",
        description="Push boundaries and markers above the reference globe",
        default=0.001,
        min=0.0,
        max=0.1,
        step=0.01,
        precision=4,
    )
    country_items: bpy.props.CollectionProperty(type=GeoCountryListItem)
    country_index: bpy.props.IntProperty(default=0)


class OBJECT_OT_create_country_wireframes(bpy.types.Operator):
    bl_idname = "object.create_country_wireframes"
    bl_label = "Create Country Wireframes"
    bl_description = (
        "Create country/continent marker instances with identifying attributes"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.country_wireframe_settings

        if not settings.countries_enabled and not settings.continents_enabled:
            self.report(
                {"ERROR"},
                "Enable Countries and/or Continents before creating markers.",
            )
            return {"CANCELLED"}

        country_tokens = [item.name for item in settings.country_items if item.selected]
        continent_tokens = _tokenize_values(settings.continents)

        if settings.countries_enabled and not country_tokens:
            self.report(
                {"ERROR"},
                "Select one or more countries in the list.",
            )
            return {"CANCELLED"}

        try:
            _world, country_lookup, continents_lookup = _load_geo_data()
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        country_radius = max(settings.globe_radius * settings.marker_scale, 0.0001)
        continent_radius = max(
            settings.globe_radius * settings.continent_scale,
            0.0001,
        )

        root = _get_or_create_collection(
            context.scene.collection,
            "Geo Wireframes",
        )
        prototypes = _get_or_create_collection(root, "Geo Prototypes")
        countries_coll = _get_or_create_collection(root, "Geo Countries")
        continents_coll = _get_or_create_collection(root, "Geo Continents")
        anchors_coll = _get_or_create_collection(root, "Geo Anchors")
        reference_coll = _get_or_create_collection(root, "Geo Reference")

        if settings.clear_existing:
            collections = (
                prototypes,
                countries_coll,
                continents_coll,
                anchors_coll,
                reference_coll,
            )
            for coll in collections:
                for obj in list(coll.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)

        if settings.create_reference_globe:
            _create_reference_globe(
                collection=reference_coll,
                radius=settings.globe_radius,
                resolution=settings.resolution,
            )

        overlay_radius = settings.globe_radius * (1.0 + settings.overlay_offset)

        country_proto = None
        continent_proto = None
        if settings.generation_mode == "MARKER":
            country_proto = _build_sphere_mesh(
                "GeoCountryPrototypeMesh",
                country_radius,
                settings.resolution,
                settings.add_surface_mesh,
            )
            country_proto_obj = bpy.data.objects.new(
                "GeoCountryPrototype",
                country_proto,
            )
            country_proto_obj.hide_viewport = True
            country_proto_obj.hide_render = True
            prototypes.objects.link(country_proto_obj)

            continent_proto = _build_sphere_mesh(
                "GeoContinentPrototypeMesh",
                continent_radius,
                settings.resolution,
                settings.add_surface_mesh,
            )
            continent_proto_obj = bpy.data.objects.new(
                "GeoContinentPrototype",
                continent_proto,
            )
            continent_proto_obj.hide_viewport = True
            continent_proto_obj.hide_render = True
            prototypes.objects.link(continent_proto_obj)

        created = 0
        missing = []
        anchor_points = []
        anchor_items = []

        if settings.countries_enabled:
            for token in country_tokens:
                row = country_lookup.get(token.lower())
                if row is None:
                    missing.append(token)
                    continue

                point = row.geometry.representative_point()
                lat = point.y
                lon = point.x
                location = _latlon_to_xyz(lat, lon, overlay_radius)
                name = str(row["name"])
                continent_name = str(row["continent"])
                iso2 = str(row["iso_a2"])
                iso3 = str(row["iso_a3"])

                if settings.generation_mode == "BOUNDARY":
                    created_obj = _create_boundary_wire_object(
                        collection=countries_coll,
                        obj_name=f"CountryWF_{name}",
                        geometry=row.geometry,
                        globe_radius=overlay_radius,
                        kind="country",
                        geo_name=name,
                        continent_name=continent_name,
                        iso2=iso2,
                        iso3=iso3,
                    )
                    if created_obj is None:
                        missing.append(token)
                        continue
                else:
                    _make_linked_instance(
                        name=f"CountryWF_{name}",
                        source_mesh=country_proto,
                        location=location,
                        collection=countries_coll,
                        kind="country",
                        geo_name=name,
                        continent_name=continent_name,
                        iso2=iso2,
                        iso3=iso3,
                    )

                anchor_points.append(location)
                anchor_items.append(
                    {
                        "kind": "country",
                        "name": name,
                        "continent": continent_name,
                        "iso2": iso2,
                        "iso3": iso3,
                        "uv": _to_uv(lat, lon),
                    }
                )
                created += 1

        if settings.continents_enabled:
            selected_continents = set(
                name.lower() for name in continent_tokens if name.strip()
            )
            continent_items = list(continents_lookup.values())
            for item in continent_items:
                continent_name = item["name"]
                if (
                    selected_continents
                    and continent_name.lower() not in selected_continents
                ):
                    continue

                point = item["point"]
                lat = point.y
                lon = point.x
                location = _latlon_to_xyz(lat, lon, overlay_radius)

                if settings.generation_mode == "BOUNDARY":
                    created_obj = _create_boundary_wire_object(
                        collection=continents_coll,
                        obj_name=f"ContinentWF_{continent_name}",
                        geometry=item.get("geometry"),
                        globe_radius=overlay_radius,
                        kind="continent",
                        geo_name=continent_name,
                        continent_name=continent_name,
                        iso2="",
                        iso3="",
                    )
                    if created_obj is None:
                        continue
                else:
                    _make_linked_instance(
                        name=f"ContinentWF_{continent_name}",
                        source_mesh=continent_proto,
                        location=location,
                        collection=continents_coll,
                        kind="continent",
                        geo_name=continent_name,
                        continent_name=continent_name,
                        iso2="",
                        iso3="",
                    )

                anchor_points.append(location)
                anchor_items.append(
                    {
                        "kind": "continent",
                        "name": continent_name,
                        "continent": continent_name,
                        "iso2": "",
                        "iso3": "",
                        "uv": _to_uv(lat, lon),
                    }
                )
                created += 1

        if anchor_points:
            _create_anchor_object(
                context,
                "GeoAnchorPoints",
                anchor_points,
                anchor_items,
                anchors_coll,
            )

        if created == 0:
            self.report({"ERROR"}, "No valid countries or continents found.")
            return {"CANCELLED"}

        if missing:
            unknown = ", ".join(missing)
            self.report(
                {"WARNING"},
                f"Created {created} markers. " f"Unrecognized countries: {unknown}",
            )
        else:
            self.report(
                {"INFO"},
                f"Created {created} geo marker instance(s).",
            )

        return {"FINISHED"}


class OBJECT_OT_build_geo_nodes_source(bpy.types.Operator):
    bl_idname = "object.build_geo_nodes_source"
    bl_label = "Build GeoNodes Source"
    bl_description = "Create a Geometry Nodes source group wired to GeoAnchorPoints"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        anchor = _find_geo_anchor_object()
        if anchor is None:
            self.report(
                {"ERROR"},
                "No GeoAnchorPoints object found. Create geo markers first.",
            )
            return {"CANCELLED"}

        node_group = _ensure_geo_source_group(anchor)
        host = context.active_object
        if host is None:
            host = _ensure_geo_source_host(context)

        modifier = host.modifiers.get("Geo Source")
        if modifier is None or modifier.type != "NODES":
            modifier = host.modifiers.new(name="Geo Source", type="NODES")
        modifier.node_group = node_group

        _apply_node_group_input_defaults(
            modifier,
            node_group,
            {
                "Anchor Object": anchor,
                "As Instance": True,
            },
        )

        self.report(
            {"INFO"},
            f"Geo Source group attached to '{host.name}'.",
        )
        return {"FINISHED"}


class VIEW3D_PT_country_wireframes(bpy.types.Panel):
    bl_label = "Country Wireframes"
    bl_idname = "VIEW3D_PT_country_wireframes"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Create"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.country_wireframe_settings

        layout.label(text="Build Sets")
        row = layout.row(align=True)
        row.prop(settings, "countries_enabled", toggle=True)
        row.prop(settings, "continents_enabled", toggle=True)

        layout.separator()
        layout.prop(settings, "generation_mode")

        row = layout.row()
        row.template_list(
            "VIEW3D_UL_geo_country_list",
            "",
            settings,
            "country_items",
            settings,
            "country_index",
            rows=10,
        )
        col = row.column(align=True)
        col.operator("object.refresh_geo_country_list", text="", icon="FILE_REFRESH")
        col.operator("object.select_all_geo_countries", text="", icon="CHECKBOX_HLT")
        col.operator(
            "object.select_none_geo_countries",
            text="",
            icon="CHECKBOX_DEHLT",
        )

        layout.prop(settings, "continents")
        layout.prop(settings, "clear_existing")
        layout.prop(settings, "globe_radius")
        layout.prop(settings, "create_reference_globe")
        layout.prop(settings, "overlay_offset")
        layout.prop(settings, "resolution")
        layout.prop(settings, "marker_scale")
        layout.prop(settings, "continent_scale")
        layout.prop(settings, "add_surface_mesh")
        layout.separator()
        layout.operator(
            "object.create_country_wireframes",
            icon="MESH_UVSPHERE",
        )
        layout.operator(
            "object.build_geo_nodes_source",
            icon="NODETREE",
        )


CLASSES = (
    GeoCountryListItem,
    VIEW3D_UL_geo_country_list,
    OBJECT_OT_refresh_geo_country_list,
    OBJECT_OT_select_all_geo_countries,
    OBJECT_OT_select_none_geo_countries,
    CountryWireframeSettings,
    OBJECT_OT_create_country_wireframes,
    OBJECT_OT_build_geo_nodes_source,
    VIEW3D_PT_country_wireframes,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.country_wireframe_settings = bpy.props.PointerProperty(
        type=CountryWireframeSettings
    )


def unregister():
    if hasattr(bpy.types.Scene, "country_wireframe_settings"):
        del bpy.types.Scene.country_wireframe_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
