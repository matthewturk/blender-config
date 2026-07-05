import json
import os
import socket
import sys

DEFAULT_CONNECTION_FILE = os.path.expanduser(
    os.environ.get(
        "BLENDER_JUPYTER_CONNECTION",
        "~/.local/state/blender-jupyter/connection.json",
    )
)


class BlenderExecutionError(RuntimeError):
    pass


class BlenderClient:
    def __init__(self, connection_file=None, timeout=None):
        self.connection_file = os.path.expanduser(
            connection_file or DEFAULT_CONNECTION_FILE
        )
        self.timeout = timeout

    def _load_connection(self):
        with open(self.connection_file, "r", encoding="utf-8") as handle:
            info = json.load(handle)
        return info

    def request(self, action, **payload):
        info = self._load_connection()
        timeout = self.timeout or info.get("timeout", 30.0)

        request = {
            "action": action,
            **payload,
        }
        if info.get("token"):
            request["token"] = info["token"]

        address = (info["host"], int(info["port"]))
        with socket.create_connection(address, timeout) as sock:
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk

        if not buffer:
            raise BlenderExecutionError(
                "No response received from Blender bridge."
            )

        return json.loads(buffer.decode("utf-8"))

    def ping(self):
        return self.request("ping")

    def exec(self, code, raise_on_error=True):
        response = self.request("exec", code=code)
        if raise_on_error and not response.get("ok"):
            raise BlenderExecutionError(
                response.get("traceback", "Blender execution failed.")
            )
        return response


def get_client(connection_file=None, timeout=None):
    return BlenderClient(connection_file=connection_file, timeout=timeout)


try:
    from IPython.core.magic import Magics, cell_magic, line_magic, magics_class
except ImportError:
    Magics = None
else:

    @magics_class
    class BlenderMagics(Magics):
        def _client(self, line):
            connection_file = line.strip() or None
            return BlenderClient(connection_file=connection_file)

        @line_magic
        def blender_status(self, line):
            response = self._client(line).ping()
            print(json.dumps(response, indent=2, sort_keys=True))
            return response

        @cell_magic
        def blender(self, line, cell):
            response = self._client(line).exec(cell, raise_on_error=False)

            stdout = response.get("stdout") or ""
            stderr = response.get("stderr") or ""
            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="", file=sys.stderr)

            if not response.get("ok"):
                raise BlenderExecutionError(
                    response.get("traceback", "Blender execution failed.")
                )

            result = response.get("result")
            if result:
                print(result)
            return result


def load_ipython_extension(ipython):
    if Magics is None:
        raise ImportError(
            "IPython is required to load the blender_jupyter extension."
        )
    ipython.register_magics(BlenderMagics)
