import bpy
import addon_utils
import json
import os
import shutil
import subprocess
import threading
import sys
from bpy.app.handlers import persistent

# Global tracking state for the background thread
UV_STATUS = "CHECKING"


def draw_popup(self, context):
    global UV_STATUS
    layout = self.layout
    if UV_STATUS == "NEEDS_SYNC":
        layout.label(
            text="Blender environment is out of sync with uv.lock!", icon="ERROR"
        )
        layout.label(
            text="Running 'uv sync' automatically in the background...", icon="INFO"
        )
    elif UV_STATUS == "SYNC_COMPLETE":
        layout.label(text="Environment Sync Completed Successfully!", icon="CHECKMARK")
    elif UV_STATUS == "ERROR":
        layout.label(
            text="Background uv sync failed. Check system console.", icon="CANCEL"
        )


def safe_ui_refresh():
    """This callback runs safely on Blender's main thread to refresh the UI."""
    # Tag all visible areas to redraw themselves cleanly
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None  # Returning None tells Blender to run the timer exactly once and stop


def run_background_sync(uv_bin, project_dir):
    global UV_STATUS
    try:
        # Executes 'uv sync' natively using the workspace files in project_dir
        subprocess.run([uv_bin, "sync"], cwd=project_dir, check=True)
        UV_STATUS = "SYNC_COMPLETE"
        print("[Chezmoi/uv] Background sync completed successfully.")

        # Safe alternative: Register a deferred 1-shot timer on the main thread
        bpy.app.timers.register(safe_ui_refresh)

    except Exception as e:
        UV_STATUS = "ERROR"
        print(f"[Chezmoi/uv Error] Background uv sync failed: {e}")
        # Make sure the error state redraws too
        bpy.app.timers.register(safe_ui_refresh)


def _module_matches_package(module_name, pkg_id):
    """Accept classic add-ons (node_wrangler) and extension modules (bl_ext.<repo>.<pkg>)."""
    return module_name == pkg_id or module_name.endswith(f".{pkg_id}")


def _apply_property_map(target, values, label):
    """Apply a dict of properties onto a Blender RNA object defensively."""
    if not isinstance(values, dict):
        print(f"[Chezmoi/Preferences Warning] {label} must be an object/dict.")
        return 0

    applied = 0
    for key, value in values.items():
        if not hasattr(target, key):
            print(f"[Chezmoi/Preferences Warning] Unknown property '{key}' in {label}.")
            continue
        try:
            setattr(target, key, value)
            applied += 1
        except Exception as e:
            print(f"[Chezmoi/Preferences Warning] Failed to set {label}.{key}: {e}")
    return applied


def _apply_theme_preset(theme_name):
    """Apply a bundled or user interface theme preset by its display name."""
    if not theme_name:
        return
    target_filename = theme_name.strip().lower().replace(" ", "_") + ".py"
    for preset_dir in bpy.utils.preset_paths("interface_theme"):
        candidate = os.path.join(preset_dir, target_filename)
        if os.path.exists(candidate):
            try:
                bpy.ops.script.execute_preset(
                    filepath=candidate,
                    menu_idname="USERPREF_MT_interface_theme_presets",
                )
                print(f"[Chezmoi/Preferences] Applied theme preset: {theme_name}")
            except Exception as e:
                print(f"[Chezmoi/Preferences Error] Failed to apply theme '{theme_name}': {e}")
            return
    print(f"[Chezmoi/Preferences Warning] Theme preset not found: {theme_name}")


def _resolve_addon_module(addons_by_name, addon_key):
    """Resolve configured add-on key to an enabled add-on module name."""
    if addon_key in addons_by_name:
        return addon_key
    return next(
        (name for name in addons_by_name if _module_matches_package(name, addon_key)),
        None,
    )


@persistent
def load_and_sync_chezmoi(dummy=None):
    global UV_STATUS
    config = {}
    prefs = bpy.context.preferences

    # Define paths relative to your local blender config directory
    project_dir = os.path.expanduser("~/.config/blender/blender-config")
    config_path = os.path.expanduser("~/.config/blender/config.json")

    # -------------------------------------------------------------------------
    # PART 1: Apply Plain-Text Preferences (UI Scale, Render Devices)
    # -------------------------------------------------------------------------
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)

            # 1. Set Interface Scale
            if "interface_scale" in config:
                prefs.view.ui_scale = config["interface_scale"]

            # 2. Configure Compute/Render Devices (Cycles)
            if "render_device_type" in config and "cycles" in prefs.addons:
                cprefs = prefs.addons["cycles"].preferences
                device_type = config["render_device_type"]

                if device_type != "NONE":
                    cprefs.compute_device_type = device_type
                    cprefs.get_devices()
                    for device in cprefs.devices:
                        device.use = True
                else:
                    cprefs.compute_device_type = "NONE"

            # 3. Apply Interface Theme Preset
            if "theme" in config:
                _apply_theme_preset(config["theme"])

            print("[Chezmoi/Preferences] Applied hardware configurations successfully.")
        except Exception as e:
            print(f"[Chezmoi/Preferences Error] Failed to parse config.json: {e}")
    else:
        print(f"[Chezmoi/Preferences] No config.json found at {config_path}")

    # -------------------------------------------------------------------------
    # PART 2: Resolve Path & Verify Python Environment Sync via uv
    # -------------------------------------------------------------------------
    # Dynamically find uv executable in system PATH
    uv_bin = shutil.which("uv")

    # GUI Application Fallback (if Steam clears your shell variables)
    if not uv_bin:
        fallback = os.path.expanduser("~/.local/bin/uv")
        if os.path.exists(fallback):
            uv_bin = fallback

    if not uv_bin:
        print(
            "[Chezmoi/uv Error] Could not find 'uv' in system PATH or common local fallback."
        )
        return

    # Dynamically attach venv path matching active Python major.minor version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    uv_venv = os.path.join(
        project_dir, ".venv", "lib", f"python{py_version}", "site-packages"
    )
    if os.path.exists(uv_venv) and uv_venv not in sys.path:
        sys.path.append(uv_venv)
        print(
            f"[Chezmoi/uv] Dynamically attached venv environment for Python {py_version}"
        )
        print(
            f"[Chezmoi/uv] That path is {uv_venv}"
        )

    try:
        check = subprocess.run(
            [uv_bin, "sync", "--check"], cwd=project_dir, capture_output=True
        )

        if check.returncode != 0:
            UV_STATUS = "NEEDS_SYNC"

            # Display a quick non-blocking native alert popup box
            bpy.context.window_manager.popup_menu(
                draw_popup, title="Environment Sync", icon="URL"
            )

            # Spin up background process so the viewport doesn't freeze
            threading.Thread(
                target=run_background_sync, args=(uv_bin, project_dir), daemon=True
            ).start()
        else:
            UV_STATUS = "OK"
            print("[Chezmoi/uv] Local packages match lockfile definitions perfectly.")

    except Exception as e:
        print(
            f"[Chezmoi/uv Error] Failed during dependency environment verification: {e}"
        )

    # 3.1 Configure Input, Navigation, and External Tools preferences
    if "input" in config:
        applied = _apply_property_map(prefs.inputs, config["input"], "input")
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} input preference(s).")

    if "filepaths" in config:
        applied = _apply_property_map(prefs.filepaths, config["filepaths"], "filepaths")
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} filepath preference(s).")

    if "view" in config:
        applied = _apply_property_map(prefs.view, config["view"], "view")
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} view preference(s).")

    if "edit" in config:
        applied = _apply_property_map(prefs.edit, config["edit"], "edit")
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} edit preference(s).")

    if "system" in config:
        applied = _apply_property_map(prefs.system, config["system"], "system")
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} system preference(s).")

    if "experimental" in config:
        applied = _apply_property_map(
            prefs.experimental, config["experimental"], "experimental"
        )
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} experimental preference(s).")

    if "external_tools" in config and isinstance(config["external_tools"], dict):
        external_tools = config["external_tools"]
        mapped = {
            "text_editor": "text_editor",
            "image_editor": "image_editor",
            "animation_player": "animation_player",
        }
        applied = 0
        for config_key, blender_key in mapped.items():
            if config_key not in external_tools:
                continue
            tool_path = os.path.expanduser(str(external_tools[config_key]))
            if hasattr(prefs.filepaths, blender_key):
                setattr(prefs.filepaths, blender_key, tool_path)
                applied += 1
            else:
                print(
                    f"[Chezmoi/Preferences Warning] External tool setting unsupported: {blender_key}"
                )
        if applied:
            print(f"[Chezmoi/Preferences] Applied {applied} external tool path(s).")

    # 3.2 Configure enabled add-on preferences
    if "addon_preferences" in config:
        addon_prefs_cfg = config["addon_preferences"]
        if isinstance(addon_prefs_cfg, dict):
            addons_by_name = prefs.addons
            total_applied = 0
            for addon_key, values in addon_prefs_cfg.items():
                module_name = _resolve_addon_module(addons_by_name, addon_key)
                if not module_name:
                    print(
                        f"[Chezmoi/Preferences Warning] Add-on '{addon_key}' is not enabled; cannot apply preferences."
                    )
                    continue

                addon_entry = addons_by_name.get(module_name)
                addon_prefs = getattr(addon_entry, "preferences", None)
                if addon_prefs is None:
                    print(
                        f"[Chezmoi/Preferences Warning] Add-on '{module_name}' has no configurable preferences."
                    )
                    continue

                applied = _apply_property_map(
                    addon_prefs,
                    values,
                    f"addon_preferences.{module_name}",
                )
                total_applied += applied

            if total_applied:
                print(
                    f"[Chezmoi/Preferences] Applied {total_applied} add-on preference value(s)."
                )
        else:
            print(
                "[Chezmoi/Preferences Warning] 'addon_preferences' must be an object/dict."
            )

    # 3.3 Configure Asset Libraries (Idempotent Guard with Path Updates)
    if "asset_libraries" in config:
        filepath_prefs = prefs.filepaths

        for lib_cfg in config["asset_libraries"]:
            target_name = lib_cfg["name"]
            target_path = os.path.expanduser(lib_cfg["path"])
            target_method = lib_cfg.get("import_method", "LINK").upper()

            if not os.path.exists(target_path):
                print(
                    f"[Chezmoi/Preferences Warning] Skipping asset library '{target_name}'; path does not exist: {target_path}"
                )
                continue

            # Search for an existing library matching this exact name
            existing_lib = next(
                (
                    lib
                    for lib in filepath_prefs.asset_libraries
                    if lib.name == target_name
                ),
                None,
            )

            if existing_lib:
                # Name match found! Check if the path or method needs to be synchronized
                updated = False

                # Normalize paths to avoid false mismatches from trailing slashes
                if os.path.normpath(existing_lib.path) != os.path.normpath(target_path):
                    existing_lib.path = target_path
                    updated = True
                    print(
                        f"[Chezmoi/Preferences] Remapped path for asset library '{target_name}' -> {target_path}"
                    )

                if existing_lib.import_method != target_method:
                    existing_lib.import_method = target_method
                    updated = True
                    print(
                        f"[Chezmoi/Preferences] Updated import method for '{target_name}' -> {target_method}"
                    )

                if not updated:
                    print(
                        f"[Chezmoi/Preferences] Asset library '{target_name}' is already up-to-date."
                    )
                continue

            # If the name doesn't exist at all, check if the path is duplicated under a different name
            if any(
                os.path.normpath(lib.path) == os.path.normpath(target_path)
                for lib in filepath_prefs.asset_libraries
            ):
                print(
                    f"[Chezmoi/Preferences Warning] Path '{target_path}' is already registered under a different library name. Skipping."
                )
                continue

            # Safe to add a brand new library entry
            try:
                bpy.ops.preferences.asset_library_add(directory=target_path)
                new_lib = filepath_prefs.asset_libraries[-1]
                new_lib.name = target_name
                if target_method in {"LINK", "APPEND", "APPEND_REUSE"}:
                    new_lib.import_method = target_method
                print(
                    f"[Chezmoi/Preferences] Successfully attached asset library: {target_name} -> {target_path} ({target_method})"
                )
            except Exception as e:
                print(
                    f"[Chezmoi/Preferences Error] Failed to register asset library: {e}"
                )
    # -------------------------------------------------------------------------
    # PART 4: Automated Extension/Add-on Synchronization (Blender 4.2+)
    # -------------------------------------------------------------------------
    if "extensions" in config and config["extensions"]:
        enabled_addons = set(bpy.context.preferences.addons.keys())
        available_modules = {mod.__name__ for mod in addon_utils.modules()}
        missing_extensions = []

        for pkg_id in config["extensions"]:
            # Idempotent check: treat classic add-ons and extensions as equivalent package IDs.
            if any(_module_matches_package(name, pkg_id) for name in enabled_addons):
                continue

            # If present but disabled, enable instead of reinstalling.
            disabled_match = next(
                (
                    name
                    for name in available_modules
                    if _module_matches_package(name, pkg_id)
                ),
                None,
            )
            if disabled_match:
                try:
                    bpy.ops.preferences.addon_enable(module=disabled_match)
                    print(
                        f"[Chezmoi/Extensions] Enabled installed add-on/extension: {disabled_match}"
                    )
                    enabled_addons.add(disabled_match)
                    continue
                except Exception as e:
                    print(
                        f"[Chezmoi/Extensions Warning] Could not enable '{disabled_match}': {e}"
                    )

            # Truly missing package, queue for installation from extension repos.
            if not disabled_match:
                missing_extensions.append(pkg_id)

        if missing_extensions:
            print(
                f"[Chezmoi/Extensions] Found {len(missing_extensions)} missing extensions. Synchronizing repositories..."
            )
            try:
                # 1. Force Blender to refresh its remote repository cache indices
                bpy.ops.extensions.repo_sync_all()

                # 2. Iterate and download the missing packages from the default store (repo_index=0)
                for pkg_id in missing_extensions:
                    print(
                        f"[Chezmoi/Extensions] Downloading and enabling extension: {pkg_id}"
                    )
                    bpy.ops.extensions.package_install(
                        repo_index=0, pkg_id=pkg_id, enable_on_install=True
                    )

                    # Validate install/enable result to avoid silent repeated reinstall attempts.
                    available_modules = {mod.__name__ for mod in addon_utils.modules()}
                    enabled_addons = set(bpy.context.preferences.addons.keys())
                    if not any(
                        _module_matches_package(name, pkg_id)
                        for name in available_modules | enabled_addons
                    ):
                        print(
                            f"[Chezmoi/Extensions Warning] Package was requested but still unavailable: {pkg_id}"
                        )

                # 3. Commit preferences changes to disk persistently
                bpy.ops.wm.save_userpref()
                print("[Chezmoi/Extensions] All extensions synchronized successfully.")
            except Exception as e:
                print(f"[Chezmoi/Extensions Error] Network installation failed: {e}")
        else:
            print(
                "[Chezmoi/Extensions] All specified extensions are already installed and active."
            )


def register():
    # Hook directly into the post-load routine so context variables exist safely
    bpy.app.handlers.load_post.append(load_and_sync_chezmoi)


def unregister():
    if load_and_sync_chezmoi in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_and_sync_chezmoi)


if __name__ == "__main__":
    # We only register the handler hook.
    # Because it lives in a nested directory, Blender automatically discovers and runs it on boot.
    register()
