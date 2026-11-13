"""Who counts as local admin, trusted proxies, the viewer token, per-IP limits with Retry-After, security headers and
the start-up check for default secrets. No Redis/MySQL needed (limits run in memory in tests)."""
import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import config, guard, main, security, store

ADMIN = "admin-token-0123456789abcdef"
VIEWER = "viewer-token-0123456789abcdef"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    for k in ("ADMIN_TOKEN", "ADMIN_TOKENS", "VIEWER_TOKEN", "TRUSTED_PROXIES", "LOCALHOST_ADMIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(store, "rooms", lambda: [])
    monkeypatch.setattr(store, "emergency", lambda: {"on": False, "since": None})
    monkeypatch.setattr(main.alerts, "recent", lambda lang="en", limit=20: [])
    monkeypatch.setattr(store, "waste_today", lambda now: 0.0)
    return monkeypatch


def client(ip):
    return TestClient(main.app, client=(ip, 5000), base_url=LOCAL_URL)


# --- client IP and proxies ---

class Req:
    def __init__(self, peer, headers=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = {"host": "127.0.0.1:8000", **{k.lower(): v for k, v in (headers or {}).items()}}


def test_forwarded_for_only_from_trusted_proxies(env):
    spoof = {"X-Forwarded-For": "10.1.1.1"}
    assert security.client_ip(Req("192.168.1.5", spoof)) == "192.168.1.5"  # not trusted: header ignored
    env.setenv("TRUSTED_PROXIES", "127.0.0.1")
    assert security.client_ip(Req("127.0.0.1", spoof)) == "10.1.1.1"
    # the right-most address that is not a proxy: a client cannot hide behind a forged left-most entry
    assert security.client_ip(Req("127.0.0.1", {"X-Forwarded-For": "6.6.6.6, 10.1.1.1"})) == "10.1.1.1"
    assert security.client_ip(Req("127.0.0.1", {"X-Forwarded-For": "127.0.0.1"})) == "127.0.0.1"


def test_localhost_admin_needs_no_proxy_headers(env):
    assert security.is_local_admin(Req("127.0.0.1"))
    for h in ("X-Forwarded-For", "Forwarded", "X-Real-IP"):
        assert not security.is_local_admin(Req("127.0.0.1", {h: "1.2.3.4"}))  # a proxy on this computer
    assert not security.is_local_admin(Req("192.168.1.9"))
    env.setenv("LOCALHOST_ADMIN", "off")
    assert not security.is_local_admin(Req("127.0.0.1"))
    env.setenv("LOCALHOST_ADMIN", "on")
    env.setenv("NADI_MODE", "huawei")
    assert not security.is_local_admin(Req("127.0.0.1"))  # never in huawei mode


def test_proxy_on_this_computer_cannot_pass_callers_off_as_admin(env):
    env.setenv("ADMIN_TOKEN", ADMIN)
    local = client("127.0.0.1")
    assert local.get("/api/me").json()["admin"] is True  # the server computer itself
    proxied = local.get("/api/me", headers={"X-Forwarded-For": "203.0.113.9"}).json()
    assert proxied["admin"] is False
    assert local.post("/api/emergency", json={"on": True}, headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 401


# --- viewer token ---

def test_viewer_token_guards_every_read(env):
    env.setenv("VIEWER_TOKEN", VIEWER)
    env.setenv("ADMIN_TOKEN", ADMIN)
    lan = client("192.168.1.40")
    for path in ("/api/rooms", "/api/history", "/api/summary", "/api/energy", "/api/uptime", "/api/alerts", "/api/info",
                 "/api/health"):
        assert lan.get(path).status_code == 401, path
    me = lan.get("/api/me").json()
    assert me["viewer"] is False and me["viewer_required"] is True
    assert lan.get("/api/rooms", headers={"X-Viewer-Token": VIEWER}).status_code == 200
    assert lan.get("/api/rooms", headers={"X-Admin-Token": ADMIN}).status_code == 200  # an admin can read too
    assert lan.get("/api/rooms", headers={"X-Viewer-Token": "wrong-" + VIEWER}).status_code == 401
    assert client("127.0.0.1").get("/api/rooms").status_code == 200  # the server computer
    assert lan.get("/").status_code == 200  # the page itself loads and asks for the token


def test_viewer_token_is_not_an_admin_token(env):
    env.setenv("VIEWER_TOKEN", VIEWER)
    env.setenv("ADMIN_TOKEN", ADMIN)
    r = client("192.168.1.40").post("/api/emergency", json={"on": True}, headers={"X-Admin-Token": VIEWER})
    assert r.status_code == 401


def test_wrong_viewer_tokens_lock_out(env):
    env.setenv("VIEWER_TOKEN", VIEWER)
    lan = client("192.168.1.41")
    codes = [lan.get("/api/rooms", headers={"X-Viewer-Token": f"guess-{i}"}).status_code for i in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert lan.get("/api/rooms", headers={"X-Viewer-Token": VIEWER}).status_code == 200  # the right token still works


# --- rate limits ---

def test_reads_limited_per_ip_with_retry_after(env):
    env.setattr(main, "LIMITS", {**main.LIMITS, "read": 5})
    a, b = client("192.168.1.50"), client("192.168.1.51")
    codes = [a.get("/api/rooms").status_code for _ in range(7)]
    assert codes == [200] * 5 + [429, 429]
    r = a.get("/api/rooms")
    assert r.status_code == 429 and 1 <= int(r.headers["Retry-After"]) <= 61
    assert b.get("/api/rooms").status_code == 200  # another IP is not affected


def test_history_has_its_own_tighter_limit(env):
    env.setattr(main, "LIMITS", {**main.LIMITS, "history": 2})
    env.setattr(store, "history", lambda since, bucket=None, room_id=None: {})
    env.setattr(main, "_history_cache", {})
    a = client("192.168.1.52")
    assert [a.get("/api/history?minutes=5").status_code for _ in range(3)] == [200, 200, 429]
    assert a.get("/api/rooms").status_code == 200


def test_iotda_push_is_not_limited_per_ip(env):
    assert main.bucket_of("POST", "/iotda") is None
    assert main.bucket_of("GET", "/api/rooms") == "read"
    assert main.bucket_of("GET", "/api/rooms/room1/climate") == "history"
    assert main.bucket_of("POST", "/api/emergency") == "admin"
    assert main.bucket_of("GET", "/assets/index.js") == "static"


def test_limits_shared_through_valkey_when_it_is_up(env):
    calls = []

    class Pipe:
        def incr(self, key):
            calls.append(key)

        def expire(self, key, s):
            pass

        def execute(self):
            return [len(calls)]

    class R:
        def pipeline(self, transaction=False):
            return Pipe()

    env.setattr(guard, "USE_REDIS", True)
    env.setattr(guard, "_redis", lambda: R())
    assert guard.allow("read", "1.2.3.4", 2) == (True, 0)
    assert guard.allow("read", "1.2.3.4", 2) == (True, 0)
    assert guard.allow("read", "1.2.3.4", 2)[0] is False
    assert calls[0].startswith("rl:read:1.2.3.4:")


# --- headers ---

def test_security_headers_on_pages_and_api(env):
    for path in ("/", "/api/rooms", "/api/me"):
        h = client("127.0.0.1").get(path).headers
        assert "script-src 'self'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "no-referrer"


def test_built_console_has_no_inline_script():
    import re
    html = (main.WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)  # the CSP forbids inline scripts


def test_built_console_serves_its_own_icons():
    """The favicon and the touch icon come from this server (no CDN), and each file holds image data only."""
    import struct
    html = (main.WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon" href="/favicon.ico"' in html and 'rel="apple-touch-icon" href="/apple-touch-icon.png"' in html
    c = client("192.168.1.40")
    ico, png = c.get("/favicon.ico"), c.get("/apple-touch-icon.png")
    assert ico.status_code == png.status_code == 200
    assert ico.headers["content-type"].startswith("image/") and png.headers["content-type"] == "image/png"
    assert ico.content[:4] == b"\x00\x00\x01\x00" and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    kinds, pos = [], 8
    while pos < len(png.content):
        length, kind = struct.unpack(">I4s", png.content[pos:pos + 8])
        kinds.append(kind)
        pos += 12 + length
    assert set(kinds) <= {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND", b"sRGB", b"gAMA", b"pHYs"}  # no text or metadata chunks
    assert struct.unpack(">II", png.content[16:24]) == (192, 192)


# --- secrets at start-up ---

def test_huawei_refuses_default_or_short_secrets(env):
    env.setenv("NADI_MODE", "huawei")
    env.setenv("MYSQL_PASSWORD", "nadi_local_pw")  # the docker-compose value
    env.setenv("ADMIN_TOKEN", "short")
    with pytest.raises(SystemExit) as e:
        security.check_secrets_at_start()
    msg = str(e.value)
    assert "MYSQL_PASSWORD" in msg and "ADMIN_TOKEN is shorter" in msg and "VIEWER_TOKEN must be set" in msg
    assert "nadi_local_pw" not in msg and "short" not in msg.replace("shorter", "")  # values are never printed


def test_local_mode_only_warns(env, capsys):
    env.setenv("MYSQL_PASSWORD", "nadi_local_pw")
    security.check_secrets_at_start()
    assert "warning: MYSQL_PASSWORD" in capsys.readouterr().out


def test_huawei_starts_with_strong_secrets(env):
    env.setenv("NADI_MODE", "huawei")
    env.setenv("MYSQL_PASSWORD", "x" * 24)
    env.setenv("ADMIN_TOKENS", "warden:" + "a" * 32)
    env.setenv("VIEWER_TOKEN", "b" * 32)
    env.setenv("INGEST_TOKEN", "c" * 32)
    for k in ("REDIS_PASSWORD", "MQTT_SERVER_PASSWORD"):
        env.delenv(k, raising=False)
    env.setattr(security, "secrets_in_use", lambda: [("MYSQL_PASSWORD", "x" * 24), ("VIEWER_TOKEN", "b" * 32)])
    security.check_secrets_at_start()
    assert config.is_huawei()


def test_me_cannot_be_used_to_guess_tokens(env):
    env.setenv("ADMIN_TOKEN", ADMIN)
    env.setenv("VIEWER_TOKEN", VIEWER)
    lan = client("192.168.1.60")
    for i in range(5):
        assert lan.get("/api/me", headers={"X-Admin-Token": f"guess-{i}-0123456789"}).json()["admin"] is False
    assert lan.get("/api/me", headers={"X-Admin-Token": "guess-again-0123456789"}).json()["status"] == 429
    assert lan.get("/api/me", headers={"X-Viewer-Token": "guess-viewer-0123456789"}).json()["status"] == 429
    assert lan.get("/api/me", headers={"X-Admin-Token": ADMIN}).json()["admin"] is True  # the right token still works
    assert lan.get("/api/me").json()["viewer"] is False  # no token: no failure counted, plain answer
    assert main.bucket_of("GET", "/api/me") == "read"  # and it is rate limited like every read


# --- security review of the console and scale commits (each test pins one fix) ---

def test_cross_site_posts_refused(env):
    """Fix: another website open in a browser on the server computer could press admin buttons as "localhost"."""
    env.setattr(store, "devices", lambda: [])
    env.setattr(store, "forget_devices", lambda ids: None)
    local = client("127.0.0.1")
    for headers in ({"Origin": "http://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"},
                    {"Sec-Fetch-Site": "same-site", "Origin": "http://127.0.0.1"}):
        r = local.post("/api/devices/clear", headers=headers)
        assert r.status_code == 403 and "another website" in r.json()["detail"], headers
        assert "content-security-policy" in r.headers  # refused responses still carry the security headers
    assert local.post("/api/devices/clear", headers={"Origin": "http://127.0.0.1", "Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert local.post("/api/devices/clear").status_code == 200  # no Origin: curl, scripts, the boards
    assert local.get("/api/rooms", headers={"Origin": "http://evil.example"}).status_code == 200  # reads are not changed


def test_dns_rebinding_gets_no_localhost_admin(env):
    """Fix: a site whose name resolves to 127.0.0.1 sends its own name as Host; it must not count as this computer."""
    rebound = TestClient(main.app, client=("127.0.0.1", 5000), base_url="http://attacker.example:8000")
    assert rebound.get("/api/me").json()["admin"] is False
    assert rebound.post("/api/emergency", json={"on": True}).status_code == 403
    for host in ("localhost:8000", "127.0.0.1", "[::1]:8000"):
        assert security.host_name(host) in security.LOOPBACK_NAMES
    assert not security.is_local_admin(Req("127.0.0.1", {"Host": "nadi.example"}))


def test_iotda_without_ingest_token_only_from_this_computer(env):
    """Fix: without INGEST_TOKEN anyone on the network (or the internet in huawei mode) could post readings."""
    env.setattr(main, "INGEST_TOKEN", "")
    env.setattr(main, "process", lambda services, device_id=None: {"saved": 1, "duplicate": 0, "dropped": 0,
                                                                   "suspicious": 0, "errors": []})
    env.setattr(store, "mark_iotda_push", lambda ts: None)
    body = {"resource": "device.property", "notify_data": {"body": {"services": []}}}
    assert client("192.168.1.70").post("/iotda", json=body).status_code == 401
    assert client("127.0.0.1").post("/iotda", json=body, headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 401
    assert client("127.0.0.1").post("/iotda", json=body).status_code == 200
    env.setenv("NADI_MODE", "huawei")
    assert client("127.0.0.1").post("/iotda", json=body).status_code == 401  # never without a token in huawei mode
    env.setattr(main, "INGEST_TOKEN", "ingest-0123456789abcdef")
    assert client("192.168.1.70").post("/iotda?token=ingest-0123456789abcdef", json=body).status_code == 200


IOTDA_VARIANTS = ("/iotda", "/iotda/", "//iotda", "/IOTDA", "/Iotda/", "/iotda//", "//IoTDA/")
CROSS_SITE = ({"Origin": "http://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"})


def test_paths_normalised_before_every_check():
    for p in IOTDA_VARIANTS:
        assert security.norm_path(p) == "/iotda", p
    assert security.norm_path("") == security.norm_path("/") == "/"
    assert main.bucket_of("POST", "/iotda") is None
    for p in IOTDA_VARIANTS[1:]:
        assert main.bucket_of("POST", p) == "static", p  # the exemption is for the exact path only
    assert main.bucket_of("GET", "/API//History/") == "history"
    assert main.bucket_of("POST", "/api/chat/") == "admin"
    assert main.app.router.redirect_slashes is False


def test_cross_site_post_to_iotda_refused_on_every_path(env):
    """Fix: SameOrigin exempted exactly "/iotda", so a page in a browser on this computer could post readings there."""
    env.setattr(main, "INGEST_TOKEN", "")
    calls = []
    env.setattr(main, "process", lambda services, device_id=None: calls.append(services) or
                {"saved": 1, "duplicate": 0, "dropped": 0, "suspicious": 0, "errors": []})
    env.setattr(store, "mark_iotda_push", lambda ts: None)
    body = {"resource": "device.property", "notify_data": {"body": {"services": []}}}
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL, follow_redirects=False)
    for path in IOTDA_VARIANTS:
        for headers in CROSS_SITE:
            r = local.post(LOCAL_URL + path, json=body, headers=headers)
            assert r.status_code == 403 and "another website" in r.json()["detail"], (path, headers)
        r = local.post(LOCAL_URL + path, json=body)  # same computer, no browser headers: never a redirect to /iotda
        assert r.status_code == (200 if path == "/iotda" else 405), path
        assert "location" not in r.headers
    assert len(calls) == 1  # only the plain, same-site POST to the real path got through
    env.setattr(main, "INGEST_TOKEN", "ingest-0123456789abcdef")
    r = local.post("/iotda?token=ingest-0123456789abcdef", json=body, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403  # even with the right token a browser on another site is refused
    assert len(calls) == 1


def test_iotda_body_limit_on_every_path(env):
    big = b"{" + b" " * (main.MAX_IOTDA_BODY + 10) + b"}"
    mid = b"{" + b" " * (main.MAX_BODY + 10) + b"}"  # over the normal limit, under the IoTDA one
    local = client("127.0.0.1")
    for path in IOTDA_VARIANTS:
        assert local.post(LOCAL_URL + path, content=big, headers={"Content-Type": "application/json"}).status_code == 413, path
        assert local.post(LOCAL_URL + path, content=mid, headers={"Content-Type": "application/json"}).status_code != 413, path


def test_iotda_with_empty_ingest_token_refused_unless_this_computer(env):
    env.setattr(main, "INGEST_TOKEN", "")
    calls = []
    env.setattr(main, "process", lambda services, device_id=None: calls.append(services) or
                {"saved": 1, "duplicate": 0, "dropped": 0, "suspicious": 0, "errors": []})
    env.setattr(store, "mark_iotda_push", lambda ts: None)
    body = {"resource": "device.property", "notify_data": {"body": {"services": []}}}
    lan = TestClient(main.app, client=("192.168.1.70", 5000), base_url=LOCAL_URL, follow_redirects=False)
    for path in IOTDA_VARIANTS:
        for q in ("", "?token=", "?token=anything-at-all-0123"):
            assert lan.post(LOCAL_URL + path + q, json=body).status_code in (401, 405), (path, q)
    rebound = TestClient(main.app, client=("127.0.0.1", 5000), base_url="http://attacker.example:8000")
    assert rebound.post("/iotda", json=body).status_code == 401  # DNS rebinding is not this computer
    assert calls == []
    env.setenv("NADI_MODE", "huawei")
    assert client("127.0.0.1").post("/iotda", json=body).status_code == 401
    assert calls == []


def test_fake_zero_readings_during_emergency_refused(env):
    """Someone tries to make a room look empty during an emergency: every unauthorised path is refused and the live
    count stays; a board with the token that suddenly reports 0 is held back by the plausibility check."""
    env.setattr(main, "INGEST_TOKEN", "ingest-0123456789abcdef")
    env.setattr(store, "emergency", lambda: {"on": True, "since": 1, "drill": False, "id": None})
    env.setattr(store, "mark_iotda_push", lambda ts: None)
    env.setattr(main, "_emergency_now", lambda: {"on": True})
    live, pending = {}, {}
    env.setattr(store, "room", lambda room: live.get(room))
    env.setattr(store, "save_count", lambda room, ts, n, p: live.__setitem__(room, {"room_id": room, "headcount": n,
                                                                                     "count_ts": ts}) or True)
    env.setattr(store, "pending_count", lambda room: pending.get(room))
    env.setattr(store, "set_pending_count", lambda room, n: pending.__setitem__(room, n))
    env.setattr(store, "should_alert_suspicious", lambda room: True)
    env.setattr(main, "check_waste", lambda room, now: None)
    env.setattr(main.alerts, "send", lambda *a, **k: None)
    import time
    now = int(time.time())
    live["room3"] = {"room_id": "room3", "headcount": 40, "count_ts": now - 25}
    zero = {"resource": "device.property", "notify_data": {"header": {"device_id": "nadi-sim"}, "body": {"services": [
        {"service_id": "count", "properties": {"room_id": "room3", "ts": now - 5, "headcount": 0}}]}}}
    lan = TestClient(main.app, client=("192.168.1.80", 5000), base_url=LOCAL_URL, follow_redirects=False)
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL, follow_redirects=False)
    assert lan.post("/iotda", json=zero).status_code == 401                              # no token
    assert lan.post("/iotda?token=wrong-0123456789abcdef", json=zero).status_code == 401  # wrong token
    assert local.post("/iotda", json=zero).status_code == 401                             # token set: localhost too
    for path in IOTDA_VARIANTS:
        assert local.post(LOCAL_URL + path + "?token=ingest-0123456789abcdef", json=zero,
                          headers={"Origin": "http://evil.example"}).status_code == 403, path
    assert live["room3"]["headcount"] == 40
    r = lan.post("/iotda?token=ingest-0123456789abcdef", json=zero)  # a board with the token: 40 -> 0 is held back
    assert r.status_code == 200 and r.json()["suspicious"] == 1 and live["room3"]["headcount"] == 40


def test_huawei_refuses_to_start_without_ingest_token(env):
    env.setenv("NADI_MODE", "huawei")
    env.setenv("VIEWER_TOKEN", "b" * 32)
    env.setenv("ADMIN_TOKEN", "a" * 32)
    env.delenv("INGEST_TOKEN", raising=False)
    env.setattr(security, "secrets_in_use", lambda: [])
    with pytest.raises(SystemExit) as e:
        security.check_secrets_at_start()
    assert "INGEST_TOKEN must be set" in str(e.value)


def test_ingest_token_hidden_in_the_access_log():
    """Fix: the IoTDA push URL carries ?token=..., and uvicorn's access log (on in deploy/nadi.service) printed it."""
    import logging

    security.redact_access_log()
    security.redact_access_log()  # twice: still one filter
    logger = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, security.RedactToken) for f in logger.filters) == 1
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "POST", "/iotda?token=s3cret-value&x=1", "1.1", 200), None)
    for f in logger.filters:
        f.filter(rec)
    assert "s3cret" not in rec.getMessage() and "token=***&x=1" in rec.getMessage()


def test_body_limit_covers_every_method_with_a_body(env):
    """Fix: only POST/PUT/PATCH were capped; DELETE (and anything else) could stream an unlimited body."""
    r = client("192.168.1.71").request("DELETE", "/api/rooms", content=b"x" * 10000)
    assert r.status_code == 413


def test_api_docs_off_in_huawei_admin_only_in_local(env):
    """Item 7: /docs, /redoc and /openapi.json."""
    lan, local = client("192.168.1.72"), client("127.0.0.1")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert lan.get(path).status_code == 403, path  # local mode, not this computer, no token
        assert local.get(path).status_code == 200, path
    env.setenv("ADMIN_TOKEN", ADMIN)
    assert lan.get("/openapi.json").status_code == 401
    spec = lan.get("/openapi.json", headers={"X-Admin-Token": ADMIN}).json()
    assert "/api/emergency" in spec["paths"]
    assert "cdn.jsdelivr.net" in local.get("/docs").headers["content-security-policy"]  # Swagger UI's scripts
    assert "cdn.jsdelivr.net" not in local.get("/").headers["content-security-policy"]  # the console stays strict
    env.setenv("NADI_MODE", "huawei")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert local.get(path, headers={"X-Admin-Token": ADMIN}).status_code == 404, path


def test_mqtt_ca_key_kept_out_of_the_broker_folder(tmp_path, monkeypatch):
    """Fix: ca.key was written into deploy/mosquitto/certs, which is mounted into the broker container."""
    import sys

    from scripts import mqtt_tls

    certs, ca_dir = tmp_path / "mosquitto" / "certs", tmp_path / "mqtt_ca"
    monkeypatch.setattr(mqtt_tls, "CERTS", certs)
    monkeypatch.setattr(mqtt_tls, "CA_KEY", ca_dir / "ca.key")
    monkeypatch.setattr(mqtt_tls, "OLD_CA_KEY", certs / "ca.key")
    monkeypatch.setattr(mqtt_tls, "CONF", tmp_path / "mosquitto" / "conf.d" / "tls.conf")
    monkeypatch.setattr(mqtt_tls, "RECV_CA", tmp_path / "mqtt_ca.pem")
    monkeypatch.setattr(mqtt_tls, "CLIMATE_CA", tmp_path / "mqtt_ca.h")
    monkeypatch.setattr(sys, "argv", ["mqtt_tls.py", "--ip", "192.168.1.23"])
    mqtt_tls.main()
    assert (ca_dir / "ca.key").is_file() and not (certs / "ca.key").exists() and (certs / "server.key").is_file()
    old_key = (ca_dir / "ca.key").read_bytes()
    (certs / "ca.key").write_bytes(old_key)  # an earlier version left it in the broker's folder
    (ca_dir / "ca.key").unlink()
    mqtt_tls.main()
    assert (ca_dir / "ca.key").read_bytes() == old_key and not (certs / "ca.key").exists()  # moved, same CA
