"""NADI server: ingest -> Redis + MySQL, room API, emergency, alerts, chat, dashboard.

NADI_MODE=local:  subscribes to local Mosquitto (same topic/JSON as IoTDA). No Huawei Cloud calls.
NADI_MODE=huawei: IoTDA data forwarding (HTTP push) to POST /iotda, SMN alerts, MaaS chat.

    uvicorn server.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --limit-concurrency 200 --timeout-keep-alive 5
"""
import concurrent.futures
import hmac
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from typing import Literal  # noqa: E402

from pydantic import BaseModel, Field, StrictBool, StrictInt  # noqa: E402

from server import plan as plan_view  # noqa: E402
from server import site, upload  # noqa: E402
from server import (alerts, chat, clock, config, demo, energy, guard, health, incident, labels, logic, model, monitor,  # noqa: E402
                    privacy, security, store, timeutil, validate)
from server.health import check_mqtt as _check_mqtt  # noqa: E402
from server.plan import PLAN, exit_name  # noqa: E402
from server.health import check_mysql as _check_mysql  # noqa: E402
from server.health import check_redis as _check_redis  # noqa: E402
from server.strings import t  # noqa: E402

config.utf8_console()

INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")
REPORT_INTERVAL_S = int(os.getenv("REPORT_INTERVAL_S", "20"))
STALE_S = 3 * REPORT_INTERVAL_S  # no CSI report for this long = sensor offline
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_BODY = 4096  # same per-message limit as IoTDA
MAX_IOTDA_BODY = 8192  # a 4 KB device message plus the IoTDA forwarding envelope (header, resource, event)
MAX_QUESTION = 500
MAX_HEADCOUNT_LABEL = 100   # the labelling page: 0 to 100 people
JUMP_LIMIT = int(os.getenv("JUMP_LIMIT", "20"))  # a count changing by more than this within one report is suspicious
ROOMS_CACHE_S = float(os.getenv("ROOMS_CACHE_S", "1"))
# Per-IP requests per minute, by kind of request (see RateLimit). Chat and emergency have their own, stricter limits.
LIMITS = {"read": int(os.getenv("READ_PER_MIN", "240")), "history": int(os.getenv("HISTORY_PER_MIN", "60")),
          "admin": int(os.getenv("ADMIN_PER_MIN", "30")), "static": int(os.getenv("STATIC_PER_MIN", "600"))}


def warm_ollama():
    """Load the local chat model in the background so the first question on stage isn't slow."""
    be = chat.backend()
    if be and chat.ollama_up(max_age_s=0):
        try:
            chat.llm_answer({**be, "timeout": 120}, "ping", "OK.")  # loading the model can take a minute
            print("Ollama chat model loaded", flush=True)
        except Exception as e:
            print(f"Ollama warm-up failed: {e}", flush=True)


TICK_S = 5  # sensor offline check, incident tracking and the minute snapshots


def background_tick(now=None):
    """Every TICK_S: sensor offline / back online alerts, and during an emergency or drill, which rooms are not
    reporting plus a snapshot every minute. Never raises: a failure here must not stop the next tick."""
    now = now or int(time.time())
    if not health.should_try("redis"):
        return
    try:
        em = store.emergency()
        monitor.check(store, now, REPORT_INTERVAL_S, em)
        if em["on"] and em.get("id"):
            views = room_views(now)
            incident.track_offline(em["id"], views, now)
            if incident.snapshot_due(em["id"], now):
                save_snapshot(em, views, now)
    except store.REDIS_ERRORS:
        health.mark("redis", False)
    except Exception as e:
        print(f"background check failed: {e}", flush=True)


def save_snapshot(em, views, now):
    """Write the export page to disk (JSON + printable HTML). A full disk must not stop the alarm: log and go on."""
    try:
        incident.save_snapshot(em["id"], incident.build_snapshot(em, views, incident.statuses(em["id"]), now))
    except store.REDIS_ERRORS[0]:  # Redis itself (OSError, e.g. a full disk, is the snapshot's own problem)
        raise
    except Exception as e:
        print(f"snapshot not saved: {e}", flush=True)


def start_ticks():
    def loop():
        while True:
            time.sleep(TICK_S)
            background_tick()

    threading.Thread(target=loop, daemon=True, name="nadi-tick").start()


@asynccontextmanager
async def lifespan(app):
    print(f"NADI_MODE={config.mode()}", flush=True)
    config.log_to_file()
    security.redact_access_log()
    security.check_secrets_at_start()
    if validate.device_rooms() is None:
        print("DEVICE_ROOMS is not set: any device may report for any known room.", flush=True)
    store.init()
    health.start_watch(on_mysql_back=store.flush_buffer)
    store.start_retention()
    clock.start()
    start_ticks()
    mqtt = None
    if not config.is_huawei():
        from server import mqtt_local

        mqtt = mqtt_local.start(ingest)
        threading.Thread(target=warm_ollama, daemon=True).start()
    demo_client = demo.start(set_emergency) if demo.enabled() else None
    yield
    for client in (mqtt, demo_client):
        if client is not None:
            client.loop_stop()
            client.disconnect()


# API docs: never in huawei mode, admin only in local mode (routes near the end of this file)
app = FastAPI(title="NADI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# no automatic "/iotda/" -> "/iotda" redirect: a browser would repeat a POST on a 307, so a redirect could carry one
# past a check that compared only the first path
app.router.redirect_slashes = False


MAX_PLAN_BODY = 64 * 1024 + 1024      # a floor plan document (64 KB) and its note
MAX_IMAGE_BODY = 2 * 1024 * 1024      # a floor plan background image


def body_limit(method, path):
    """The body size allowed for one request: exact, normalised paths only get more than MAX_BODY."""
    p = security.norm_path(path)
    parts = p.split("/")
    if p == "/iotda":
        return MAX_IOTDA_BODY
    if len(parts) == 5 and parts[1:3] == ["api", "floors"] and site.FLOOR_ID.fullmatch(parts[3]):
        if method == "PUT" and parts[4] == "plan":
            return MAX_PLAN_BODY
        if method == "POST" and parts[4] == "image":
            return MAX_IMAGE_BODY
    return MAX_BODY


class BodyLimit:
    """Refuse request bodies over the limit with 413 before anything parses them (Content-Length or streamed).
    Every method that can carry a body, not only POST: nothing may stream an unlimited body in."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        limit = body_limit(scope["method"], scope["path"])
        too_large = JSONResponse({"detail": t("api.too_large", limit=limit)}, status_code=413)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return await too_large(scope, receive, send)
        body, more = b"", True
        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            if len(body) > limit:
                return await too_large(scope, receive, send)
        done = False

        async def replay():
            nonlocal done
            if not done:
                done = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def bucket_of(method, path):
    """Which per-IP limit a request counts against, or None for IoTDA pushes (they have their own token).
    The two exemptions (None) need the exact path; "/iotda/" or "/API/CHAT" is limited like everything else."""
    if path == "/iotda":
        return None
    p = security.norm_path(path)
    if p.startswith("/api/"):
        if p in ("/api/history", "/api/summary", "/api/energy", "/api/uptime") or p.endswith("/climate"):
            return "history"
        if method != "GET":
            return None if path == "/api/chat" else "admin"  # chat has its own per-IP limit in the endpoint
        return "read"
    return "static"


class RateLimit:
    """Per-IP limit on every request (kept in Valkey, see server/guard.py): 429 with Retry-After when over."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        bucket = bucket_of(scope["method"], scope["path"])
        if bucket:
            ok, wait = guard.allow(bucket, security.client_ip(Request(scope)), LIMITS[bucket])
            if not ok:
                return await JSONResponse({"detail": t("api.rate_limited", seconds=wait)}, status_code=429,
                                          headers={"Retry-After": str(wait)})(scope, receive, send)
        await self.app(scope, receive, send)


app.add_middleware(BodyLimit)
app.add_middleware(RateLimit)
app.add_middleware(security.SameOrigin)  # cross-site POSTs refused before they count or reach an endpoint
app.add_middleware(security.SecurityHeaders)


@app.exception_handler(RequestValidationError)
async def bad_request(request, exc):
    """422 without echoing the input back: a NaN or a huge value in the body would otherwise break the reply."""
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(store.REDIS_ERRORS[0])
async def redis_down(request, exc):
    health.mark("redis", False)
    return JSONResponse({"detail": t("api.redis_offline")}, status_code=503)


@app.exception_handler(store.MYSQL_ERRORS[0])
async def mysql_down(request, exc):
    health.mark("mysql", False)
    return JSONResponse({"detail": t("api.mysql_offline")}, status_code=503)


def client_ip(request):
    return security.client_ip(request)


MIN_TOKEN_LEN = 16  # long enough that guessing is hopeless even without the lockout


def admin_tokens():
    """{token: label}. ADMIN_TOKEN is labelled "admin"; ADMIN_TOKENS=warden1:tokenA,warden2:tokenB adds named ones,
    so the audit log shows who started or ended an emergency. Tokens shorter than MIN_TOKEN_LEN are ignored."""
    pairs = [(os.getenv("ADMIN_TOKEN", "").strip(), "admin")]
    for part in os.getenv("ADMIN_TOKENS", "").split(","):
        label, sep, token = part.partition(":")
        if sep and label.strip():
            pairs.append((token.strip(), label.strip()[:32]))
    tokens = {}
    for token, label in pairs:
        if len(token) >= MIN_TOKEN_LEN:
            tokens[token] = label
        elif token:
            _warn_once(f"admin token for {label} is shorter than {MIN_TOKEN_LEN} characters: ignored")
    return tokens


def tokens_configured():
    """True if ADMIN_TOKEN or ADMIN_TOKENS has anything in it, valid or not."""
    return bool(os.getenv("ADMIN_TOKEN", "").strip() or os.getenv("ADMIN_TOKENS", "").strip())


_warned = set()


def _warn_once(msg):
    if msg not in _warned:
        _warned.add(msg)
        print(msg, flush=True)


def token_label(given):
    """The label of the admin token given, or None."""
    label = None
    for token, name in admin_tokens().items():
        if hmac.compare_digest(given.encode(), token.encode()):
            label = name
    return label


def refuse_token(ip, message, guessed):
    """401 for a missing or wrong token. Only a wrong token counts towards the lockout (a page opened without one
    polls every few seconds and must not lock its own address); during a lockout, guesses get 429."""
    if not guessed:
        raise HTTPException(401, message)
    wait = guard.locked(ip)
    if wait:
        raise HTTPException(429, t("api.locked_out", minutes=(wait + 59) // 60), headers={"Retry-After": str(wait)})
    if guard.failed(ip):
        print(f"too many wrong tokens from {ip}, further guesses refused for {guard.LOCK_S // 60} minutes", flush=True)
    raise HTTPException(401, message)


def require_admin(request: Request, x_admin_token: str = Header("")):
    """A right admin token (ADMIN_TOKEN or one of ADMIN_TOKENS), or this computer when LOCALHOST_ADMIN is on and the
    request has no proxy headers (server/security.py). Returns who it was (token label or "localhost") for the audit log.
    A right token always works, even during a lockout, so nobody can lock a warden out during a fire."""
    ip = client_ip(request)
    if not admin_tokens() and tokens_configured():  # fail closed: a bad token must not quietly fall back to localhost
        raise HTTPException(503, t("api.admin_token_short", n=MIN_TOKEN_LEN))
    label = token_label(x_admin_token) if x_admin_token else None
    if label is not None:
        return label
    if security.is_local_admin(request):
        return "localhost"
    if admin_tokens():
        refuse_token(ip, t("api.admin_required"), bool(x_admin_token))
    if config.is_huawei():
        raise HTTPException(403, t("api.admin_huawei"))
    raise HTTPException(403, t("api.admin_localhost"))


def viewer_allowed(request, x_admin_token="", x_viewer_token=""):
    """Read access: everyone when VIEWER_TOKEN is not set; otherwise the viewer token, an admin token, or local admin."""
    viewer = os.getenv("VIEWER_TOKEN", "")
    if not viewer:
        return True
    if x_viewer_token and hmac.compare_digest(x_viewer_token.encode(), viewer.encode()):
        return True
    if x_admin_token and token_label(x_admin_token) is not None:
        return True
    return security.is_local_admin(request)


def require_viewer(request: Request, x_admin_token: str = Header(""), x_viewer_token: str = Header("")):
    """Dependency for every read endpoint (required in huawei mode, see server/security.py)."""
    if not viewer_allowed(request, x_admin_token, x_viewer_token):
        refuse_token(client_ip(request), t("api.viewer_required"), bool(x_viewer_token or x_admin_token))


VIEWER = [Depends(require_viewer)]


def rate_limit(bucket, request, limit):
    ok, wait = guard.allow(bucket, client_ip(request), limit)
    if not ok:
        raise HTTPException(429, t("api.rate_limited", seconds=wait), headers={"Retry-After": str(wait)})


def check_waste(room_id, now):
    """Update the empty-with-air-conditioning-on timer and alert at most once per room per hour."""
    room = store.room(room_id)
    if room is None or room["headcount"] is None:
        return
    since = logic.update_empty_cold_since(room["empty_cold_since"], room["headcount"], room["temp_c"], now,
                                          energy.current(now)["ac_on_below_c"])
    store.set_empty_cold_since(room_id, since)
    energy.add_ended(energy.ended(room["empty_cold_since"], since, now, room_id), now, room_id)
    waste = energy.waste(since, now, room_id)
    if waste and logic.should_alert_waste(room["waste_alert_ts"], now):
        store.set_waste_alert_ts(room_id, now)
        name = config.room_name(room_id)
        alerts.send("waste", "alert.waste_subject", "alert.waste_body", name=name, minutes=waste["minutes"],
                    temp=f"{room['temp_c']:.1f}", rm=f"{waste['rm']:.2f}")


def _as_dict(value):
    """value if it is a dict, else {}. dict.get(k, {}) only substitutes a missing key, not a wrong type."""
    return value if isinstance(value, dict) else {}


def process(services, device_id=None):
    """Check a whole report (server/validate.py), then store it. Any bad entry rejects the report: nothing stored.
    Returns {"saved", "duplicate", "errors"}."""
    clean, errors = validate.check_all(services, device_id)
    if errors:
        print(f"report from {device_id or 'unknown device'} rejected: {'; '.join(errors)}", flush=True)
        return {"saved": 0, "duplicate": 0, "errors": errors}
    saved = duplicate = dropped = suspicious = 0
    touched = set()
    em = _emergency_now()
    for svc in clean:
        props = dict(svc["properties"])
        board = props.pop("health", {})  # the sending board's health, kept per device
        room_id, ts, p = svc["room_id"], svc["ts"], {**props, "source": device_id[:64] if device_id else None}
        if store.already_seen(svc["service_id"], room_id, ts):  # a resend (MQTT QoS 1) is a duplicate, not a flood
            duplicate += 1
            continue
        if device_id and not device_rate_ok(device_id, room_id, svc["service_id"]):
            dropped += 1
            continue
        if svc["service_id"] == "csi":
            count, _ = model.headcount(p)
            stored = store.save_csi(room_id, ts, max(0, min(3, int(count))), p)  # 3 from CSI means "at least 3"
        elif svc["service_id"] == "count":
            if not plausible(room_id, ts, int(p["headcount"])):
                suspicious += 1
                continue
            stored = store.save_count(room_id, ts, int(p["headcount"]), p)
        else:
            stored = store.save_climate(room_id, ts, p)
        if stored is False:
            duplicate += 1
            continue
        saved += 1
        touched.add(room_id)
        if em.get("id") and svc["service_id"] in ("csi", "count"):
            try:
                incident.on_count(em["id"], room_id, int(p["headcount"]) if svc["service_id"] == "count" else
                                  max(0, min(3, int(count))), ts)
            except store.REDIS_ERRORS:
                health.mark("redis", False)
        if device_id and health.ok("redis"):
            if svc["service_id"] == "csi" and p.get("n_packets") is not None:
                board = {**board, "n_packets": p["n_packets"]}  # packets per report: shows the sender is working
            try:
                store.save_device(device_id[:64], svc["service_id"], room_id, int(time.time()), board)
            except store.REDIS_ERRORS:
                health.mark("redis", False)
    now = int(time.time())
    if health.ok("redis"):
        for room_id in touched:
            try:
                check_waste(room_id, now)
            except store.REDIS_ERRORS:
                health.mark("redis", False)
    return {"saved": saved, "duplicate": duplicate, "dropped": dropped, "suspicious": suspicious, "errors": []}


def _emergency_now():
    """The emergency state, or {} while Redis is offline (ingest goes on without the incident record)."""
    if not health.should_try("redis"):
        return {}
    try:
        return store.emergency()
    except store.REDIS_ERRORS:
        health.mark("redis", False)
        return {}


_device_seen = {}  # memory fallback for device_rate_ok


def device_rate_ok(device_id, room_id, service_id):
    """A board may report each room and service at most once per REPORT_INTERVAL_S / 2; faster messages are dropped
    and logged (a broken or hostile board flooding the server)."""
    gap_ms = int(float(os.getenv("DEVICE_MIN_GAP_S", "").strip() or REPORT_INTERVAL_S / 2) * 1000)  # empty = default
    if gap_ms <= 0 or (demo.enabled() and device_id == os.getenv("SIM_DEVICE_ID", "nadi-sim")):
        return True  # switched off, or the demo story (it reports every few seconds on purpose)
    key = f"devrate:{device_id[:64]}:{room_id}:{service_id}"
    if health.ok("redis"):
        try:
            if store.r.set(key, 1, nx=True, px=gap_ms):
                return True
            print(f"report from {device_id} for {room_id} dropped: faster than one every {gap_ms / 1000:g} s", flush=True)
            return False
        except store.REDIS_ERRORS:
            health.mark("redis", False)
    now = time.monotonic()
    last = _device_seen.get(key)
    if last is not None and now - last < gap_ms / 1000:
        return False
    if len(_device_seen) > 10000:
        _device_seen.clear()
    _device_seen[key] = now
    return True


def plausible(room_id, ts, count):
    """A count that jumps by more than JUMP_LIMIT within one report interval is held back as suspicious, not shown.
    If the next report agrees with it (within JUMP_LIMIT), it is accepted: a real crowd arriving shows up one report
    later; a single bad or forged reading never reaches the dashboard."""
    try:
        room = store.room(room_id)
        pending = store.pending_count(room_id)
    except store.REDIS_ERRORS:
        return True
    if room is None or room["headcount"] is None or room["count_ts"] is None:
        return True
    if abs(count - room["headcount"]) <= JUMP_LIMIT or ts - room["count_ts"] > 2 * REPORT_INTERVAL_S:
        store.set_pending_count(room_id, None)
        return True
    if pending is not None and abs(count - pending) <= JUMP_LIMIT:
        store.set_pending_count(room_id, None)
        return True
    store.set_pending_count(room_id, count)
    name = config.room_name(room_id)
    print(f"suspicious reading in {name}: {room['headcount']} to {count} in one report, held back", flush=True)
    if store.should_alert_suspicious(room_id):
        alerts.send("info", "alert.suspicious_subject", "alert.suspicious_body", name=name, before=room["headcount"],
                    after=count)
    return False


def ingest(services, device_id=None):
    """One property report ({"services": [...]} body) from IoTDA push or local MQTT. Returns rows saved."""
    return process(services, device_id)["saved"]


@app.post("/iotda")
def iotda_push(msg: dict, request: Request, token: str = ""):
    """IoTDA data forwarding (HTTP push) target. Set the rule URL to http://<host>:8000/iotda?token=...
    Without INGEST_TOKEN (local mode only: huawei mode refuses to start without it) only this computer may post here,
    for sim/fake_sensor.py --local; anyone else could otherwise post made-up counts for any room."""
    if INGEST_TOKEN:
        if not hmac.compare_digest(token.encode(), INGEST_TOKEN.encode()):
            raise HTTPException(401, t("api.bad_token"))
    elif config.is_huawei() or not security.is_this_computer(request):
        raise HTTPException(401, t("api.ingest_local_only"))
    if msg.get("resource") != "device.property":
        return {"ok": True, "ignored": msg.get("resource")}
    notify = _as_dict(msg.get("notify_data"))
    claimed = _as_dict(notify.get("header")).get("device_id")
    # without INGEST_TOKEN anyone can post here and claim any device, so the claim only counts with the token
    device_id = claimed if isinstance(claimed, str) and INGEST_TOKEN else None
    result = process(_as_dict(notify.get("body")).get("services"), device_id)
    if result["errors"]:
        raise HTTPException(422, result["errors"])
    if claimed != "sim-local" and health.ok("redis"):  # display only, for the "Built with" footer
        store.mark_iotda_push(int(time.time()))  # real IoTDA traffic, shown in "Built with"
    return {"ok": True, "saved": result["saved"], "duplicate": result["duplicate"], "dropped": result["dropped"],
            "suspicious": result["suspicious"]}


def room_views(now, rooms=None):
    out, names = [], config.room_names()
    for r in store.rooms() if rooms is None else rooms:
        live = r["count_ts"] is not None and now - r["count_ts"] <= STALE_S
        out.append({
            "room_id": r["room_id"], "name": config.room_name(r["room_id"], names),
            "headcount": r["headcount"], "at_least": bool(r.get("at_least")), "count_ts": r["count_ts"],
            "counter": r.get("counter", "csi"),  # "count": an exact counter, labelled on every screen
            "temp_c": r["temp_c"], "humidity": r["humidity"], "live": live,
            "waste": energy.waste(r["empty_cold_since"], now, r["room_id"]) if live else None,
        })
    return out


_last = {"rooms": None, "emergency": {"on": False, "since": None, "drill": False, "id": None}, "alerts": {},
         "waste": 0.0, "waste_kwh": None, "ts": None, "accountability": {}}


def dependencies():
    """What is offline, for the dashboard banner: {name: unix time it went offline}."""
    out = health.down()
    if config.is_huawei():
        out.pop("mqtt", None)
    return out


def refresh_live(now, lang=None):
    """Read live state from Redis into _last. If Redis is offline, _last keeps the last known data."""
    if health.should_try("redis"):
        try:
            em = store.emergency()
            _last.update(rooms=store.rooms(), emergency=em, waste=store.waste_today(now), ts=now,
                         waste_kwh=store.waste_day_extra(now)[0],  # None: today's total is in RM only so far
                         accountability=incident.statuses(em.get("id")) if em.get("on") else {})
            if lang:
                _last["alerts"][lang] = alerts.recent(lang)
            health.mark("redis", True)
        except store.REDIS_ERRORS:
            health.mark("redis", False)
    return None if health.ok("redis") else _last["ts"]


_rooms_cache = {}


@app.get("/api/rooms", dependencies=VIEWER)
def api_rooms(lang: str = "en"):
    """lang=ms gives the alerts in Malay. If Redis is offline, the last known data is returned with "stale_ts".
    Cached for ROOMS_CACHE_S (1 s): a hundred open dashboards cost one read."""
    lang = "ms" if lang == "ms" else "en"
    hit = _rooms_cache.get(lang)
    if hit and time.monotonic() - hit[0] < ROOMS_CACHE_S:
        return hit[1]
    out = rooms_state(lang)
    _rooms_cache[lang] = (time.monotonic(), out)
    return out


def rooms_state(lang):
    now = int(time.time())
    stale = refresh_live(now, lang)
    rooms = room_views(now, _last["rooms"] or [])
    if stale is not None:  # Redis offline: nothing is live, every count is the last known one
        for r in rooms:
            r["live"], r["waste"] = False, None
    ongoing = sum(r["waste"]["rm"] for r in rooms if r["waste"])
    waste_rm = _last["waste"] + ongoing
    ended_kwh = _last.get("waste_kwh")
    if ended_kwh is None:  # ended stretches stored in RM only: their kWh at the tariff in force now
        tariff = energy.current(now)["tariff_rm_per_kwh"]
        ended_kwh = _last["waste"] / tariff if tariff else 0.0
    return {"now": now, "stale_s": STALE_S, "rooms": rooms,
            "waste_today_rm": round(waste_rm, 2),
            "waste_today_kwh": round(ended_kwh + sum(r["waste"]["kwh"] for r in rooms if r["waste"]), 1),
            "emergency": _last["emergency"], "accountability": _last["accountability"] if _last["emergency"]["on"] else {},
            "alerts": _last["alerts"].get(lang, []), "offline": dependencies(), "stale_ts": stale, "demo": demo.status(),
            "clock": clock.warning()}


HISTORY_CACHE_S = 5
_history_cache = {}


CLIMATE_INTERVAL_S = 60  # the climate node reports once a minute
def plan_rooms():
    """Every room drawn on a real floor plan (they change when an admin saves a plan)."""
    return tuple(PLAN["rooms"])


RETIRED_S = 24 * 3600


@app.post("/api/devices/clear", dependencies=[Depends(require_admin)])
def api_devices_clear():
    """Forget simulator devices and devices not seen for 24 hours ("clear test devices")."""
    now = int(time.time())
    sims = {os.getenv("SIM_DEVICE_ID", "nadi-sim"), "sim-local"}
    gone = [d["device_id"] for d in store.devices()
            if d["device_id"] in sims or d["last_seen"] is None or now - d["last_seen"] > RETIRED_S]
    store.forget_devices(gone)
    return {"cleared": len(gone)}


@app.get("/api/devices", dependencies=[Depends(require_admin)])
def api_devices(retired: bool = False):
    """Every board that has reported, with its latest health (firmware, uptime, Wi-Fi signal, free memory, dropped).
    Admin only: device IDs are broker usernames and firmware versions help an attacker pick a target."""
    now = int(time.time())
    out = []
    sims = {os.getenv("SIM_DEVICE_ID", "nadi-sim"), "sim-local"}
    for d in store.devices():
        every = REPORT_INTERVAL_S if d["service"] == "csi" else CLIMATE_INTERVAL_S
        d["online"] = d["last_seen"] is not None and now - d["last_seen"] <= 3 * every
        d["name"] = config.room_name(d["room_id"]) if d["room_id"] else None
        d["simulator"] = d["device_id"] in sims
        d["retired"] = d["last_seen"] is None or now - d["last_seen"] > RETIRED_S
        if retired or not d["retired"]:
            out.append(d)
    hidden = sum(1 for d in store.devices() if d["last_seen"] is None or now - d["last_seen"] > RETIRED_S) if not retired else 0
    return {"now": now, "devices": out, "report_interval_s": REPORT_INTERVAL_S, "retired_hidden": hidden}


def lan_ip():
    """This computer's address on the local network (the route a board would use), or None."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # UDP connect sends nothing; it only picks the outgoing interface
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()
    return None if not ip or ip.startswith("127.") else ip


@app.get("/api/board-setup", dependencies=[Depends(require_admin)])
def api_board_setup():
    """Local mode: the broker address to type into a board's "setup", and whether Mosquitto still listens on it."""
    if config.is_huawei():
        raise HTTPException(409, t("api.board_local_only"))
    ip, configured = lan_ip(), os.getenv("MQTT_LAN_IP", "").strip() or None
    return {"ip": ip, "port": int(os.getenv("MQTT_PORT", "1883")), "configured_ip": configured,
            "mismatch": bool(ip and configured and ip != configured)}


HISTORY_MAX_MIN = 30 * 24 * 60  # 30 days (history is kept HISTORY_RETENTION_DAYS, 90 by default)
HISTORY_POINTS = 300   # summary tiles: about this many points
MAX_POINTS = 5000      # per history response, all rooms together


def bucket_for(minutes, rooms=1):
    """Seconds per point: 1 min up to an hour, 15 min up to a day, 1 h up to 7 days, a Malaysian day beyond (headcount:
    the highest in the bucket; temperature: the mean). Coarser if all rooms together would pass MAX_POINTS."""
    bucket = 60 if minutes <= 60 else 900 if minutes <= 24 * 60 else 3600 if minutes <= 7 * 24 * 60 else 86400
    while rooms * (minutes * 60 // bucket) > MAX_POINTS:
        bucket *= 2
    return bucket


PEOPLE_BUCKETS = ((60, 60), (24 * 60, 1800), (7 * 24 * 60, 3 * 3600))  # (up to this many minutes, seconds per point)
SINCE_LOOKBACK_S = 30 * 86400
SINCE_CACHE_S = 30
_since_cache = {}  # room_id -> (monotonic time, store.last_change's answer)


def people_bucket(minutes):
    """Seconds per point of the people chart: 1 min up to an hour, 30 min up to a day, 3 h up to 7 days, a Malaysian
    day beyond."""
    return next((bucket for most, bucket in PEOPLE_BUCKETS if minutes <= most), 86400)


def people_view(room, minutes, now):
    """One room for the people chart: [[bucket start, peak, minutes occupied], ...] and since when the room has been
    empty or occupied without a break ("since": {"occupied", "ts"}; ts None when unchanged for SINCE_LOOKBACK_S)."""
    bucket = people_bucket(minutes)
    points = store.people_history(room, now - minutes * 60, bucket)
    hit = _since_cache.get(room)
    if not hit or time.monotonic() - hit[0] >= SINCE_CACHE_S:  # the look back can be long: at most once per room per 30 s
        if len(_since_cache) > SIGNAL_CACHE_ROOMS:
            _since_cache.clear()
        hit = _since_cache[room] = (time.monotonic(), store.last_change(room, now - SINCE_LOOKBACK_S))
    occupied, ts = hit[1]
    return {"now": now, "bucket_s": bucket, "room_id": room, "people": points,
            "since": None if occupied is None else {"occupied": occupied, "ts": ts}}


@app.get("/api/history", dependencies=VIEWER)
def api_history(minutes: int = 30, room: str = "", view: str = Query("", pattern="^(people)?$")):
    """Headcount per room over the last N minutes (up to 30 days; one point per bucket, the highest count in it).
    With room=, also "waste": the buckets in which that room was empty throughout and colder than the "counts as on"
    temperature in force then. Buckets with no report are left out: they are gaps, not 0.
    With room= and view=people, the people chart's answer instead (see people_view). 503 while MySQL is offline."""
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    if room and room not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=room[:32]))
    if view and not room:
        raise HTTPException(422, "view=people needs room=")
    now = int(time.time())
    minutes = max(1, min(minutes, HISTORY_MAX_MIN))
    key = (minutes, room, view)
    hit = _history_cache.get(key)
    if hit and now - hit["now"] < HISTORY_CACHE_S:  # every open dashboard asks for the same thing
        return hit
    if view:
        out = people_view(room, minutes, now)
    else:
        bucket = bucket_for(minutes, 1 if room else max(1, len(plan_rooms()) + len(config.room_names())))
        since = now - minutes * 60
        out = {"now": now, "bucket_s": bucket, "rooms": store.history(since, bucket, room or None)}
        if room:
            cold = store.coldest(room, since, bucket)
            out["waste"] = [ts for ts, peak in out["rooms"].get(room, [])
                            if peak == 0 and ts in cold and cold[ts] < energy.current(ts + bucket)["ac_on_below_c"]]
    health.mark("mysql", True)
    if len(_history_cache) > 64:
        _history_cache.clear()
    _history_cache[key] = out
    return out


UPTIME_CACHE_S = 20
_uptime_cache = {}
_uptime_lock = threading.Lock()


def uptime_today(now, gaps, known, stale=None):
    """Sensor uptime for today (Malaysia time) from store.report_gaps: per room, the time its sensor was reporting out
    of the time since its first report today. Offline time is every gap between two reports longer than STALE_S, and
    the time since the last report once that is longer than STALE_S: the rule that marks a sensor offline on the
    dashboard, so the figure drops exactly when the dashboard says "offline". A room that reported on an earlier day
    and not at all today has been offline since midnight: all of today counts against it. known: the rooms' live
    state (store.rooms), or None while it cannot be read. pct is None while there is nothing to judge."""
    stale = STALE_S if stale is None else stale
    since = timeutil.midnight(now)
    rooms = {}
    for room_id, (first, last, down) in gaps.items():
        expected = now - first
        if expected <= 0:
            continue
        tail = now - last
        down += tail if tail > stale else 0
        rooms[room_id] = {"first_ts": first, "up_s": max(0, expected - down), "expected_s": expected}
    for r in known or []:
        silent = r["room_id"] not in gaps and r["count_ts"] is not None and r["count_ts"] < since
        if silent and now > since:
            rooms[r["room_id"]] = {"first_ts": None, "up_s": 0, "expected_s": now - since}
    up, expected = sum(r["up_s"] for r in rooms.values()), sum(r["expected_s"] for r in rooms.values())
    return {"now": now, "since": since, "stale_s": stale, "rooms": rooms,
            "pct": round(100 * up / expected, 2) if expected else None}


@app.get("/api/uptime", dependencies=VIEWER)
def api_uptime():
    """Sensor uptime today, for the overview's "today so far" strip (see uptime_today). Read only. 503 while MySQL is
    offline. MySQL sees at most one query per UPTIME_CACHE_S, however many dashboards are open, and one at a time: a
    burst of requests at the moment the cache expires is one query, and when that query fails the requests queued
    behind it are told "offline" at once instead of each waiting for MySQL in turn."""
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    hit = _uptime_cache.get("today")
    if hit and 0 <= now - hit["now"] < UPTIME_CACHE_S:
        return hit
    with _uptime_lock:
        hit = _uptime_cache.get("today")
        if hit and 0 <= now - hit["now"] < UPTIME_CACHE_S:
            return hit
        if not health.should_try("mysql"):
            raise HTTPException(503, t("api.mysql_offline"))
        try:
            gaps = store.report_gaps(timeutil.midnight(now), STALE_S)
        except store.MYSQL_ERRORS:
            health.mark("mysql", False)  # before the lock is released, so the queue behind does not repeat the wait
            raise
        health.mark("mysql", True)
        try:
            known = store.rooms()
        except store.REDIS_ERRORS:
            known = None
        out = _uptime_cache["today"] = uptime_today(now, gaps, known)
        return out


@app.get("/api/rooms/{room_id}/climate", dependencies=VIEWER)
def api_room_climate(room_id: str, minutes: int = 60):
    """Temperature and humidity of one room over the last N minutes (up to 7 days), for the room drawer."""
    if room_id not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=room_id[:32]))
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    minutes = max(1, min(minutes, HISTORY_MAX_MIN))
    points = store.climate_history(room_id, now - minutes * 60, bucket_for(minutes))
    health.mark("mysql", True)
    return {"now": now, "room_id": room_id, "points": points}


SIGNAL_MAX_MIN = 60
SIGNAL_CACHE_S = 2
SIGNAL_CACHE_ROOMS = 256  # far more rooms than a plan has: the cache cannot grow without limit
_signal_cache = {}        # room_id -> (monotonic time, the room's rows of the last SIGNAL_MAX_MIN minutes)
_signal_lock = threading.Lock()


def simulator_ids():
    return {os.getenv("SIM_DEVICE_ID", "nadi-sim"), "sim-local"}


def signal_rows(room_id, now):
    """A room's stored CSI reports of the last SIGNAL_MAX_MIN minutes, read from MySQL at most once per
    SIGNAL_CACHE_S per room, however many dashboards ask, however often and for whatever window. The window asked
    for is cut from these rows, so changing "minutes" on every request cannot get past the cache, and one query at a
    time runs (the lock) so a burst of requests at the moment the cache expires is still one query. When that query
    fails, the requests queued behind it are told "offline" at once instead of each waiting for MySQL in turn."""
    hit = _signal_cache.get(room_id)
    if hit and time.monotonic() - hit[0] < SIGNAL_CACHE_S:
        return hit[1]
    with _signal_lock:
        hit = _signal_cache.get(room_id)
        if hit and time.monotonic() - hit[0] < SIGNAL_CACHE_S:
            return hit[1]
        if not health.should_try("mysql"):
            raise HTTPException(503, t("api.mysql_offline"))
        skip = () if demo.enabled() else tuple(sorted(simulator_ids()))
        try:
            rows = store.signal_history(room_id, now - SIGNAL_MAX_MIN * 60, skip)
        except store.MYSQL_ERRORS:
            health.mark("mysql", False)  # before the lock is released, so the queue behind does not repeat the wait
            raise
        health.mark("mysql", True)
        if len(_signal_cache) >= SIGNAL_CACHE_ROOMS:
            _signal_cache.clear()
        _signal_cache[room_id] = (time.monotonic(), rows)
        return rows


@app.get("/api/rooms/{room_id}/signal", dependencies=VIEWER)
def api_room_signal(room_id: str, minutes: int = 5):
    """The motion figure (motion_std) of one room's stored CSI reports over the last N minutes (1 to 60), with the
    headcount each report was given, for the live signal chart. threshold: the "occupied above" line, only while the
    threshold rule is counting (None when a trained model is). Simulator reports are left out unless the demo
    scenario is on. Read only. 503 while MySQL is offline.
    Load: counted against the per-IP "read" limit like /api/rooms (the room panel polls it every 5 s; the overview asks GET /api/signals once for all rooms),
    and MySQL sees at most one query per room per SIGNAL_CACHE_S in total (signal_rows)."""
    if room_id not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=room_id[:32]))
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    minutes = max(1, min(minutes, SIGNAL_MAX_MIN))
    rows = [r for r in signal_rows(room_id, now) if r[0] >= now - minutes * 60]
    return {"now": now, "room_id": room_id, "minutes": minutes,
            "threshold": logic.THRESHOLDS[0] if model.load() is None else None,
            "points": [{"ts": ts, "motion_std": round(std, 4), "headcount": count} for ts, std, count in rows],
            "last_report_ts": rows[-1][0] if rows else None}


SIGNALS_MAX_MIN = 10
SIGNALS_MAX_ROOMS = 64
_signals_cache = {}       # "all" -> (monotonic time, {room_id: rows of the last SIGNALS_MAX_MIN minutes})
_signals_lock = threading.Lock()


def signals_rows(now):
    """Every room's stored CSI reports of the last SIGNALS_MAX_MIN minutes, from ONE MySQL query at most once per
    SIGNAL_CACHE_S, however many rooms there are and however many dashboards ask (same pattern as signal_rows)."""
    hit = _signals_cache.get("all")
    if hit and time.monotonic() - hit[0] < SIGNAL_CACHE_S:
        return hit[1]
    with _signals_lock:
        hit = _signals_cache.get("all")
        if hit and time.monotonic() - hit[0] < SIGNAL_CACHE_S:
            return hit[1]
        if not health.should_try("mysql"):
            raise HTTPException(503, t("api.mysql_offline"))
        skip = () if demo.enabled() else tuple(sorted(simulator_ids()))
        try:
            rows = store.signals_history(now - SIGNALS_MAX_MIN * 60, skip)
        except store.MYSQL_ERRORS:
            health.mark("mysql", False)  # before the lock is released, so the queue behind does not repeat the wait
            raise
        health.mark("mysql", True)
        _signals_cache["all"] = (time.monotonic(), rows)
        return rows


@app.get("/api/signals", dependencies=VIEWER)
def api_signals(minutes: int = 5):
    """The motion figure of EVERY Wi-Fi sensing room over the last N minutes (1 to 10) in one answer: the overview
    asks this once per poll instead of once per room, so its load does not grow with the number of rooms. Each room
    has the same shape as GET /api/rooms/{id}/signal. At most SIGNALS_MAX_ROOMS rooms ("truncated" says when rooms
    were left out). Read only, the per-IP "read" limit. 503 while MySQL is offline."""
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    minutes = max(1, min(minutes, SIGNALS_MAX_MIN))
    threshold = logic.THRESHOLDS[0] if model.load() is None else None
    known = validate.known_rooms()
    every = {room_id: rows for room_id, rows in sorted(signals_rows(now).items()) if room_id in known}
    rooms = {}
    for room_id, all_rows in list(every.items())[:SIGNALS_MAX_ROOMS]:
        rows = [r for r in all_rows if r[0] >= now - minutes * 60]
        rooms[room_id] = {"now": now, "room_id": room_id, "minutes": minutes, "threshold": threshold,
                          "points": [{"ts": ts, "motion_std": round(std, 4), "headcount": count} for ts, std, count in rows],
                          "last_report_ts": rows[-1][0] if rows else None}
    return {"now": now, "minutes": minutes, "threshold": threshold, "rooms": rooms,
            "truncated": len(every) > SIGNALS_MAX_ROOMS}


DETECTOR_CACHE_S = 10
DETECTOR_MAX_ROOMS = 20
MODEL_FACTS = ("framework", "platform", "trained_on", "accuracy", "threshold_accuracy", "trained_at", "n_train", "n_test")
_detector_cache = {}
_detector_lock = threading.Lock()


def label_segments():
    """{room_id: [(start_ts, end_ts or None, headcount), ...]} from the labels file; rows that do not parse are skipped."""
    return labels.segments()


def labelled_points(now):
    """{room_id: [{"ts", "headcount_label", "motion_std"}, ...]}: each stored CSI report that falls inside a label
    segment of its room, with that label. Same matching as scripts/calibrate.py (start <= ts <= end, an open segment
    runs until now, the first segment that fits wins). Reports from the simulator or with no known device never count."""
    sims = simulator_ids()
    known = validate.known_rooms()
    out = {}
    for room_id, segs in sorted(label_segments().items()):
        if room_id not in known or len(out) >= DETECTOR_MAX_ROOMS:
            continue
        points = []
        for ts, std, src in store.labelled_reports(room_id, min(s[0] for s in segs), max(s[1] or now for s in segs)):
            if not src or src in sims:
                continue
            for start, end, count in segs:
                if start <= ts <= (end or now):
                    points.append({"ts": ts, "headcount_label": count, "motion_std": round(std, 4)})
                    break
        out[room_id] = points
    return out


def model_facts(active):
    """What the trained model's file says about itself (the fields ml/train.py writes), plus whether it is the one
    counting now. With the threshold rule counting, the facts are those of the model file in the repo, if there is one."""
    m = active
    if m is None:
        try:
            m = json.loads(model.DEFAULT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if not isinstance(m, dict):
        return None
    return {**{k: m.get(k) for k in MODEL_FACTS}, "active": active is not None}


def detector_summary():
    """What is counting people right now, without the labelled reports: mode ("rule" or "model"), the threshold in
    rule mode, and the model file's own facts (None when there is no file). Read only; part of GET /api/info, so the
    overview can name the live detector and the true state of the model to every viewer."""
    active = model.load()
    return {"mode": "rule" if active is None else "model", "threshold": logic.THRESHOLDS[0] if active is None else None,
            "model": model_facts(active)}


@app.get("/api/detector", dependencies=[Depends(require_admin)])
def api_detector():
    """What is counting people right now, for the calibration page. mode: "rule" (the calibrated threshold) or
    "model" (a trained model file is loaded). threshold: the "occupied above" line, in rule mode only. rooms: the
    labelled reports per room (labelled_points). model: the model file's own facts, or None when there is no file.
    Read only, admin only (it reads the labels, like /api/labels), the per-IP "read" limit. 503 while MySQL is
    offline. MySQL sees at most one query per labelled room per DETECTOR_CACHE_S, one request at a time."""
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    hit = _detector_cache.get("rooms")
    if not (hit and 0 <= now - hit[0] < DETECTOR_CACHE_S):
        with _detector_lock:
            hit = _detector_cache.get("rooms")
            if not (hit and 0 <= now - hit[0] < DETECTOR_CACHE_S):
                if not health.should_try("mysql"):
                    raise HTTPException(503, t("api.mysql_offline"))
                try:
                    hit = _detector_cache["rooms"] = (now, labelled_points(now))
                except store.MYSQL_ERRORS:
                    health.mark("mysql", False)  # before the lock is released, so the queue behind does not repeat the wait
                    raise
                health.mark("mysql", True)
    active = model.load()
    return {"now": now, "mode": "rule" if active is None else "model",
            "threshold": logic.THRESHOLDS[0] if active is None else None,
            "report_interval_s": REPORT_INTERVAL_S, "rooms": hit[1], "model": model_facts(active)}


CO2_KG_PER_KWH = energy.CO2_KG_PER_KWH  # the default grid emission factor, until an admin saves another one


ENERGY_RANGES = {"today": 1, "7d": 7, "30d": 30}
FIRST_REPORT_CACHE_S = 60
_first_report = {"at": -1e9, "ts": None, "known": False}


def first_report(now):
    """(known, ts): the first report still in the history, read at most once a minute. known is False while MySQL is
    offline (then no day is left out)."""
    if time.monotonic() - _first_report["at"] >= FIRST_REPORT_CACHE_S:
        _first_report["at"] = time.monotonic()
        if health.should_try("mysql"):
            try:
                _first_report.update(ts=store.first_report_ts(), known=True)
                health.mark("mysql", True)
            except store.MYSQL_ERRORS:
                health.mark("mysql", False)
                _first_report["known"] = False
    return _first_report["known"], _first_report["ts"]


def energy_range(now, rng, ids, names, ongoing_since, day, room=None):
    """The Energy page's chosen period: totals in RM, kWh and CO2, the same for the period of the same length before
    (None when nothing was reported before this period began), RM, kWh and hours per room, and RM per hour (today)
    or per day: of the building, or of `room` when one is given ("series_room" names it).
    A stretch counts in full on the day it ended, as the day totals always have; the hour chart puts each part in the
    hour it ran. Days or hours before the first report are None (nothing to show), later ones without waste 0."""
    n = ENERGY_RANGES[rng]
    zero = {"rm": 0.0, "kwh": 0.0, "co2_kg": 0.0}
    known, first = first_report(now)
    start = timeutil.midnight(now) - (n - 1) * 86400
    before_first = (lambda end: known and (first is None or end <= first))
    ongoing = {room_id: energy.cost(since, now, room_id) for room_id, since in ongoing_since.items()}

    def total(days_ago_list, with_ongoing):
        parts = [day(d) for d in days_ago_list] + (list(ongoing.values()) if with_ongoing else [])
        return {k: sum(p[k] for p in parts) for k in zero}

    def shown(a):
        return {"rm": round(a["rm"], 2), "kwh": round(a["kwh"], 1), "co2_kg": round(a["co2_kg"], 1)}

    current = total(range(n), True)
    previous = None if before_first(start) else shown(total(range(n, 2 * n), False))
    try:
        per_room = energy.room_days(now, n, ids)
    except store.REDIS_ERRORS:
        per_room = {}
    by_room = []
    for room_id in ids:
        ended, running = per_room.get(room_id, {"rm": 0.0, "kwh": 0.0, "hours": 0.0}), ongoing.get(room_id, zero)
        since = ongoing_since.get(room_id)
        by_room.append({"room_id": room_id, "name": config.room_name(room_id, names),
                        "rm": round(ended["rm"] + running["rm"], 2), "kwh": round(ended["kwh"] + running["kwh"], 1),
                        "hours": round(ended["hours"] + ((now - since) / 3600 if since is not None else 0.0), 1)})
    mine = {k: v for k, v in ongoing.items() if room is None or k == room}  # the stretches still running that count
    if rng == "today":
        try:
            hours = store.waste_hours(now, room)
        except store.REDIS_ERRORS:
            hours = [0.0] * 24
        midnight = timeutil.midnight(now)
        for room_id, a in ongoing_since.items():
            if room is not None and room_id != room:
                continue
            for ts, rm in energy.hour_pieces(max(a, midnight), now, room_id):
                hours[(int(ts) - midnight) // 3600] += rm
        points = []
        for h in range(24):
            ts = midnight + h * 3600
            empty = ts > now or before_first(ts + 3600)
            points.append({"ts": ts, "rm": None if empty else round(hours[h], 2)})
        series = {"unit": "hour", "points": points}
    else:
        points = []
        for d in range(n - 1, -1, -1):
            ts = timeutil.midnight(now - d * 86400)
            rm = None if before_first(ts + 86400) else day(d, room)["rm"] + (sum(o["rm"] for o in mine.values()) if d == 0 else 0.0)
            points.append({"day": timeutil.day(ts), "rm": None if rm is None else round(rm, 2)})
        series = {"unit": "day", "points": points}
    return {"id": rng, "days": n, "total": shown(current), "previous": previous, "by_room": by_room, "series": series,
            "series_room": room, "first_ts": first if known else None}


@app.get("/api/energy", dependencies=VIEWER)
def api_energy(rng: str = Query("7d", alias="range", pattern="^(today|7d|30d)$"), room: str = ""):
    """Air conditioning waste: today and the last 7 days, per room and per day, in RM, kWh and an estimated CO2,
    and in "range" the period chosen on the Energy page (today, 7d or 30d) set against the period before it.
    Every stretch was costed at the tariff, power and CO2 factor in force while it ran (server/energy.py), so a
    changed rate never restates earlier days. rate_changes lists the saves of the last 14 days."""
    if room and room not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=room[:32]))
    now = int(time.time())
    stale = refresh_live(now)
    rooms = room_views(now, _last["rooms"] or [])
    ongoing = {r["room_id"]: energy.cost(r["waste"]["since"], now, r["room_id"]) for r in rooms if r["waste"]}
    names = config.room_names()
    ids = sorted(set(plan_rooms()) | {r["room_id"] for r in rooms})
    zero = {"rm": 0.0, "kwh": 0.0, "co2_kg": 0.0}

    def day(days_ago, room_id=None):
        try:
            return energy.day_amounts(now, days_ago, room_id)
        except store.REDIS_ERRORS:
            return dict(zero)

    def add(*parts):
        return {k: sum(p[k] for p in parts) for k in zero}

    def shown(a):
        return {"rm": round(a["rm"], 2), "kwh": round(a["kwh"], 1), "co2_kg": round(a["co2_kg"], 1)}

    by_room = []
    for room_id in ids:
        today = round(day(0, room_id)["rm"] + ongoing.get(room_id, zero)["rm"], 2)
        week = round(today + sum(day(d, room_id)["rm"] for d in range(1, 7)), 2)
        by_room.append({"room_id": room_id, "name": config.room_name(room_id, names), "rm_today": today, "rm_week": week})
    days = [add(day(d), *(ongoing.values() if d == 0 else ())) for d in range(6, -1, -1)]  # oldest first, today last
    daily = [{"day": timeutil.day(now - d * 86400), "rm": round(a["rm"], 2)} for d, a in zip(range(6, -1, -1), days)]
    live = energy.current(now)
    return {"now": now, "today": shown(days[-1]), "week": shown(add(*days)),
            "previous_week": shown(add(*(day(d) for d in range(7, 14)))),
            "yesterday": shown(days[-2]), "by_room": by_room, "daily": daily,
            "tariff_rm_per_kwh": live["tariff_rm_per_kwh"], "ac_kw": live["ac_kw"], "co2_kg_per_kwh": live["co2_kg_per_kwh"],
            "rate_changes": energy.rate_changes(now), "stale_ts": stale,
            "range": energy_range(now, rng, ids, names, {r["room_id"]: r["waste"]["since"] for r in rooms if r["waste"]}, day,
                                  room or None)}


@app.get("/api/energy/settings", dependencies=VIEWER)
def api_energy_settings():
    """The energy settings in force (tariff, air conditioner power, the temperature that counts as on, the waste
    delay, the CO2 factor), where they come from ("database", "defaults" from the server configuration, or
    "last_known" while MySQL is offline), the allowed range of each, and the change history, newest first."""
    return energy.view(int(time.time()))


@app.put("/api/energy/settings")
def api_energy_settings_save(request: Request, body: dict = Body(...), lang: str = "en", who: str = Depends(require_admin)):
    """An admin saves the energy settings. All six fields are required and checked against their ranges; the new
    values apply from this second and earlier figures keep the earlier values. Audit-logged with old and new values.
    422 with a message per field, 503 while MySQL is offline (a change that cannot be stored is refused)."""
    lang = "ms" if lang == "ms" else "en"
    settings, errors = energy.check(body, validate.known_rooms(), lang, config.display_names())
    if errors:
        return JSONResponse({"detail": " ".join(errors.values()), "errors": errors}, status_code=422)
    now = int(time.time())
    try:
        diff = energy.save(settings, who, now)
    except energy.Offline:
        raise HTTPException(503, t("es.err_offline", lang))
    if diff:
        try:  # the stored version itself records who and when; a missing audit line must not undo a saved change
            store.audit({"ts": now, "action": "energy_settings", "by": who, "ip": client_ip(request), "changes": diff})
        except store.REDIS_ERRORS:
            health.mark("redis", False)
        _rooms_cache.clear()
    return {"ok": True, "changed": bool(diff), **energy.view(now)}


@app.get("/api/summary", dependencies=VIEWER)
def api_summary(minutes: int = 60):
    """Key figures for the overview tiles, this period against the one before it: average and peak people,
    alerts raised. 503 while MySQL is offline."""
    if not health.should_try("mysql"):
        raise HTTPException(503, t("api.mysql_offline"))
    now = int(time.time())
    minutes = max(5, min(minutes, HISTORY_MAX_MIN))
    span = minutes * 60
    bucket = max(REPORT_INTERVAL_S, span // HISTORY_POINTS)
    series = store.history(now - 2 * span, bucket)
    health.mark("mysql", True)

    def people(start, end):
        totals = {}
        for points in series.values():
            for ts, n in points:
                if start <= ts < end:
                    totals[ts] = totals.get(ts, 0.0) + n
        vals = list(totals.values())
        return {"avg": round(sum(vals) / len(vals), 1) if vals else None, "peak": round(max(vals), 1) if vals else None}

    try:
        kept = alerts.recent(limit=alerts.KEEP)
    except store.REDIS_ERRORS:
        kept = []

    def count(start, end):
        return sum(1 for a in kept if start <= a["ts"] < end)

    cur, prev = people(now - span, now + 1), people(now - 2 * span, now - span)
    return {"now": now, "minutes": minutes,
            "people_avg": cur["avg"], "people_avg_prev": prev["avg"],
            "people_peak": cur["peak"], "people_peak_prev": prev["peak"],
            "alerts": count(now - span, now + 1), "alerts_prev": count(now - 2 * span, now - span)}


@app.get("/api/alerts", dependencies=VIEWER)
def api_alerts(lang: str = "en", limit: int = 50, offset: int = 0):
    """The kept alerts (up to 200), newest first, a page at a time (limit up to 100). No IP addresses."""
    lang = "ms" if lang == "ms" else "en"
    limit, offset = max(1, min(limit, 100)), max(0, min(offset, alerts.KEEP))
    try:
        kept = alerts.recent(lang, limit=alerts.KEEP)
        return {"alerts": kept[offset:offset + limit], "total": len(kept), "limit": limit, "offset": offset}
    except store.REDIS_ERRORS:
        health.mark("redis", False)
        raise HTTPException(503, t("api.redis_offline"))


@app.post("/api/alerts/{alert_id}/ack")
def api_alert_ack(alert_id: str, who: str = Depends(require_admin)):
    """An admin has seen this alert; every screen shows who and when."""
    if not alerts.acknowledge(alert_id, who, int(time.time())):
        raise HTTPException(404, t("api.alert_unknown"))
    return {"ok": True, "id": alert_id, "by": who}


@app.get("/api/me")
def api_me(request: Request, x_admin_token: str = Header(""), x_viewer_token: str = Header("")):
    """Whether this caller may read the dashboard and use admin features, without raising. A wrong token counts
    towards the lockout here too (this is where the sign-in dialogs check a token), and during a lockout wrong tokens
    get status 429; a right token always works."""
    ip = client_ip(request)
    viewer = viewer_allowed(request, x_admin_token, x_viewer_token)
    out = {"viewer": viewer, "viewer_required": bool(os.getenv("VIEWER_TOKEN", "")), "rule": admin_rule()}
    label = token_label(x_admin_token) if x_admin_token and admin_tokens() else None
    if label:
        return {**out, "admin": True, "who": label}
    viewer_token = os.getenv("VIEWER_TOKEN", "")
    wrong = (bool(x_admin_token) or
             bool(x_viewer_token and viewer_token and not hmac.compare_digest(x_viewer_token.encode(), viewer_token.encode())))
    if wrong:
        if guard.locked(ip):
            return {**out, "admin": False, "who": None, "status": 429}
        guard.failed(ip)
    if security.is_local_admin(request) and not (not admin_tokens() and tokens_configured()):
        return {**out, "admin": True, "who": "localhost"}
    return {**out, "admin": False, "who": None,
            "status": 503 if (not admin_tokens() and tokens_configured()) else 401 if admin_tokens() else 403}


def _timed(check, timeout=2):
    """Run check with a hard timeout; return False on timeout or any error."""
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(check)
    try:
        return bool(fut.result(timeout=timeout))
    except Exception:
        return False
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


@app.get("/api/health", dependencies=VIEWER)
def api_health():
    """Liveness of Redis, MySQL and the MQTT broker. Never returns secrets."""
    redis_ok = _timed(_check_redis)
    mysql_ok = _timed(_check_mysql)
    mqtt_ok = _timed(_check_mqtt)
    ok = redis_ok and mysql_ok and mqtt_ok
    return {"status": "ok" if ok else "degraded", "mode": config.mode(),
            "redis": redis_ok, "mysql": mysql_ok, "mqtt": mqtt_ok}


def built_with(lang="en"):
    """Only what is actually in use right now, for the dashboard footer."""
    def local(host_var, default="127.0.0.1"):
        return os.getenv(host_var, default) in LOCAL_HOSTS

    items = ["FastAPI"]
    if config.is_huawei():
        try:
            if store.iotda_push_recent():
                items.append(t("built.iotda", lang))
        except store.REDIS_ERRORS:
            pass
        items.append(t("built.redis_local", lang) if local("REDIS_HOST") else t("built.dcs", lang))
        items.append(t("built.mysql_local", lang) if local("MYSQL_HOST") else t("built.rds", lang))
        if os.getenv("ECS_PUBLIC_IP"):
            items.append(t("built.ecs", lang))
    else:
        items += [t("built.mosquitto", lang), t("built.redis_local", lang), t("built.mysql_local", lang)]
    m = model.info()
    if m:
        key = "built.model_modelarts" if m.get("platform") == "modelarts" else "built.model_local"
        kinds = {"synthetic": "built.data_synthetic", "real CSI": "built.data_real", "mixed real + synthetic": "built.data_mixed"}
        data = m.get("trained_on")  # written by ml/train.py data_kind(), shown in the dashboard language
        data = t(kinds[data], lang) if data in kinds else data
        items.append(t(key, lang, framework=m.get("framework", "MindSpore"), data=data))
    else:
        items.append(t("built.threshold", lang))
    label = chat.label_now(lang)
    if label != t("model.builtin", lang):
        items.append(label)
    items.append(t("built.smn", lang) if alerts.smn_enabled() else t("built.console", lang))
    return items


def admin_rule():
    """How admin features are protected, for the header: tokens, this computer only, or refused."""
    if admin_tokens() or tokens_configured():
        return "token"
    return "localhost" if security.localhost_admin_enabled() else "refused"


@app.get("/api/info", dependencies=VIEWER)
def api_info(lang: str = "en"):
    """lang=ms gives the "Built with" badges and model label in Malay."""
    lang = "ms" if lang == "ms" else "en"
    return {"mode": config.mode(), "built_with": built_with(lang), "chat_model": chat.label_now(lang),
            "chat_source": chat.source_now(), "building": config.building_name(), "level": config.level_name(),
            "room_names": config.display_names(), "admin": admin_rule(),
            # every room drawn on a real floor: its floor, and its nearest exit in the page language
            "room_floors": {room_id: room["floor"] for room_id, room in PLAN["rooms"].items()},
            "room_exits": {room_id: exit_name(room_id, lang) for room_id in PLAN["rooms"]},
            "headcount_source": "mindspore" if model.info() else "threshold", "detector": detector_summary(),
            "waste_minutes": energy.waste_after_s() / 60, "ac_on_below_c": energy.current()["ac_on_below_c"],
            "demo": demo.status()["on"],
            "emergency_number": incident.emergency_number(), "timezone": timeutil.TZ_NAME}


class EmergencyBody(BaseModel):
    on: StrictBool  # "false" as text must not start an alarm
    drill: StrictBool = False  # a practice run: same screens, alerts marked DRILL, kept apart in the history


class ChatBody(BaseModel):
    question: str = ""
    lang: str = "en"
    # the floor the chat panel's chip has chosen; empty or missing: the whole building
    floor: str | None = Field(default=None, max_length=32)


@app.post("/api/emergency")
def api_emergency(body: EmergencyBody, request: Request, who: str = Depends(require_admin)):
    """{"on": true} starts the alarm view (and alerts once), {"on": true, "drill": true} starts a drill, {"on": false}
    ends either. Safe to repeat: a second start keeps the first start time and kind, a second end does nothing.
    Who did it is kept in the audit log and the alerts."""
    rate_limit("emergency", request, guard.EMERGENCY_PER_MIN)
    return set_emergency(body.on, who, client_ip(request), drill=body.drill)


def set_emergency(on, who, ip, drill=False):
    """Start or end emergency mode or a drill (the API and the demo scenario both use this). Starting keeps an
    incident record and saves the first snapshot at once; ending writes the incident or drill report.
    Returns the emergency state."""
    now = int(time.time())
    kind = "drill" if drill else "real"
    incident_id = incident.new_id(now, kind) if on else None
    if on and store.start_emergency(now, who, kind, incident_id):
        store.audit({"ts": now, "action": "start", "by": who, "ip": ip, "drill": drill, "incident": incident_id})
        views = room_views(now)
        incident.begin(incident_id, kind, now, who, views)
        live = [r for r in views if r["live"] and r["headcount"] is not None]
        unknown = [r for r in views if not (r["live"] and r["headcount"] is not None)]
        total = sum(r["headcount"] for r in live)
        plus = any(logic.is_lower_bound(r) for r in live) or bool(unknown)
        rooms = ", ".join(f"{r['name']}: {logic.shown(r['headcount'], logic.is_lower_bound(r))}"
                          for r in sorted(live, key=lambda r: -r["headcount"]))
        body = "alert.emergency_body_unknown" if unknown else \
            "alert.emergency_body_plus" if plus else "alert.emergency_body"
        alerts.send("drill" if drill else "emergency", "alert.emergency_subject", body, drill=drill, total=total,
                    rooms=rooms, n=len(unknown), unknown=", ".join(r["name"] for r in unknown))
        alerts.send("info", "alert.audit_start_subject", "alert.audit_body", drill=drill, who=who,
                    time=timeutil.clock(now))  # IP: audit log only
        _rooms_cache.clear()
        save_snapshot(store.emergency(), views, now)  # at once: it exists even if this computer goes down next
    elif not on:
        ended = store.end_emergency()
        if ended:
            was_drill = ended.get("kind") == "drill"
            store.audit({"ts": now, "action": "end", "by": who, "ip": ip, "started": int(ended["since"]),
                         "drill": was_drill, "incident": ended.get("id") or None})
            alerts.send("info", "alert.audit_end_subject", "alert.audit_body", drill=was_drill, who=who,
                        time=timeutil.clock(now))
            _rooms_cache.clear()
            if ended.get("id"):
                try:
                    incident.finish(ended["id"], now, who, room_views(now))
                except store.REDIS_ERRORS[0]:
                    raise
                except Exception as e:  # the alarm is off either way; the report is what failed
                    print(f"incident report not written: {e}", flush=True)
    return store.emergency()


class RoomStatusBody(BaseModel):
    status: Literal["clear", "help"] | None = None  # None removes the mark


@app.post("/api/emergency/rooms/{room_id}")
def api_room_status(room_id: str, body: RoomStatusBody, request: Request, who: str = Depends(require_admin)):
    """A warden marks a room during an emergency or drill: "clear" (searched, nobody inside) or "help" (people still
    inside, need help). Shown on every screen and the export, kept in the report, audit-logged. 409 when no emergency
    or drill is on: marks belong to one incident and start empty with the next."""
    em = store.emergency()
    if not em["on"] or not em["id"]:
        raise HTTPException(409, t("api.no_emergency"))
    if room_id not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=room_id[:32]))
    now = int(time.time())
    incident.set_status(em["id"], room_id, body.status, who, now)
    store.audit({"ts": now, "action": f"room_{body.status or 'reset'}", "room": room_id, "by": who,
                 "ip": client_ip(request), "drill": em["drill"], "incident": em["id"]})
    _rooms_cache.clear()
    return {"accountability": incident.statuses(em["id"])}


def editor_on():
    """PLAN_EDITOR=off hides the floor plan editor and refuses its write endpoints (404)."""
    return os.getenv("PLAN_EDITOR", "on").strip().lower() not in ("off", "0", "false", "no")


def floor_or_404(floor_id):
    try:
        return site.floor_info(floor_id)
    except site.NotFound:
        raise HTTPException(404, t("api.floor_unknown", floor=str(floor_id)[:32]))


@app.get("/api/site", dependencies=VIEWER)
def api_site(lang: str = "en"):
    """Buildings and their floors (rooms on each floor, current plan version), the floor shown first, and whether the
    plan editor is on. The example building is marked "example": true and named in lang (en or ms)."""
    return site.summary(editor_on(), "ms" if lang == "ms" else "en")


@app.get("/api/floors/{floor_id}/plan", dependencies=VIEWER)
def api_floor_plan(floor_id: str, lang: str = "en"):
    """A floor's current plan: {"floor_id", "version", "saved_ts", "saved_by", "plan"}. 404 for an unknown floor.
    lang names the example building's rooms; names an admin typed are as written."""
    floor_or_404(floor_id)
    doc = site.plan(floor_id, "ms" if lang == "ms" else "en")
    plan_doc = doc["plan"]
    names = config.room_names()  # ROOM_NAMES wins over the name on the plan, as everywhere else on screen
    if names and not site.is_example(floor_id) and any(r in names for r in plan_doc.get("rooms", {})):
        plan_doc = {**plan_doc, "rooms": {r: ({**room, "name": names[r]} if r in names else room) for r, room in plan_doc["rooms"].items()}}
    return {"floor_id": doc["floor_id"], "version": doc["version"], "saved_ts": doc["saved_ts"], "saved_by": doc["saved_by"], "plan": plan_doc}


@app.get("/api/floors/{floor_id}/versions", dependencies=[Depends(require_admin)])
def api_floor_versions(floor_id: str):
    """Every stored version of a floor's plan, newest first (f1 ends with its built-in version 0). Admin only."""
    floor_or_404(floor_id)
    return {"floor_id": floor_id, "versions": site.versions(floor_id)}


def live_room_ids():
    """Rooms with a sensor reporting now: a plan save may not take one of them off its floor."""
    now = int(time.time())
    try:
        rooms = store.rooms()
    except store.REDIS_ERRORS:
        rooms = _last["rooms"] or []
    return {r["room_id"] for r in rooms if r.get("count_ts") is not None and now - r["count_ts"] <= STALE_S}


def editor_or_404():
    if not editor_on():
        raise HTTPException(404, t("api.not_found"))


def refused(errors, lang):
    out = site.messages(errors, lang)
    return JSONResponse({"detail": " ".join(e["message"] for e in out), "errors": out}, status_code=422)


def audit_quietly(entry):
    """The audit line of a change that is already stored: Valkey being offline must not turn it into an error."""
    try:
        store.audit(entry)
    except store.REDIS_ERRORS:
        health.mark("redis", False)


def site_changed():
    """After any write: the merged plan, known rooms and names follow, and every cache is fresh."""
    plan_view.refresh()
    _rooms_cache.clear()


class PlanBody(BaseModel):
    plan: dict
    note: str = ""
    base_version: StrictInt | None = None


class RestoreBody(BaseModel):
    version: StrictInt


class BuildingBody(BaseModel):
    name: str
    code: str = ""


class FloorBody(BaseModel):
    name: str
    level: StrictInt  # "2" as text is refused, not read as 2


class RenameBuildingBody(BaseModel):
    name: str
    code: str | None = None


class RenameFloorBody(BaseModel):
    name: str
    level: StrictInt | None = None


def site_write(fn, *args, lang="en"):
    """Run a site write and turn its refusals into answers: 404 unknown, 409 example building or a conflicting save,
    422 with every problem in the page language."""
    try:
        return fn(*args)
    except site.NotFound:
        raise HTTPException(404, t("api.floor_unknown", lang, floor=str(args[0])[:32]))
    except site.ReadOnly:
        raise HTTPException(409, t("site.err_example", lang))
    except site.Conflict:
        raise HTTPException(409, t("ed.conflict", lang))


@app.put("/api/floors/{floor_id}/plan")
def api_floor_plan_save(floor_id: str, body: PlanBody, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    """Save a floor's plan as its next version, after every drawing rule (server/site.py). base_version: the version
    the editor opened; 409 when someone saved in between. 422 lists every problem; nothing is stored then."""
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    floor_or_404(floor_id)
    before = site.plan(floor_id)["plan"]
    try:
        version = site_write(site.save_plan, floor_id, body.plan, who, body.note, body.base_version, live_room_ids(), None, lang, lang=lang)
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    entry = {"ts": int(time.time()), "action": "plan_save", "by": who, "ip": client_ip(request), "floor": floor_id,
             "version": version, "rooms": len(body.plan.get("rooms", {}))}
    capacity = site.capacity_changes(before, body.plan)
    if capacity:  # who changed a room's capacity, from what to what
        entry["capacity"] = capacity[:50]
    audit_quietly(entry)
    return {"ok": True, "floor_id": floor_id, "version": version}


@app.post("/api/floors/{floor_id}/restore")
def api_floor_restore(floor_id: str, body: RestoreBody, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    """Make an old version current again, as a new version (checked again against the floors as they are now)."""
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    floor_or_404(floor_id)
    try:
        version = site_write(site.restore, floor_id, body.version, who, live_room_ids(), lang, lang=lang)
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    audit_quietly({"ts": int(time.time()), "action": "plan_restore", "by": who, "ip": client_ip(request), "floor": floor_id,
                 "version": version, "from": body.version})
    return {"ok": True, "floor_id": floor_id, "version": version}


@app.post("/api/site/buildings")
def api_site_add_building(body: BuildingBody, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    """A new building with one empty floor."""
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    try:
        building_id, floor_id = site.add_building(body.name, body.code, t("site.level_n", lang, n=1))
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    audit_quietly({"ts": int(time.time()), "action": "site_add", "by": who, "ip": client_ip(request), "building": building_id,
                 "floor": floor_id, "name": body.name.strip()[:40]})
    return {"ok": True, "building_id": building_id, "floor_id": floor_id}


@app.post("/api/site/buildings/{building_id}/floors")
def api_site_add_floor(building_id: str, body: FloorBody, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    """A new, empty floor in a building."""
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    try:
        floor_id = site_write(site.add_floor, building_id, body.name, body.level, lang=lang)
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    audit_quietly({"ts": int(time.time()), "action": "site_add", "by": who, "ip": client_ip(request), "building": building_id,
                 "floor": floor_id, "name": body.name.strip()[:40]})
    return {"ok": True, "floor_id": floor_id}


@app.put("/api/site/buildings/{building_id}")
def api_site_rename_building(building_id: str, body: RenameBuildingBody, request: Request, lang: str = "en",
                             who: str = Depends(require_admin)):
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    try:
        site_write(site.rename_building, building_id, body.name, body.code, lang=lang)
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    audit_quietly({"ts": int(time.time()), "action": "site_rename", "by": who, "ip": client_ip(request), "building": building_id,
                 "name": body.name.strip()[:40]})
    return {"ok": True}


@app.put("/api/site/floors/{floor_id}")
def api_site_rename_floor(floor_id: str, body: RenameFloorBody, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    try:
        site_write(site.rename_floor, floor_id, body.name, body.level, lang=lang)
    except site.Invalid as e:
        return refused(e.errors, lang)
    site_changed()
    audit_quietly({"ts": int(time.time()), "action": "site_rename", "by": who, "ip": client_ip(request), "floor": floor_id,
                 "name": body.name.strip()[:40]})
    return {"ok": True}


@app.post("/api/floors/{floor_id}/image")
async def api_floor_image(floor_id: str, request: Request, lang: str = "en", who: str = Depends(require_admin)):
    """Upload a background for a floor's plan: the raw bytes of a PNG or JPEG (at most 2 MB, 64 to 4096 pixels a
    side). The type is decided by the bytes; the image is stored without its metadata, named by its SHA-256. The plan
    uses it once a plan that names it is saved."""
    editor_or_404()
    lang = "ms" if lang == "ms" else "en"
    floor_or_404(floor_id)
    if site.is_example(floor_id):
        raise HTTPException(409, t("site.err_example", lang))
    try:
        cleaned, ext, width, height = upload.clean(await request.body())
    except upload.Refused as e:
        return refused([{"key": e.key, "values": {}}], lang)
    name = site.store_image(cleaned, ext)
    audit_quietly({"ts": int(time.time()), "action": "plan_image", "by": who, "ip": client_ip(request), "floor": floor_id,
                 "image": name})
    return {"image": name, "width": width, "height": height}


@app.get("/api/site/images/{name}", dependencies=VIEWER)
def api_site_image(name: str):
    """An uploaded floor plan background. Only names the server gave out (SHA-256 + .png/.jpg); served as an image
    that can never be read as a page or a script."""
    path = site.image_path(name)
    if path is None:
        raise HTTPException(404, t("api.not_found"))
    return FileResponse(path, media_type="image/png" if name.endswith(".png") else "image/jpeg",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'",
                                 "Cache-Control": "private, max-age=86400, immutable"})


@app.get("/api/incidents", dependencies=VIEWER)
def api_incidents():
    """Reports of past emergencies and drills, newest first, and the one running now (if any) with its snapshots."""
    em = store.emergency()
    active = None
    if em["on"] and em["id"]:
        snaps = [int(x) for x in store.r.lrange(f"incident:{em['id']}:snaps", 0, -1)]
        active = {"id": em["id"], "drill": em["drill"], "since": em["since"], "snapshots": len(snaps),
                  "last_snapshot": snaps[-1] if snaps else None}
    return {"incidents": incident.reports(), "active": active}


@app.get("/api/incidents/{incident_id}", dependencies=VIEWER)
def api_incident(incident_id: str, lang: str = "en"):
    """One report, with its alerts in the dashboard language and who acknowledged them."""
    rep = incident.report(incident_id)
    if rep is None:
        raise HTTPException(404, t("api.incident_unknown"))
    lang = "ms" if lang == "ms" else "en"
    shown = []
    for a in rep.get("alerts", []):
        subject, message = alerts.render(a, lang)
        kind = a.get("kind", "info")
        shown.append({"id": a.get("id"), "ts": a.get("ts"), "kind": kind,
                      "severity": a.get("severity") or alerts.SEVERITY.get(kind, "info"),
                      "subject": subject, "message": message, "ack": a.get("ack")})
    return {**rep, "alerts": shown}


@app.get("/api/incidents/{incident_id}/snapshot", dependencies=VIEWER, response_class=HTMLResponse)
def api_incident_snapshot(incident_id: str, ts: str = "latest", lang: str = "en"):
    """A saved snapshot page (the latest, or one by its time), exactly as written to disk."""
    path = incident.snapshot_file(incident_id, ts, lang)
    if path is None:
        raise HTTPException(404, t("api.incident_unknown"))
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


class DeleteBody(BaseModel):
    confirm: str = ""


@app.post("/api/data/delete")
def api_delete_all(body: DeleteBody, request: Request, who: str = Depends(require_admin)):
    """Delete every reading, label, alert, audit entry, report and snapshot (PDPA request, see PRIVACY.md).
    The body must carry the typed confirmation "DELETE ALL DATA". Refused during an emergency or drill.
    One audit entry remains afterwards: who deleted everything, and when."""
    rate_limit("emergency", request, guard.EMERGENCY_PER_MIN)
    try:
        out = privacy.delete_all(body.confirm)
    except privacy.Refused as e:
        if str(e) == "emergency":
            raise HTTPException(409, t("api.delete_emergency"))
        raise HTTPException(422, t("api.delete_confirm", phrase=privacy.CONFIRM))
    now = int(time.time())
    store.audit({"ts": now, "action": "delete_all", "by": who, "ip": client_ip(request)})
    print(f"all stored data deleted by {who}: {out}", flush=True)
    _rooms_cache.clear()
    _history_cache.clear()
    _uptime_cache.clear()
    _last.update(rooms=None, alerts={}, waste=0.0, accountability={})
    return {"ok": True, "deleted": out}


@app.post("/api/demo/restart", dependencies=[Depends(require_admin)])
def api_demo_restart():
    """Play the demo scenario from the start (DEMO_SCENARIO=on only)."""
    if not demo.status()["on"]:
        raise HTTPException(409, t("api.demo_off"))
    demo.restart()
    return demo.status()


class LabelBody(BaseModel):
    room_id: str
    headcount: int | None = None  # 0 to 100 people; None = stop labelling this room


LABELS_SHOWN = 50  # the Calibration page lists ten and opens the rest on request


def label_view():
    names = config.room_names()
    return {"recent": [{**r, "name": config.room_name(r["room_id"], names)} for r in labels.recent(LABELS_SHOWN)],
            "open": labels.open_segments()}


@app.get("/api/labels", dependencies=[Depends(require_admin)])
def api_labels():
    """The last LABELS_SHOWN labels, newest first, and the labels running now, for the Calibration page."""
    return label_view()


@app.post("/api/labels", dependencies=[Depends(require_admin)])
def api_label(body: LabelBody):
    """A tap on the /label page: room_id has headcount people from now (closes that room's previous label)."""
    if body.room_id not in validate.known_rooms():
        raise HTTPException(422, t("api.reject_unknown_room", room=body.room_id[:32]))
    now = int(time.time())
    if body.headcount is None:
        labels.stop(body.room_id, now)
    elif 0 <= body.headcount <= MAX_HEADCOUNT_LABEL:
        labels.add(body.room_id, body.headcount, now)
    else:
        raise HTTPException(422, t("api.reject_headcount"))
    return label_view()


@app.post("/api/labels/undo", dependencies=[Depends(require_admin)])
def api_label_undo():
    labels.undo()
    return label_view()


@app.get("/api/audit", dependencies=[Depends(require_admin)])
def api_audit(limit: int = 50, offset: int = 0):
    """Who started or ended an emergency, with IP address and time, a page at a time. Admin only."""
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    log = store.audit_log()
    return {"audit": log[offset:offset + limit], "total": len(log), "limit": limit, "offset": offset}


@app.post("/api/chat")
def api_chat(body: ChatBody, request: Request, who: str = Depends(require_admin)):
    rate_limit("chat", request, guard.CHAT_PER_MIN)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, t("api.empty_question"))
    if len(question) > MAX_QUESTION:
        raise HTTPException(422, t("api.question_too_long", limit=MAX_QUESTION))
    now = int(time.time())
    lang = "ms" if body.lang == "ms" else "en"  # dashboard language, for the model label only
    refresh_live(now)  # Redis offline: answer from the last known data, like the dashboard shows
    floor = body.floor if body.floor and site.FLOOR_ID.fullmatch(body.floor) else None
    return chat.answer(question, {"now": now, "emergency": _last["emergency"], "rooms": room_views(now, _last["rooms"] or [])}, lang, floor)


# --- API docs: off in huawei mode (404), admin only in local mode. Swagger UI and ReDoc load their scripts from a
# CDN, so these two pages get a CSP that allows it; everything else keeps the strict one. ---

DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
            "worker-src blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")


def docs_admin(request: Request, x_admin_token: str = Header("")):
    if config.is_huawei():
        raise HTTPException(404, t("api.not_found"))
    return require_admin(request, x_admin_token)


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(docs_admin)])
def openapi_json():
    return app.openapi()


@app.get("/docs", include_in_schema=False, dependencies=[Depends(docs_admin)])
def swagger_docs():
    from fastapi.openapi.docs import get_swagger_ui_html

    page = get_swagger_ui_html(openapi_url="/openapi.json", title="NADI API")
    page.headers["Content-Security-Policy"] = DOCS_CSP
    return page


@app.get("/redoc", include_in_schema=False, dependencies=[Depends(docs_admin)])
def redoc_docs():
    from fastapi.openapi.docs import get_redoc_html

    page = get_redoc_html(openapi_url="/openapi.json", title="NADI API")
    page.headers["Content-Security-Policy"] = DOCS_CSP
    return page


WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"  # the console, built with npm run build (committed)

if (WEB_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def console(path: str):
    """The web console. Every page (/, /floor, /label, /export, ...) is the same app; files in web/dist are served as is."""
    if path.startswith("api/"):
        raise HTTPException(404, t("api.not_found"))
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, t("api.console_not_built"))
    f = (WEB_DIR / path).resolve()
    if path and f.is_file() and WEB_DIR.resolve() in f.parents:
        return FileResponse(f)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
