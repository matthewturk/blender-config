bl_info = {
    "name": "Adaptive Viewport Clipping",
    "author": "Matthew Turk",
    "version": (1, 0),
    "blender": (4, 2, 0),
    "category": "3D View",
}

# Live counterpart to the old one-shot viewport_switch.py script: instead of
# running a script by hand every time the selection changes, this watches the
# selection continuously and rescales the 3D Viewport's near/far clip
# distances to match whatever's selected - close-up work on a tiny object
# gets a tight near clip so you can zoom into it without it disappearing,
# and a big/far-flung selection gets a far clip generous enough to keep
# background context in view.
#
# Toggle: OBJECT_OT / the "Auto-Adjust Clipping" checkbox in the 3D Viewport
# sidebar (N-panel > Viewport Clip) turns the behavior on and off. All the
# heuristic constants the original script hardcoded (near/far clip factors
# and minimums, plus a depth-precision ratio cap mentioned in the original
# comment but never actually enforced) are exposed as settings in that same
# panel instead of requiring an edit to this file.
#
# No native "selection changed" event: Blender doesn't fire depsgraph or
# msgbus notifications for select/deselect - selection is view-layer UI
# state, not evaluated data. The standard workaround (used by most addons
# that need this) is a repeating bpy.app.timers callback that polls
# context.selected_objects and diffs it against the last-seen selection;
# that's what drives this here. The poll interval is itself a setting so you
# can trade responsiveness for a bit less idle overhead.
#
# Scene-scoped settings: the toggle and every parameter live in a
# PropertyGroup on the Scene (scene.viewport_clip_settings), matching how
# dynamic_script_runner.py and friends store their own settings - saved with
# the .blend, and (as a consequence) "enabled" is per-scene. Switching to a
# scene where it's off stops the polling timer; switching back doesn't
# restart it on its own, only toggling the checkbox or reloading the file
# does. Fine for the common case of one working scene per file; if you
# routinely flip between scenes wanting this live in more than one at once,
# that's the corner this design doesn't cover.

import bpy
import mathutils
from bpy.app.handlers import persistent


# ---------------------------------------------------------------------------
#  Core heuristic - geometry measurement is unchanged from the original
#  script; only the constants that turn a size into clip distances now come
#  from settings instead of being hardcoded.
# ---------------------------------------------------------------------------

def calculate_selection_bounds(selected_objects):
    """
    Calculates the minimum and maximum world-space coordinates
    of all selected objects to determine the bounding box size.
    """
    min_coord = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    max_coord = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))

    found_valid = False

    for obj in selected_objects:
        # Evaluate world transform for bound corners
        matrix = obj.matrix_world
        if obj.type == 'MESH' and obj.data:
            found_valid = True
            for corner in obj.bound_box:
                world_corner = matrix @ mathutils.Vector(corner)
                min_coord.x = min(min_coord.x, world_corner.x)
                min_coord.y = min(min_coord.y, world_corner.y)
                min_coord.z = min(min_coord.z, world_corner.z)
                max_coord.x = max(max_coord.x, world_corner.x)
                max_coord.y = max(max_coord.y, world_corner.y)
                max_coord.z = max(max_coord.z, world_corner.z)
        else:
            # Fallback for non-mesh objects using origin location
            found_valid = True
            loc = matrix.translation
            min_coord.x = min(min_coord.x, loc.x)
            min_coord.y = min(min_coord.y, loc.y)
            min_coord.z = min(min_coord.z, loc.z)
            max_coord.x = max(max_coord.x, loc.x)
            max_coord.y = max(max_coord.y, loc.y)
            max_coord.z = max(max_coord.z, loc.z)

    if not found_valid:
        return None

    diagonal = (max_coord - min_coord).length
    return max(diagonal, 0.001)  # Prevent zero-length bounds


def _adjust_viewport_clipping(settings, verbose=None):
    """Recompute clip_start/clip_end from the current selection and apply
    them to the relevant 3D Viewport space(s), per `settings`."""
    if verbose is None:
        verbose = settings.verbose

    selected = bpy.context.selected_objects
    size = None

    if not selected:
        if not settings.reset_on_empty:
            if verbose:
                print("[Viewport Clip] No objects selected - clipping unchanged.")
            return
        new_start = max(settings.reset_start, 0.0000001)
        new_end = max(settings.reset_end, new_start * 2)
    else:
        size = calculate_selection_bounds(selected)
        if size is None:
            if verbose:
                print("[Viewport Clip] Nothing measurable in selection - clipping unchanged.")
            return

        # Adaptive clipping limits - ratio of end/start kept reasonably tight
        # below to prevent depth-buffer precision artifacts (z-fighting).
        new_start = max(size * settings.start_factor, settings.start_min)
        new_end = max(size * settings.end_factor, settings.end_min)

        if settings.enforce_max_ratio:
            new_end = min(new_end, new_start * settings.max_ratio)

    screens = bpy.data.screens if settings.all_screens else [bpy.context.screen]

    updated = 0
    for screen in screens:
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.clip_start = new_start
                        space.clip_end = new_end
                        updated += 1

    if verbose:
        scale_txt = f"~{size:.3f}m" if size is not None else "n/a (reset)"
        print(
            f"[Viewport Clip] Updated {updated} viewport(s) -> "
            f"Clip Start: {new_start:.6f}m, Clip End: {new_end:.2f}m "
            f"(Object scale: {scale_txt})"
        )


# ---------------------------------------------------------------------------
#  Settings
# ---------------------------------------------------------------------------

def _on_enabled_update(self, context):
    if self.enabled:
        _start_polling()
    else:
        _stop_polling()


class ViewportClipSettings(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(
        name="Auto-Adjust Clipping",
        description=(
            "Continuously watch the selection and rescale the 3D Viewport's "
            "near/far clip distances to match its size"
        ),
        default=False,
        update=_on_enabled_update,
    )
    poll_interval: bpy.props.FloatProperty(
        name="Poll Interval",
        description=(
            "How often (seconds) to check whether the selection changed. "
            "Lower is more responsive but costs a bit more overhead while idle"
        ),
        default=0.2, min=0.05, max=2.0,
    )

    start_factor: bpy.props.FloatProperty(
        name="Near Clip Factor",
        description="Near clip distance = selection bounding-diagonal x this factor",
        default=0.0005, min=0.0, precision=5,
    )
    start_min: bpy.props.FloatProperty(
        name="Near Clip Minimum",
        description=(
            "Absolute floor for the near clip distance, regardless of "
            "selection size (prevents zero/negative clip start)"
        ),
        default=0.0001, min=0.0000001, precision=6,
    )
    end_factor: bpy.props.FloatProperty(
        name="Far Clip Factor",
        description="Far clip distance = selection bounding-diagonal x this factor",
        default=50.0, min=0.0,
    )
    end_min: bpy.props.FloatProperty(
        name="Far Clip Minimum",
        description=(
            "Absolute floor for the far clip distance, so small objects "
            "still keep some background in view"
        ),
        default=1000.0, min=0.0,
    )

    enforce_max_ratio: bpy.props.BoolProperty(
        name="Cap Clip Ratio",
        description=(
            "Keep clip_end / clip_start below Max Clip Ratio to avoid the "
            "depth-buffer precision artifacts (z-fighting) that show up "
            "when the two are too far apart. The original script's comment "
            "described this but never actually applied it - this does"
        ),
        default=True,
    )
    max_ratio: bpy.props.FloatProperty(
        name="Max Clip Ratio",
        description="Largest allowed clip_end / clip_start ratio when Cap Clip Ratio is on",
        default=1_000_000.0, min=2.0,
    )

    all_screens: bpy.props.BoolProperty(
        name="All Screens",
        description=(
            "Update every 3D Viewport across every screen/workspace, not "
            "just the current one"
        ),
        default=False,
    )

    reset_on_empty: bpy.props.BoolProperty(
        name="Reset When Nothing Selected",
        description=(
            "When the selection is emptied, reset clipping to fixed values "
            "below instead of leaving the last computed clipping in place"
        ),
        default=False,
    )
    reset_start: bpy.props.FloatProperty(
        name="Empty-Selection Near Clip",
        default=0.1, min=0.0000001,
    )
    reset_end: bpy.props.FloatProperty(
        name="Empty-Selection Far Clip",
        default=1000.0, min=0.0,
    )

    verbose: bpy.props.BoolProperty(
        name="Log To Console",
        description="Print a line to the console every time clipping is updated",
        default=False,
    )


# ---------------------------------------------------------------------------
#  Selection-change polling - see module docstring for why a timer instead
#  of a handler.
# ---------------------------------------------------------------------------

_last_selection_key = None


def _selection_key():
    try:
        return frozenset(o.name for o in bpy.context.selected_objects)
    except Exception:
        return None


def _poll_selection():
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "viewport_clip_settings", None) if scene else None
    if settings is None or not settings.enabled:
        return None  # stop the timer - re-enabling the toggle restarts it

    global _last_selection_key
    try:
        key = _selection_key()
        if key is not None and key != _last_selection_key:
            _last_selection_key = key
            _adjust_viewport_clipping(settings)
    except Exception as e:
        print(f"[Viewport Clip] Poll error (continuing): {e}")

    return settings.poll_interval


def _start_polling():
    global _last_selection_key
    _last_selection_key = None
    if not bpy.app.timers.is_registered(_poll_selection):
        bpy.app.timers.register(_poll_selection, first_interval=0.1)


def _stop_polling():
    if bpy.app.timers.is_registered(_poll_selection):
        bpy.app.timers.unregister(_poll_selection)


@persistent
def _restore_polling_state(dummy=None):
    """_last_selection_key/the running timer are plain process memory, gone
    after loading a .blend - restart polling here if the loaded scene has
    the toggle on, mirroring chezmoi_sync.py's own load_post pattern."""
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "viewport_clip_settings", None) if scene else None
    if settings and settings.enabled:
        _start_polling()
    return None


# ---------------------------------------------------------------------------
#  Operator - manual "run once" trigger, independent of the toggle
# ---------------------------------------------------------------------------

class VIEW3D_OT_adjust_viewport_clipping(bpy.types.Operator):
    """Recalculate viewport clipping from the current selection right now"""
    bl_idname = "view3d.adjust_viewport_clipping"
    bl_label = "Adjust Viewport Clipping Now"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.viewport_clip_settings
        _adjust_viewport_clipping(settings, verbose=True)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
#  Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_viewport_clip(bpy.types.Panel):
    bl_label = "Adaptive Viewport Clipping"
    bl_idname = "VIEW3D_PT_viewport_clip"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Viewport Clip'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.viewport_clip_settings

        row = layout.row(align=True)
        row.prop(
            settings, "enabled", toggle=True,
            icon='HIDE_OFF' if settings.enabled else 'HIDE_ON',
        )
        row.operator(VIEW3D_OT_adjust_viewport_clipping.bl_idname, text="", icon='FILE_REFRESH')

        layout.prop(settings, "poll_interval")

        box = layout.box()
        box.label(text="Near Clip Heuristic")
        box.prop(settings, "start_factor")
        box.prop(settings, "start_min")

        box = layout.box()
        box.label(text="Far Clip Heuristic")
        box.prop(settings, "end_factor")
        box.prop(settings, "end_min")

        box = layout.box()
        box.prop(settings, "enforce_max_ratio")
        sub = box.column()
        sub.enabled = settings.enforce_max_ratio
        sub.prop(settings, "max_ratio")

        box = layout.box()
        box.prop(settings, "reset_on_empty")
        sub = box.column(align=True)
        sub.enabled = settings.reset_on_empty
        sub.prop(settings, "reset_start")
        sub.prop(settings, "reset_end")

        layout.prop(settings, "all_screens")
        layout.prop(settings, "verbose")


# ---------------------------------------------------------------------------
#  Register / unregister
# ---------------------------------------------------------------------------

_CLASSES = (
    ViewportClipSettings,
    VIEW3D_OT_adjust_viewport_clipping,
    VIEW3D_PT_viewport_clip,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viewport_clip_settings = bpy.props.PointerProperty(type=ViewportClipSettings)

    bpy.app.handlers.load_post.append(_restore_polling_state)
    # load_post covers the normal "open a .blend" case; this timer covers
    # register() running with a file already open (e.g. after Reload
    # Scripts) - same reasoning as constant_mass_emission_generator.py's
    # identical first_interval=1.0 timer.
    bpy.app.timers.register(_restore_polling_state, first_interval=1.0)


def unregister():
    _stop_polling()
    if _restore_polling_state in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restore_polling_state)

    del bpy.types.Scene.viewport_clip_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
