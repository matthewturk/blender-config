"""Thin re-export so Blender's startup-scan still finds a config-sync
entry point inside scripts/startup/ - where chezmoi's real-machine symlink
targets (see ../../config/run_onchange_after_configure-blender-paths.sh
.tmpl - a reference copy only, chezmoi actually runs its own copy from its
source directory, not this repo), and where __init__.py expects every
registered feature to live - while
the actual implementation and its config files now live in a separate
top-level config/ directory (see ../../config/README.md).

Config-sync is a config-management concern, not a Blender feature/plugin,
and doesn't belong mixed in among the real feature scripts (GIS importers,
node builders, the CLI-facing operators, etc.) that make up the rest of
this package - loading "the plugins" shouldn't also always mean loading
the whole preference-sync machinery (GPU device, theme, asset libraries,
extensions) as an inseparable side effect. This shim is the smallest
possible bridge back to the one place Blender's own startup-scan (and
this package's __init__.py) still looks.

Uses the same file-path-based loading this repo already uses elsewhere
for a sibling module with no package context (see e.g.
user_scripts/collection_to_lists.py's _load_sibling) - a plain `import
chezmoi_sync` after a sys.path append would also work, but risks
colliding with an unrelated same-named module anywhere else on sys.path.

MUST use os.path.realpath(__file__), not plain __file__, before climbing
"..": scripts/startup/ itself is what chezmoi's real-machine hook
symlinks into Blender's own startup directory as a folder literally named
"chezmoi" (see the .tmpl reference above) - so when Blender loads this
shim through that symlink, __file__ reflects the traversed symlink path
(".../<blender>/scripts/startup/chezmoi/_chezmoi_sync_shim.py"), NOT this
repo's real location. Climbing ".." twice from the unresolved path lands
outside the real repo entirely (in Blender's own scripts/ directory,
which has no config/ of its own) - confirmed via FileNotFoundError in
real-machine testing, and reproduced+fixed 2026-09-18. realpath()
resolves the symlink first, giving the one true filesystem location this
computation actually needs.
"""

import importlib.util
import os


def _load_real_module():
    config_dir = os.path.abspath(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "config")
    )
    path = os.path.join(config_dir, "chezmoi_sync.py")
    spec = importlib.util.spec_from_file_location("_real_chezmoi_sync", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_impl = _load_real_module()
register = _impl.register
unregister = _impl.unregister
