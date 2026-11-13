"""Headcount labels for training, written by the /label page to ml/data/labels.csv (git-ignored).

Same columns as the teammates' sheet: room_id,start_ts,end_ts,headcount (0 to 100 people; training uses 3 for 3 or more).
A tap starts a new segment for that room and closes the previous one (its end_ts = this start).
An open segment has an empty end_ts; ml/prepare.py skips open segments, so tap "Stop" when a session ends.
"""
import csv
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["room_id", "start_ts", "end_ts", "headcount"]
_lock = threading.Lock()


def path():
    p = Path(os.getenv("LABELS_PATH") or ROOT / "ml" / "data" / "labels.csv")
    return p if p.is_absolute() else ROOT / p


def read():
    p = path()
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return [{k: (r.get(k) or "").strip() for k in FIELDS} for r in csv.DictReader(f)]


def segments():
    """{room_id: [(start_ts, end_ts or None, headcount), ...]} from the labels file; rows that do not parse are skipped."""
    out = {}
    for r in read():
        try:
            seg = (int(r["start_ts"]), int(r["end_ts"]) if r["end_ts"] else None, int(r["headcount"]))
        except (ValueError, KeyError, TypeError):
            continue
        out.setdefault(r["room_id"], []).append(seg)
    return out


def _write(rows):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, p)  # never leave a half-written file


def _close_open(rows, room_id, ts):
    for r in reversed(rows):
        if r["room_id"] == room_id:
            if not r["end_ts"]:
                r["end_ts"] = str(ts)
            return


def add(room_id, headcount, ts):
    """Start a segment: room_id now has headcount people (0..100) from ts. Closes the room's open segment."""
    with _lock:
        rows = read()
        _close_open(rows, room_id, ts)
        rows.append({"room_id": room_id, "start_ts": str(ts), "end_ts": "", "headcount": str(headcount)})
        _write(rows)


def stop(room_id, ts):
    """End the room's open segment without starting a new one. False if nothing was open."""
    with _lock:
        rows = read()
        open_rows = [r for r in rows if r["room_id"] == room_id and not r["end_ts"]]
        if not open_rows:
            return False
        _close_open(rows, room_id, ts)
        _write(rows)
        return True


def undo():
    """Remove the last tap. If it closed the room's previous segment, that one is reopened. Returns the removed row."""
    with _lock:
        rows = read()
        if not rows:
            return None
        last = rows.pop()
        for r in reversed(rows):
            if r["room_id"] == last["room_id"]:
                if r["end_ts"] == last["start_ts"]:
                    r["end_ts"] = ""
                break
        _write(rows)
        return last


def recent(n=5):
    return [{"room_id": r["room_id"], "start_ts": int(r["start_ts"]), "end_ts": int(r["end_ts"]) if r["end_ts"] else None,
             "headcount": int(r["headcount"])} for r in read()[-n:]][::-1]


def open_segments():
    """{room_id: {"headcount", "start_ts"}} for rooms with a label running now."""
    out = {}
    for r in read():
        if r["end_ts"]:
            out.pop(r["room_id"], None)
        else:
            out[r["room_id"]] = {"headcount": int(r["headcount"]), "start_ts": int(r["start_ts"])}
    return out
