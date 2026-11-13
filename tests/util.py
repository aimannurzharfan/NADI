"""Shared by the tests."""
from starlette.requests import Request

# The Host a browser on the server computer sends: only then does "this computer" count as admin (DNS rebinding).
LOCAL_URL = "http://127.0.0.1"


def local_request(path="/iotda", host="127.0.0.1"):
    """A request from this computer, for calling an endpoint function directly."""
    return Request({"type": "http", "method": "POST", "path": path, "client": ("127.0.0.1", 5000),
                    "headers": [(b"host", host.encode())]})
