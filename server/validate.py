"""Checks on every sensor report before anything is stored. A report that fails is rejected whole, with a reason.

Rules:
- room_id: letters, digits, - and _ (max 32), and a room the server knows (plan.json or ROOM_NAMES).
- DEVICE_ROOMS (optional): nadi-recv-1:room1,nadi-climate-1:room1,nadi-sim:* limits which rooms a device may
  report for. When it is set, a device that is not listed is refused. Empty = any known room (logged at start-up).
- ts: 0 or missing = the server's clock (a board without NTP sends 0). Otherwise a number no older than one day
  and no more than 5 minutes ahead of the server.
- Numbers must be real numbers (not text, true/false, NaN or Infinity) inside the bounds below.
"""
import math
import os
import re
import time

from server import config
from server.plan import PLAN
from server.strings import t

ROOM_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")  # used with fullmatch: "$" would let a trailing newline through
MAX_AGE_S = 86400
MAX_AHEAD_S = 300
clock = time.time  # tests replace this to check old fixed timestamps

# (low, high, required). Wide enough for any real board, tight enough to catch nonsense like temp 500.
BOUNDS = {
    "csi": {
        "motion_mean": (0.0, 100.0, False), "motion_std": (0.0, 100.0, True), "amp_var": (0.0, 1e6, False),
        "rssi_mean": (-127.0, 0.0, False), "n_packets": (0, 100000, False),
    },
    "climate": {"temp_c": (-20.0, 70.0, True), "humidity": (0.0, 100.0, False)},
    # an exact headcount from another counter (door counter, the demo hall): 0 to 1000 people
    "count": {"headcount": (0, 1000, True)},
}
# Board health, sent with every report by firmware 1.1 and later (optional, so older boards still work)
HEALTH = {"uptime_s": (0, 10 ** 9, False), "wifi_rssi": (-127, 0, False), "free_heap": (0, 10 ** 9, False),
          "dropped": (0, 10 ** 9, False)}
FW_VERSION = re.compile(r"[A-Za-z0-9._-]{1,16}")


class Rejected(ValueError):
    """reason is a strings.json key, values fill its placeholders."""

    def __init__(self, reason, **values):
        super().__init__(reason)
        self.reason, self.values = reason, values

    def text(self, lang="en"):
        return t(self.reason, lang, **self.values)


def known_rooms():
    return set(PLAN["rooms"]) | set(config.room_names())


def device_rooms(raw=None):
    """DEVICE_ROOMS -> {device_id: {room_id, ...} or {"*"}}, or None when not set."""
    raw = os.getenv("DEVICE_ROOMS", "") if raw is None else raw
    out = {}
    for part in raw.split(","):
        device, sep, room = part.partition(":")
        device, room = device.strip(), room.strip()
        if sep and device and room:
            out.setdefault(device, set()).add(room)
    return out or None


def number(p, field, low, high, required):
    """The value of field as a float/int inside [low, high], None if absent and optional."""
    v = p.get(field)
    if v is None:
        if required:
            raise Rejected("api.reject_missing", field=field)
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Rejected("api.reject_type", field=field)
    if not math.isfinite(v) or not low <= v <= high:
        raise Rejected("api.reject_range", field=field, low=low, high=high)
    return v


def check(svc, device_id=None, now=None):
    """One services[] entry -> {"service_id", "room_id", "ts", "properties"} with only checked fields, or Rejected."""
    now = int(clock()) if now is None else now
    if not isinstance(svc, dict):
        raise Rejected("api.reject_shape")
    service_id = svc.get("service_id")
    if service_id not in BOUNDS:
        raise Rejected("api.reject_service")
    p = svc.get("properties")
    if not isinstance(p, dict):
        raise Rejected("api.reject_shape")
    room_id = p.get("room_id")
    if not isinstance(room_id, str) or not ROOM_ID.fullmatch(room_id):
        raise Rejected("api.reject_room_id")
    if room_id not in known_rooms():
        raise Rejected("api.reject_unknown_room", room=room_id)
    allowed = device_rooms()
    if allowed is not None:
        rooms = allowed.get(device_id or "", set())
        if "*" not in rooms and room_id not in rooms:
            raise Rejected("api.reject_device_room", device=str(device_id)[:64], room=room_id)

    raw_ts = p.get("ts")
    if raw_ts in (None, 0):
        ts = now
    else:
        if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)) or not math.isfinite(raw_ts):
            raise Rejected("api.reject_type", field="ts")
        ts = int(raw_ts)
        if ts < now - MAX_AGE_S:
            raise Rejected("api.reject_ts_old")
        if ts > now + MAX_AHEAD_S:
            raise Rejected("api.reject_ts_future")

    props = {"room_id": room_id, "ts": ts}
    for field, (low, high, required) in BOUNDS[service_id].items():
        props[field] = number(p, field, low, high, required)
    if service_id == "count" and props["headcount"] != int(props["headcount"]):
        raise Rejected("api.reject_type", field="headcount")
    health = {field: number(p, field, low, high, required) for field, (low, high, required) in HEALTH.items()}
    fw = p.get("fw_version")
    if fw is not None and not (isinstance(fw, str) and FW_VERSION.fullmatch(fw)):
        raise Rejected("api.reject_fw")
    health["fw_version"] = fw
    props["health"] = {k: v for k, v in health.items() if v is not None}
    return {"service_id": service_id, "room_id": room_id, "ts": ts, "properties": props}


def check_all(services, device_id=None, now=None):
    """Every entry or nothing: (clean list, []) or ([], [reason text, ...])."""
    if not isinstance(services, list) or not services:
        return [], [t("api.reject_no_services")]
    if len(services) > 50:
        return [], [t("api.reject_too_many")]
    clean, errors = [], []
    for i, svc in enumerate(services):
        try:
            clean.append(check(svc, device_id, now))
        except Rejected as e:
            errors.append(f"services[{i}]: {e.text()}")
    return ([], errors) if errors else (clean, [])
