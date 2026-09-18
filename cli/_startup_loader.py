"""Load this repo's scripts/startup/ package outside of a normal Blender
GUI launch, for command-line tools under cli/ that want to call the exact
same operators the interactive panels do (bpy.ops.object.import_geojson_
wireframes, etc.) without opening Blender.

Why this is needed rather than a plain `sys.path.insert` + `import
country_wireframes`: country_wireframes.py (and its siblings) use PACKAGE-
relative imports (`from . import geo_coord`), so they need to be loaded
as part of SOME real Python package, not as bare standalone modules. A
bare `import country_wireframes` (no package context) would hit
`ImportError: attempted relative import with no known parent package` the
moment it tries `from . import geo_coord`.

So this loads scripts/startup/__init__.py as a real package (with
scripts/startup/ set as its submodule search path), then calls its
register() - the same shape of thing Blender's own add-on loader does,
just under a package name of our own choosing (PACKAGE_NAME below), NOT
"chezmoi" - that name is specific to the symlink chezmoi's real-machine
hook creates (see ../config/run_onchange_after_configure-blender-paths.sh
.tmpl - a reference copy only, chezmoi actually runs its own copy from
its source directory, not this repo - see config/README.md), which is an
entirely separate, unrelated registration path from this loader. The two
never need to agree on a name: whichever one runs first
in a given process registers the real bpy classes (in bpy.types, keyed by
class name, not by which Python module/package imported them), and the
probe below detects that state directly rather than caring what either
path called itself.

If a real Blender session (or the `bpy` module, if it resolves the same
user script path chezmoi's symlink points at) already auto-loaded these
scripts, registration is skipped (detected via an already-registered
operator class) to avoid a "class already registered" error - so this is
safe to call unconditionally at the top of any cli/ tool.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_DIR = REPO_ROOT / "scripts" / "startup"
PACKAGE_NAME = "blender_config_startup"  # our own name for this loader's
                                          # sys.modules bookkeeping only -
                                          # deliberately independent of
                                          # chezmoi's real symlink name,
                                          # see module docstring above

# A representative operator CLASS this package's register() creates -
# used only to detect "is this already loaded", not called for any other
# purpose. Must be checked via bpy.types (the actual registration target
# bpy.utils.register_class populates), NOT via bpy.ops: `bpy.ops.<category>`
# attribute access is dynamic and returns a truthy-looking callable for ANY
# name, real or not - confirmed directly (`hasattr(bpy.ops.object, "anything_
# at_all")` is True) - so it can never signal "not registered" and a
# hasattr-on-bpy.ops check here would silently never re-detect a missing
# registration, meaning load_and_register() would think it's always already
# loaded and never actually load anything.
_PROBE_OPERATOR_CLASS = "OBJECT_OT_import_geojson_wireframes"


def load_and_register():
    """Import scripts/startup/ as a real package (named PACKAGE_NAME, see
    above) and register it, unless it's already registered. Returns the
    loaded package module (or None if it was already loaded some other
    way and we never imported it ourselves - callers generally don't need
    the module itself, just the side effect of bpy.ops/bpy.types being
    populated).
    """
    import bpy

    if hasattr(bpy.types, _PROBE_OPERATOR_CLASS):
        return sys.modules.get(PACKAGE_NAME)

    if PACKAGE_NAME in sys.modules:
        module = sys.modules[PACKAGE_NAME]
    else:
        spec = importlib.util.spec_from_file_location(
            PACKAGE_NAME,
            STARTUP_DIR / "__init__.py",
            submodule_search_locations=[str(STARTUP_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        # Registered in sys.modules BEFORE exec_module, so that when its
        # submodules run `from . import geo_coord` etc., Python can resolve
        # the parent package (PACKAGE_NAME) as already-in-progress rather
        # than trying (and failing) to import it fresh.
        sys.modules[PACKAGE_NAME] = module
        spec.loader.exec_module(module)

    module.register()
    return module
