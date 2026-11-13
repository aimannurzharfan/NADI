"""Who is calling, security headers, and the start-up check for default secrets.

Client IP: the TCP peer. X-Forwarded-For is used only when the peer is in TRUSTED_PROXIES (comma-separated IPs), and
then the right-most address that is not a trusted proxy. Run uvicorn with --no-proxy-headers so it does not rewrite the
peer itself.

Localhost as admin: only when LOCALHOST_ADMIN is on (default on in local mode, always off in huawei mode), the peer is
this computer, the request carries no proxy header at all (X-Forwarded-For, Forwarded, X-Real-IP), so a reverse
proxy on the same machine can never pass outside callers off as local, and the Host header names this computer
(localhost, 127.0.0.1 or [::1]): a web page whose own domain is made to resolve to 127.0.0.1 (DNS rebinding) sends
its own name as Host and gets no admin rights.

Cross-site requests: a POST from another website open in a browser on the same network (or on this computer) is
refused with 403 before it reaches an endpoint (Origin or Sec-Fetch-Site says it came from elsewhere). The console
itself always calls from its own origin. No path is exempt, /iotda included: IoTDA's server push and the boards send
no Origin or Sec-Fetch-Site header, so only browsers are affected.

Paths: every check that compares a request path uses norm_path() (one slash between parts, no trailing slash, lower
case), so "/iotda/", "//iotda" and "/IOTDA" are treated like "/iotda". Exemptions that make a check looser use the
exact path instead (see bucket_of in server/main.py).
"""
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from server import config

PROXY_HEADERS = (b"x-forwarded-for", b"forwarded", b"x-real-ip")
ROOT = Path(__file__).resolve().parent.parent
MIN_SECRET = 16


def trusted_proxies():
    return {p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()}


def has_proxy_headers(headers):
    """headers: Starlette Headers or ASGI header list."""
    if hasattr(headers, "keys"):
        return any(h.decode() in headers for h in PROXY_HEADERS)
    return any(k.lower() in PROXY_HEADERS for k, _ in headers)


def client_ip(request):
    peer = request.client.host if request.client else ""
    if peer in trusted_proxies():
        chain = [a.strip() for a in request.headers.get("x-forwarded-for", "").split(",") if a.strip()]
        for addr in reversed(chain):
            if addr not in trusted_proxies():
                return addr[:64]
    return peer


def localhost_admin_enabled():
    if config.is_huawei():
        return False
    return os.getenv("LOCALHOST_ADMIN", "on").strip().lower() in ("on", "1", "true", "yes")


LOOPBACK_NAMES = ("localhost", "127.0.0.1", "[::1]", "::1")


def host_name(host_header):
    """"127.0.0.1:8000" -> "127.0.0.1", "[::1]:8000" -> "[::1]"."""
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host[:host.find("]") + 1] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_this_computer(request):
    """The caller is this computer, by its own loopback name, with no proxy in between."""
    peer = request.client.host if request.client else ""
    return (config.is_local_host(peer) and not has_proxy_headers(request.headers)
            and host_name(request.headers.get("host")) in LOOPBACK_NAMES)


def is_local_admin(request):
    return localhost_admin_enabled() and is_this_computer(request)


UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


def norm_path(path):
    """"/IOTDA/", "//iotda", "/iotda//" -> "/iotda"; "" and "/" -> "/"."""
    return "/" + "/".join(part for part in (path or "").lower().split("/") if part)


def cross_site(scope_headers, method):
    """True for a state-changing request that a browser says came from another site."""
    if method not in UNSAFE:
        return False
    h = {k.lower(): v for k, v in scope_headers}
    fetch_site = h.get(b"sec-fetch-site", b"").decode(errors="replace").lower()
    if fetch_site in ("cross-site", "same-site"):
        return True
    origin = h.get(b"origin")
    if origin is None:
        return False  # not a browser (curl, the boards, the stress scripts) or an old one
    netloc = urlsplit(origin.decode(errors="replace")).netloc.lower()
    return netloc != h.get(b"host", b"").decode(errors="replace").lower()


class SameOrigin:
    """403 for POST/PUT/PATCH/DELETE that a browser sent from another site (cross-site request forgery)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and cross_site(scope["headers"], scope["method"]):
            from fastapi.responses import JSONResponse

            from server.strings import t

            return await JSONResponse({"detail": t("api.cross_site")}, status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)


class RedactToken(logging.Filter):
    """uvicorn's access log prints the request line: hide ?token=... (the IoTDA push URL carries INGEST_TOKEN)."""
    PATTERN = re.compile(r"(token=)[^&\s\"]*", re.I)

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(self.PATTERN.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


def redact_access_log():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactToken) for f in logger.filters):
        logger.addFilter(RedactToken())


# --- security headers ---

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


class SecurityHeaders:
    """Adds the headers above to every HTTP response (inline scripts are not allowed by the CSP)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in HEADERS if h[0] not in names]
            await send(message)

        await self.app(scope, receive, wrapped)


# --- default secrets ---

SECRET_VARS = ("MYSQL_PASSWORD", "REDIS_PASSWORD", "ADMIN_TOKEN", "VIEWER_TOKEN", "INGEST_TOKEN", "MQTT_SERVER_PASSWORD",
               "MAAS_API_KEY", "HUAWEICLOUD_SK", "IOTDA_DEVICE_SECRET")


def known_defaults():
    """Every value written in .env.example and docker-compose.yml: none of them may be used as a real secret."""
    values = set()
    for name in (".env.example", "docker-compose.yml"):
        p = ROOT / name
        if p.exists():
            for m in re.finditer(r"^\s*-?\s*([A-Z0-9_]+)\s*[=:]\s*\"?([^\s\"#]+)", p.read_text(encoding="utf-8"), flags=re.M):
                values.add(m.group(2))
    return {v for v in values if len(v) >= 3}


def secrets_in_use():
    """[(name, value)] for every secret that is set, including each ADMIN_TOKENS token and MQTT device password."""
    out = [(k, os.getenv(k, "")) for k in SECRET_VARS if os.getenv(k, "")]
    for part in os.getenv("ADMIN_TOKENS", "").split(","):
        label, sep, token = part.partition(":")
        if sep and token.strip():
            out.append((f"ADMIN_TOKENS[{label.strip()}]", token.strip()))
    out += [(k, v) for k, v in os.environ.items() if k.startswith("MQTT_PASSWORD_") and v]
    return out


def secret_problems():
    """Messages for secrets that are defaults or too short, and for what huawei mode requires."""
    problems = []
    defaults = known_defaults()
    for name, value in secrets_in_use():
        if value in defaults:
            problems.append(f"{name} still has the example or docker-compose value")
        elif len(value) < MIN_SECRET and name not in ("HUAWEICLOUD_SK", "IOTDA_DEVICE_SECRET", "MAAS_API_KEY"):
            problems.append(f"{name} is shorter than {MIN_SECRET} characters")
    if config.is_huawei():
        if not os.getenv("VIEWER_TOKEN"):
            problems.append("VIEWER_TOKEN must be set in huawei mode (the dashboard data is not public)")
        if not (os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_TOKENS")):
            problems.append("ADMIN_TOKEN or ADMIN_TOKENS must be set in huawei mode")
        if not os.getenv("INGEST_TOKEN"):
            problems.append("INGEST_TOKEN must be set in huawei mode (without it anyone can post readings to /iotda)")
    return problems


def check_secrets_at_start():
    """Huawei mode: refuse to start with any problem. Local mode: print warnings and carry on."""
    problems = secret_problems()
    if not problems:
        return
    if config.is_huawei():
        raise SystemExit("Refusing to start in huawei mode: " + "; ".join(problems)
                         + ". Make new values with: python scripts/new_token.py")
    for p in problems:
        print(f"warning: {p} (fine on a laptop demo, not for a real deployment)", flush=True)
