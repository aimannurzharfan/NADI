"""Incidents and drills: what happened between "start" and "end" of emergency mode.

While one runs (live state in Redis, keyed by its id):
  incident:{id}            the start record: kind (real or drill), who, when, every room's count at the start
  incident:{id}:zero       room -> when its count reached 0 (cleared again if people come back)
  incident:{id}:status     room -> {"status": "clear" | "help", "by", "ts"}: a warden's mark ("searched, clear" or
                           "people still inside, need help")
  incident:{id}:offline    room -> [[from, to], ...]: when its sensor was not reporting
  incident:{id}:snaps      times of the saved snapshots
When it ends, a report is written to INCIDENT_DIR/<id>/report.json and the live keys are deleted, so the next
emergency starts with no marks.

Snapshots: the export page's content, saved as JSON plus a self-contained printable HTML page in English and Malay
(INCIDENT_DIR/<id>/snapshot-<time>.*, and latest.*), when the emergency starts and every SNAPSHOT_EVERY_S until it
ends. The files open in any browser with no server, so they exist even if the laptop goes down later.
INCIDENT_DIR defaults to data/incidents (git-ignored).
"""
import html
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from server import alerts, config, logic, store, timeutil
from server.plan import exit_name
from server.strings import t

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"\d{8}-\d{6}-(?:real|drill)-[0-9a-f]{4}")
SNAP = re.compile(r"\d{10}")
SNAPSHOT_EVERY_S = 60
STATUSES = ("clear", "help")
DEMO_KEEP = 5  # the demo scenario raises an alarm every few minutes: keep only its last few reports
LIVE_KEYS = ("", ":zero", ":status", ":offline", ":snaps")


def folder():
    p = Path(os.getenv("INCIDENT_DIR") or ROOT / "data" / "incidents")
    return p if p.is_absolute() else ROOT / p


def new_id(now, kind):
    return f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime(now))}-{'drill' if kind == 'drill' else 'real'}-{secrets.token_hex(2)}"


def valid_id(incident_id):
    return isinstance(incident_id, str) and bool(ID.fullmatch(incident_id))


def emergency_number(lang=None):
    """EMERGENCY_NUMBER from .env, shown on the export as it is (display only, 40 characters). Not set: None, or with
    lang the default from strings.json, "999 (112 from a mobile phone)" in that language."""
    value = os.getenv("EMERGENCY_NUMBER", "").strip()[:40]
    if value or lang is None:
        return value or None
    return t("print.number_default", lang)


# --- live record ---

def _key(incident_id, part=""):
    return f"incident:{incident_id}{part}"


def begin(incident_id, kind, now, by, rooms):
    """Keep the start record. rooms: the room views at the start (server/main.py room_views)."""
    start = [{k: r.get(k) for k in ("room_id", "name", "headcount", "at_least", "live", "count_ts")} for r in rooms]
    rec = {"id": incident_id, "kind": "drill" if kind == "drill" else "real", "started": now, "started_by": by,
           "demo": by == "demo", "building": config.building_name(), "level": config.level_name(), "start_rooms": start}
    store.r.set(_key(incident_id), json.dumps(rec, ensure_ascii=False))
    track_offline(incident_id, rooms, now)
    return rec


def record(incident_id):
    raw = store.r.get(_key(incident_id))
    return json.loads(raw) if raw else None


def on_count(incident_id, room_id, count, ts):
    """A new count for a room during the incident: remember when it reached 0 (and forget it if people return)."""
    if count == 0:
        store.r.hsetnx(_key(incident_id, ":zero"), room_id, int(ts))
    else:
        store.r.hdel(_key(incident_id, ":zero"), room_id)


def set_status(incident_id, room_id, status, by, now):
    """status "clear", "help", or None to remove the mark."""
    if status is None:
        store.r.hdel(_key(incident_id, ":status"), room_id)
    else:
        store.r.hset(_key(incident_id, ":status"), room_id, json.dumps({"status": status, "by": by, "ts": int(now)}))


def statuses(incident_id):
    if not incident_id:
        return {}
    return {room: json.loads(v) for room, v in store.r.hgetall(_key(incident_id, ":status")).items()}


def track_offline(incident_id, rooms, now):
    """Note which rooms' sensors are not reporting now (called at the start and every few seconds)."""
    key = _key(incident_id, ":offline")
    known = store.r.hgetall(key)
    for r in rooms:
        periods = json.loads(known.get(r["room_id"], "[]"))
        down = not r.get("live")
        if down and (not periods or periods[-1][1] is not None):
            periods.append([int(now), None])
        elif not down and periods and periods[-1][1] is None:
            periods[-1][1] = int(now)
        else:
            continue
        store.r.hset(key, r["room_id"], json.dumps(periods))


# --- snapshots ---

def rescue_order(rooms):
    """Same order as the dashboard's "Go here first" list (web/src/components/emergency.tsx rescueOrder): rooms with
    people or with an unknown count, most people first, a room whose sensor is not reporting first on a tie; then the
    rooms known to be empty."""
    def known(r):
        return r.get("live") and r.get("headcount") is not None

    ranked = sorted([r for r in rooms if not known(r) or r["headcount"] > 0],
                    key=lambda r: (-(r.get("headcount") or 0), bool(r.get("live"))))
    return ranked, [r for r in rooms if known(r) and r["headcount"] == 0]


def build_snapshot(em, rooms, marks, now):
    """What the export page shows, as data. em: the emergency state; rooms: room views; marks: statuses()."""
    ranked, zero = rescue_order(rooms)
    live = [r for r in rooms if r.get("live") and r.get("headcount") is not None]
    out = []
    for rank, r in [(i, r) for i, r in enumerate(ranked, 1)] + [(None, r) for r in zero]:
        out.append({"rank": rank, "room_id": r["room_id"], "name": r["name"], "headcount": r.get("headcount"),
                    "at_least": bool(r.get("at_least")), "live": bool(r.get("live")), "count_ts": r.get("count_ts"),
                    "counter": r.get("counter", "csi"),
                    "exit": {lang: exit_name(r["room_id"], lang) for lang in ("en", "ms")},
                    "status": marks.get(r["room_id"])})
    return {"taken": int(now), "id": em.get("id"), "drill": bool(em.get("drill")), "since": em.get("since"),
            "building": config.building_name(), "level": config.level_name(), "emergency_number": emergency_number(),
            "total": sum(r["headcount"] for r in live),
            "at_least": any(logic.is_lower_bound(r) for r in live) or len(live) < len(rooms),
            "unknown": [r["name"] for r in rooms if not (r.get("live") and r.get("headcount") is not None)],
            "rooms": out}


def _count(r):
    if not r["live"] or r["headcount"] is None:
        return "?"
    return logic.shown(r["headcount"], r["at_least"])


def _source(r, now, lang):
    if r["live"]:
        return t("print.live", lang)
    if r["headcount"] is not None and r["count_ts"]:
        return t("count.last_known", lang, count=logic.shown(r["headcount"], r["at_least"]),
                 ago=t("time.seconds", lang, n=max(0, now - r["count_ts"])))
    return t("count.unknown", lang)


def _counter_note(r, lang):
    """A count from the "count" service is a simulated counter (phase 2), never a Wi-Fi sensor: say so."""
    return f"<br><small>{html.escape(t('room.sim_counter', lang))}</small>" if r.get("counter") == "count" else ""


def status_text(status, lang):
    if not status:
        return t("acc.none", lang)
    word = t("acc.clear" if status["status"] == "clear" else "acc.help", lang)
    return t("acc.by", lang, status=word, who=status["by"], time=timeutil.clock(status["ts"]))


def snapshot_html(snap, lang="en"):
    """A printable page that needs nothing else: no scripts, no server, all text escaped."""
    e = html.escape
    now = snap["taken"]
    since = snap.get("since")
    head = [t("print.taken", lang, time=f"{timeutil.stamp(now)} ({t('time.zone', lang)})")]
    head.append(t("print.alarm", lang, time=timeutil.clock(since), duration=timeutil.duration(now - since))
                if since else t("print.no_alarm", lang))
    total = (f"{e(t('count.at_least_label', lang))} " if snap["at_least"] else "") + str(snap["total"])
    still_one = snap["total"] == 1  # "1 person still inside"
    unknown = snap["unknown"]
    unknown_line = (t("count.unknown_one" if len(unknown) == 1 else "count.unknown_many", lang, n=len(unknown))
                    + ": " + ", ".join(unknown)) if unknown else t("print.all_live", lang)
    rows = "".join(
        f"<tr><td>{r['rank'] or '–'}</td><td><b>{e(r['name'])}</b></td><td class=n>{e(_count(r))}</td>"
        f"<td>{e(r['exit'][lang] or '–')}</td><td>{e(_source(r, now, lang))}{_counter_note(r, lang)}</td>"
        f"<td>{e(status_text(r['status'], lang))}</td></tr>"
        for r in snap["rooms"])
    drill = f"<p class=drill>{e(t('drill.banner', lang))}</p>" if snap.get("drill") else ""
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><title>{e(t('print.title', lang))}</title>
<style>body{{font:14px/1.4 Arial,sans-serif;color:#111;max-width:800px;margin:24px auto;padding:0 16px}}
h1{{font-size:22px;margin:4px 0}}table{{width:100%;border-collapse:collapse;margin-top:12px}}
th,td{{text-align:left;padding:5px 6px;border-bottom:1px solid #ccc}}th{{border-bottom:2px solid #111}}td.n{{font-weight:bold;font-size:16px}}
.big{{font-size:32px;font-weight:bold}}.note{{border:1px solid #111;padding:4px 8px;font-weight:bold}}
.drill{{background:#111;color:#fff;padding:6px 10px;font-weight:bold;letter-spacing:.04em}}</style></head>
<body>{drill}<p><b>{e(t('print.title', lang))}</b></p><h1>{e(snap['building'])}, {e(snap['level'])}</h1>
<p>{e(' '.join(head))}</p>
<p class=note>{e(t('print.call', lang, number=snap['emergency_number'] or t('print.number_default', lang)))}</p>
<p><span class=big>{total}</span> <b>{e(t('em.still_inside_one' if still_one else 'em.still_inside', lang))}</b>. {e(unknown_line)}</p>
<p class=note>{e(t('safety.disclaimer', lang))}</p>
<table><thead><tr><th>#</th><th>{e(t('rooms.col_room', lang))}</th><th>{e(t('rooms.col_people', lang))}</th>
<th>{e(t('detail.nearest_exit', lang))}</th><th>{e(t('print.count_source', lang))}</th><th>{e(t('acc.col', lang))}</th></tr></thead>
<tbody>{rows}</tbody></table>
<p>{e(t('print.footer', lang))}</p>
<p><small>{e(t('print.saved', lang, time=timeutil.stamp(now), id=snap.get('id') or '–'))}</small></p>
</body></html>
"""


def _write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # never a half-written file, even if the power goes now


def snapshot_due(incident_id, now):
    last = store.r.lindex(_key(incident_id, ":snaps"), -1)
    return last is None or now - int(last) >= SNAPSHOT_EVERY_S


def save_snapshot(incident_id, snap):
    """Write the snapshot files and note the time. Returns the folder."""
    d = folder() / incident_id
    d.mkdir(parents=True, exist_ok=True)
    ts = snap["taken"]
    data = json.dumps(snap, ensure_ascii=False, indent=1)
    for name in (f"snapshot-{ts}", "latest"):
        _write(d / f"{name}.json", data)
        for lang in ("en", "ms"):
            _write(d / f"{name}.{lang}.html", snapshot_html(snap, lang))
    store.r.rpush(_key(incident_id, ":snaps"), ts)
    return d


def snapshot_file(incident_id, ts, lang):
    """Path of a saved snapshot page ("latest" or a time), or None."""
    if not valid_id(incident_id) or not (ts == "latest" or SNAP.fullmatch(str(ts))):
        return None
    p = folder() / incident_id / f"{'latest' if ts == 'latest' else 'snapshot-' + str(ts)}.{'ms' if lang == 'ms' else 'en'}.html"
    return p if p.is_file() else None


# --- the report, written when it ends ---

def finish(incident_id, now, by, rooms_now):
    """Freeze the report, write it to disk, delete the live keys. Returns the report (None without a start record)."""
    rec = record(incident_id)
    if rec is None:
        return None
    started = rec["started"]
    zero = {k: int(v) for k, v in store.r.hgetall(_key(incident_id, ":zero")).items()}
    marks = statuses(incident_id)
    track_offline(incident_id, rooms_now, now)
    offline = {k: json.loads(v) for k, v in store.r.hgetall(_key(incident_id, ":offline")).items()}
    snaps = [int(x) for x in store.r.lrange(_key(incident_id, ":snaps"), 0, -1)]
    names = config.room_names()
    start = {r["room_id"]: r for r in rec["start_rooms"]}
    end = {r["room_id"]: r for r in rooms_now}
    ids = list(start) + sorted((set(end) | set(marks) | set(zero)) - set(start))
    rooms = []
    for rid in ids:
        s, e = start.get(rid) or {}, end.get(rid) or {}
        empty_at_start = bool(s.get("live")) and s.get("headcount") == 0
        zero_ts = zero.get(rid)
        rooms.append({"room_id": rid, "name": config.room_name(rid, names),
                      "start_count": s.get("headcount"), "start_at_least": bool(s.get("at_least")),
                      "start_live": bool(s.get("live")), "empty_at_start": empty_at_start,
                      "zero_ts": None if empty_at_start else zero_ts,
                      "to_zero_s": None if empty_at_start or zero_ts is None else max(0, zero_ts - started),
                      "end_count": e.get("headcount"), "end_at_least": bool(e.get("at_least")),
                      "end_live": bool(e.get("live")),
                      "status": marks.get(rid)})
    raised = []
    for raw in store.r.lrange("alerts", 0, alerts.KEEP - 1):
        a = json.loads(raw)
        if started <= a.get("ts", 0) <= now and a.get("id"):
            raised.append(a)
    acks = store.r.hgetall("alert_ack")
    for a in raised:
        a["ack"] = json.loads(acks[a["id"]]) if a["id"] in acks else None
    report = {**{k: rec[k] for k in ("id", "kind", "started", "started_by", "demo", "building", "level")},
              "ended": int(now), "ended_by": by, "duration_s": int(now) - started,
              "start_total": sum(r["start_count"] or 0 for r in rooms if r["start_live"]),
              "start_at_least": any(r["start_at_least"] or not r["start_live"] for r in rooms),
              "start_unknown": [r["name"] for r in rooms if not r["start_live"] and r["room_id"] in start],
              "rooms": rooms, "alerts": list(reversed(raised)),
              "offline": [{"room_id": rid, "name": config.room_name(rid, names), "periods": p}
                          for rid, p in sorted(offline.items())],
              "snapshots": snaps}
    d = folder() / incident_id
    d.mkdir(parents=True, exist_ok=True)
    _write(d / "report.json", json.dumps(report, ensure_ascii=False, indent=1))
    store.r.delete(*[_key(incident_id, part) for part in LIVE_KEYS])
    if rec.get("demo"):
        _prune_demo()
    return report


def _prune_demo():
    demo = [r for r in reports() if r.get("demo")]
    for r in demo[DEMO_KEEP:]:
        shutil.rmtree(folder() / r["id"], ignore_errors=True)


def report(incident_id):
    """The saved report, or None. Acknowledgements made after it ended are filled in from the alerts."""
    if not valid_id(incident_id):
        return None
    p = folder() / incident_id / "report.json"
    if not p.is_file():
        return None
    rep = json.loads(p.read_text(encoding="utf-8"))
    try:
        acks = store.r.hgetall("alert_ack")
    except store.REDIS_ERRORS:
        acks = {}
    for a in rep.get("alerts", []):
        if a.get("id") in acks:
            a["ack"] = json.loads(acks[a["id"]])
    return rep


def reports():
    """Every saved report, newest first, as a short summary."""
    out = []
    root = folder()
    if not root.is_dir():
        return out
    for d in root.iterdir():
        p = d / "report.json"
        if valid_id(d.name) and p.is_file():
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            out.append({k: r.get(k) for k in ("id", "kind", "started", "ended", "duration_s", "started_by", "ended_by",
                                              "start_total", "start_at_least", "demo")}
                       | {"marked": sum(1 for x in r.get("rooms", []) if x.get("status")),
                          "offline_rooms": len(r.get("offline", []))})
    return sorted(out, key=lambda r: r["started"] or 0, reverse=True)


def delete_all():
    """Every report and snapshot on disk (privacy deletion). Returns the number of incident folders removed."""
    root = folder()
    n = 0
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                n += 1
    return n
