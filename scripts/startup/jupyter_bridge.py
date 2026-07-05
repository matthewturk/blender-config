import contextlib
import errno
import io
import json
import os
import socketserver
import sys
import threading
import traceback

import bpy

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5667
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECTION_FILE = os.path.expanduser(
    "~/.local/state/blender-jupyter/connection.json"
)
CONFIG_PATH = os.path.expanduser("~/.config/blender/config.json")

_SERVER = None
_SERVER_THREAD = None
_EXEC_LOCK = threading.Lock()
_EXEC_GLOBALS = {
    "__builtins__": __builtins__,
    "__name__": "__main__",
    "bpy": bpy,
}


def _load_bridge_config():
    if not os.path.exists(CONFIG_PATH):
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except Exception as exc:
        print(f"[Blender/Jupyter] Failed to parse config.json: {exc}")
        return {}

    bridge_config = config.get("jupyter_bridge")
    if isinstance(bridge_config, dict):
        return bridge_config

    if bridge_config is not None:
        print("[Blender/Jupyter] jupyter_bridge must be an object/dict.")
    return {}


def _ensure_parent_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _write_connection_file(path, payload):
    _ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _cleanup_connection_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        print(f"[Blender/Jupyter] Failed to remove connection file: {exc}")


def _execute_code(code, timeout):
    completed = threading.Event()
    response = {}

    def _run_on_main_thread():
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with _EXEC_LOCK:
            with (
                contextlib.redirect_stdout(stdout_buffer),
                contextlib.redirect_stderr(stderr_buffer),
            ):
                try:
                    try:
                        compiled = compile(code, "<blender-jupyter>", "eval")
                    except SyntaxError:
                        compiled = compile(code, "<blender-jupyter>", "exec")
                        exec(compiled, _EXEC_GLOBALS)
                        result = None
                    else:
                        result = eval(compiled, _EXEC_GLOBALS)

                    response.update(
                        {
                            "ok": True,
                            "result": None if result is None else repr(result),
                            "stdout": stdout_buffer.getvalue(),
                            "stderr": stderr_buffer.getvalue(),
                        }
                    )
                except Exception:
                    response.update(
                        {
                            "ok": False,
                            "stdout": stdout_buffer.getvalue(),
                            "stderr": stderr_buffer.getvalue(),
                            "traceback": traceback.format_exc(),
                        }
                    )
                finally:
                    completed.set()

        return None

    bpy.app.timers.register(_run_on_main_thread, first_interval=0.0)

    if not completed.wait(timeout):
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "traceback": f"Execution did not finish within {timeout:.1f}s. "
            "Blender may be busy.",
        }

    return response


class _BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, request_handler, bridge_config):
        super().__init__(server_address, request_handler)
        self.auth_token = bridge_config.get("auth_token")
        self.timeout = float(bridge_config.get("timeout", DEFAULT_TIMEOUT))
        self.connection_file = os.path.expanduser(
            bridge_config.get("connection_file", DEFAULT_CONNECTION_FILE)
        )

    def dispatch(self, request):
        action = request.get("action", "exec")

        if self.auth_token and request.get("token") != self.auth_token:
            return {
                "ok": False,
                "error": "unauthorized",
                "traceback": "Request did not include the configured auth "
                "token.",
            }

        if action == "ping":
            return {
                "ok": True,
                "pid": os.getpid(),
                "blender_version": list(bpy.app.version),
                "scene": bpy.context.scene.name if bpy.context.scene else None,
            }

        if action != "exec":
            return {
                "ok": False,
                "error": "unsupported_action",
                "traceback": f"Unsupported action: {action}",
            }

        code = request.get("code")
        if not isinstance(code, str) or not code.strip():
            return {
                "ok": False,
                "error": "missing_code",
                "traceback": "The exec action requires a non-empty code "
                "string.",
            }

        return _execute_code(code, self.timeout)


class _BridgeRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            payload = self.rfile.readline()
            if not payload:
                return

            request = json.loads(payload.decode("utf-8"))
            response = self.server.dispatch(request)
        except json.JSONDecodeError as exc:
            response = {
                "ok": False,
                "error": "invalid_json",
                "traceback": f"Failed to decode request JSON: {exc}",
            }
        except Exception:
            response = {
                "ok": False,
                "error": "internal_error",
                "traceback": traceback.format_exc(),
            }

        self.wfile.write(json.dumps(response).encode("utf-8"))
        self.wfile.write(b"\n")


def _start_server(bridge_config):
    global _SERVER, _SERVER_THREAD

    if _SERVER is not None:
        return

    host = str(bridge_config.get("host", DEFAULT_HOST))
    port = int(bridge_config.get("port", DEFAULT_PORT))
    connection_file = os.path.expanduser(
        bridge_config.get("connection_file", DEFAULT_CONNECTION_FILE)
    )

    server = _BridgeServer((host, port), _BridgeRequestHandler, bridge_config)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    connection_info = {
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "token": bridge_config.get("auth_token"),
        "timeout": server.timeout,
        "connection_file": connection_file,
        "blender_version": list(bpy.app.version),
        "python_version": sys.version,
    }
    _write_connection_file(connection_file, connection_info)

    _SERVER = server
    _SERVER_THREAD = thread

    print(f"[Blender/Jupyter] Bridge listening on {host}:{port}")
    print(f"[Blender/Jupyter] Connection info written to {connection_file}")


def register():
    bridge_config = _load_bridge_config()
    if not bridge_config.get("enabled", False):
        return

    try:
        _start_server(bridge_config)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(
                "[Blender/Jupyter] Bridge port is already in use. Adjust "
                "jupyter_bridge.port or stop the other listener."
            )
            return
        print(f"[Blender/Jupyter] Failed to start bridge: {exc}")


def unregister():
    global _SERVER, _SERVER_THREAD

    if _SERVER is None:
        return

    connection_file = _SERVER.connection_file
    _SERVER.shutdown()
    _SERVER.server_close()
    _cleanup_connection_file(connection_file)

    _SERVER = None
    _SERVER_THREAD = None
