"""Buildings, floors and their floor plans, stored as files under SITE_DIR (default data/site, git-ignored).

    data/site/site.json                        {"buildings": [{"id", "name", "code", "floors": [{"id", "name", "level"}]}]}
    data/site/plans/<floor_id>/v000001.json    {"version", "saved_ts", "saved_by", "note", "plan": {...}}
    data/site/images/<sha256>.<png|jpg>        uploaded backgrounds, named by content hash

Files, not MySQL: the emergency view must draw its plan while the history database is down, and a plan is a
document with versions. Every write goes to a temporary file first and is moved into place (os.replace).

Built in, never stored:
- building b1 / floor f1: named by BUILDING_NAME / LEVEL_NAME until an admin renames them; f1's plan is
  dashboard/plan.json ("version 0", always restorable) until a version is saved for it. An empty SITE_DIR therefore
  gives exactly today's console.
- the example building ("Example Tower (example data)"): 12 floors drawn from the corridor template, read-only, no
  sensors, and its rooms are not known rooms (no board can report for them). EXAMPLE_BUILDING=off hides it.
"""
import json
import math
import os
import re
import threading
import time
from pathlib import Path

from server.strings import STRINGS, t

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PLAN = ROOT / "dashboard" / "plan.json"
DEFAULT_FLOOR = "f1"
EXAMPLE_ID = "example"
EXAMPLE_FLOORS = 12
BOX = (1000, 560)
MIN_SIDE = 40
MIN_LINK = 30
MAX_ROOMS = 60
MAX_PLAN_BYTES = 64 * 1024
MAX_NAME = 40
VERSIONS_KEPT = 30
ROOM_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
EXIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
FLOOR_ID = re.compile(r"(f\d{1,6}|ex-\d{1,2})")
BUILDING_ID = re.compile(r"(b\d{1,6}|example)")
IMAGE_NAME = re.compile(r"[0-9a-f]{64}\.(png|jpg)")
# the fields a plan may carry: anything else is refused, so nothing but drawing data is stored and served
KEYS = {"plan": {"viewBox", "outline", "corridor", "rooms", "exits", "other", "background"},
        "rect": {"x", "y", "w", "h"},
        "room": {"name", "x", "y", "w", "h", "door", "exit", "link", "area_m2", "capacity"},
        "exit": {"label", "name", "kind", "x", "y", "w", "h", "door"},
        "other": {"label", "name", "x", "y", "w", "h"},
        "door": {"x", "side"}, "link": {"send", "recv"}, "point": {"x", "y"}, "background": {"image", "opacity"}}

_lock = threading.RLock()
_cache = {}


MAX_CAPACITY = 1000


class NotFound(Exception):
    pass


class ReadOnly(Exception):
    """The example building cannot be changed."""


class Conflict(Exception):
    """Someone else saved this floor since the editor opened it."""


class Invalid(Exception):
    def __init__(self, errors):
        super().__init__(errors)
        self.errors = errors


def folder():
    p = Path(os.getenv("SITE_DIR") or ROOT / "data" / "site")
    return p if p.is_absolute() else ROOT / p


def reset():
    """Forget what was read (tests, and a changed SITE_DIR)."""
    with _lock:
        _cache.clear()


def example_on():
    return os.getenv("EXAMPLE_BUILDING", "on").strip().lower() not in ("off", "0", "false", "no")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# --- the built-in and example plans ---

def builtin_plan():
    """dashboard/plan.json without its "_about" notes: floor f1's version 0."""
    raw = json.loads(BUILTIN_PLAN.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def corridor_plan(prefix, level, per_side=4, lang="en"):
    """Rooms on both sides of a corridor, a staircase at each end: the example floors and the editor's first template.
    Room IDs are <prefix>-a, <prefix>-b, ...; names "Room <level>.01" ("Bilik 7.01" in Malay) ...; every room names
    its nearer staircase."""
    plan = {"viewBox": [0, 0, *BOX], "outline": {"x": 20, "y": 20, "w": 960, "h": 520},
            "corridor": {"x": 20, "y": 240, "w": 960, "h": 70}, "rooms": {},
            "exits": {"stairA": {"label": "plan.stair_a", "kind": "stair", "x": 20, "y": 20, "w": 100, "h": 220,
                                 "door": {"x": 70, "side": "s"}},
                      "stairB": {"label": "plan.stair_b", "kind": "stair", "x": 860, "y": 310, "w": 120, "h": 230,
                                 "door": {"x": 920, "side": "n"}}},
            "other": [{"label": "plan.toilets", "x": 860, "y": 20, "w": 120, "h": 220},
                      {"label": "plan.lifts", "x": 20, "y": 310, "w": 140, "h": 230}],
            "background": None}
    rows = [(120, 860, 20, 220, "s"), (160, 860, 310, 230, "n")]
    n = 0
    for x0, x1, y, h, side in rows:
        w = (x1 - x0) // per_side
        for i in range(per_side):
            x = x0 + i * w
            room_id = f"{prefix}-{chr(ord('a') + n)}"
            n += 1
            plan["rooms"][room_id] = {"name": t("site.example_room", lang, level=level, n=f"{n:02d}"), "x": x, "y": y, "w": w, "h": h,
                                      "door": {"x": x + w // 2, "side": side},
                                      "exit": "stairA" if x + w / 2 < 500 else "stairB"}
    return plan


def _example(lang="en"):
    floors = [{"id": f"ex-{n}", "name": t("site.level_n", lang, n=n), "level": n} for n in range(1, EXAMPLE_FLOORS + 1)]
    return {"id": EXAMPLE_ID, "name": t("site.example_name", lang), "code": "EX-01", "example": True, "floors": floors}


def _example_plan(floor_id, lang="en"):
    n = int(floor_id.split("-")[1])
    return corridor_plan(f"ex-l{n:02d}", n, lang=lang)


# --- reading ---

def _builtin_site():
    return {"buildings": [{"id": "b1", "name": None, "code": "", "floors": [{"id": DEFAULT_FLOOR, "name": None, "level": None}]}]}


def _stored_site():
    """site.json, or the built-in building when there is none. A file that cannot be read is reported and left as it
    is (an admin can restore it); the console then shows the built-in floor instead of failing."""
    p = folder() / "site.json"
    if not p.exists():
        return _builtin_site()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("buildings"), list) or not data["buildings"]:
            raise ValueError("no buildings")
        return data
    except (OSError, ValueError) as e:
        print(f"{p} cannot be read ({e}): showing the built-in floor", flush=True)
        return _builtin_site()


def _level_of(name):
    m = re.search(r"-?\d+", name or "")
    return int(m.group(0)) if m else 1


def buildings(with_example=True, lang="en"):
    """Every building with its floors, names filled in: [{"id", "name", "code", "example", "floors": [...]}]. The
    example building is named in lang; names an admin typed are shown as written in both languages."""
    from server import config  # here, not at the top: config reads the plan, which reads this module

    with _lock:
        key = ("site", str(folder()))
        if key not in _cache:
            _cache[key] = _stored_site()
        stored = _cache[key]
    out = []
    for b in stored["buildings"]:
        floors = []
        for f in b["floors"]:
            name = f.get("name")
            if f["id"] == DEFAULT_FLOOR and not name:
                name = config.level_name()
            level = f.get("level")
            floors.append({"id": f["id"], "name": name, "level": _level_of(name) if level is None else level})
        name = b.get("name") or (config.building_name() if b["id"] == "b1" else b["id"])
        out.append({"id": b["id"], "name": name, "code": b.get("code") or "", "example": False, "floors": floors})
    if with_example and example_on():
        out.append(_example(lang))
    return out


def floor_info(floor_id, lang="en"):
    """(building, floor) for a floor ID, or raises NotFound."""
    for b in buildings(lang=lang):
        for f in b["floors"]:
            if f["id"] == floor_id:
                return b, f
    raise NotFound(floor_id)


def is_example(floor_id):
    return isinstance(floor_id, str) and floor_id.startswith("ex-")


def _plan_dir(floor_id):
    return folder() / "plans" / floor_id


def _version_files(floor_id):
    d = _plan_dir(floor_id)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("v*.json") if re.fullmatch(r"v\d{6}\.json", p.name))


def plan(floor_id, lang="en"):
    """{"floor_id", "version", "saved_ts", "saved_by", "note", "plan"}: the floor's current plan. Raises NotFound."""
    b, _ = floor_info(floor_id)
    if b["example"]:
        return {"floor_id": floor_id, "version": 0, "saved_ts": None, "saved_by": None, "note": "", "plan": _example_plan(floor_id, lang)}
    with _lock:
        key = ("plan", str(folder()), floor_id)
        if key not in _cache:
            doc = None
            for f in reversed(_version_files(floor_id)):  # the newest version that can be read
                try:
                    doc = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(doc, dict) and isinstance(doc.get("plan"), dict) and isinstance(doc.get("version"), int):
                        break
                except (OSError, ValueError):
                    pass
                print(f"{f} cannot be read: using the version before it", flush=True)
                doc = None
            if doc is None:  # nothing saved: f1's built-in plan, or a new floor that has not been drawn yet
                doc = {"version": 0, "saved_ts": None, "saved_by": None, "note": "",
                       "plan": builtin_plan() if floor_id == DEFAULT_FLOOR else blank_plan()}
            _cache[key] = {"floor_id": floor_id, **doc}
        return _cache[key]


def capacity_changes(before, after):
    """[[room_id, old, new]] for every room whose capacity differs between two plans (None: not set)."""
    a, b = (before or {}).get("rooms") or {}, (after or {}).get("rooms") or {}
    out = []
    for room_id in sorted(set(a) | set(b)):
        old = a.get(room_id, {}).get("capacity") if isinstance(a.get(room_id), dict) else None
        new = b.get(room_id, {}).get("capacity") if isinstance(b.get(room_id), dict) else None
        if old != new:
            out.append([room_id, old, new])
    return out


def blank_plan():
    return {"viewBox": [0, 0, *BOX], "outline": {"x": 20, "y": 20, "w": 960, "h": 520}, "corridor": None, "rooms": {},
            "exits": {}, "other": [], "background": None}


def versions(floor_id):
    """[{"version", "saved_ts", "saved_by", "note", "rooms"}], newest first; f1 ends with its built-in version 0."""
    b, _ = floor_info(floor_id)
    if b["example"]:
        return [{"version": 0, "saved_ts": None, "saved_by": None, "note": "", "rooms": len(_example_plan(floor_id)["rooms"])}]
    out = []
    for p in reversed(_version_files(floor_id)):
        doc = json.loads(p.read_text(encoding="utf-8"))
        row = {"version": doc["version"], "saved_ts": doc["saved_ts"], "saved_by": doc["saved_by"],
               "note": doc.get("note", ""), "rooms": len(doc["plan"].get("rooms", {}))}
        if doc.get("restored_from") is not None:
            row["restored_from"] = doc["restored_from"]
        out.append(row)
    if floor_id == DEFAULT_FLOOR:
        out.append({"version": 0, "saved_ts": None, "saved_by": None, "note": "", "rooms": len(builtin_plan()["rooms"])})
    return out


def version_plan(floor_id, version):
    """The plan stored as one version of a floor (0: the built-in plan of f1). Raises NotFound."""
    if floor_id == DEFAULT_FLOOR and version == 0:
        return builtin_plan()
    p = _plan_dir(floor_id) / f"v{int(version):06d}.json"
    if not isinstance(version, int) or version < 1 or not p.exists():
        raise NotFound(version)
    return json.loads(p.read_text(encoding="utf-8"))["plan"]


def current_plans(with_example=False):
    """{floor_id: plan} of every floor (example floors only when asked)."""
    return {f["id"]: plan(f["id"])["plan"] for b in buildings(with_example) if with_example or not b["example"] for f in b["floors"]}


def image_path(name):
    """Path of a stored background image, or None for a name that is not one of ours."""
    if not isinstance(name, str) or not IMAGE_NAME.fullmatch(name):
        return None
    p = folder() / "images" / name
    return p if p.is_file() else None


def summary(editor, lang="en"):
    """What GET /api/site answers: buildings, floors (with rooms and version), the default floor, editor on/off."""
    out = []
    for b in buildings(lang=lang):
        floors = []
        for f in b["floors"]:
            doc = plan(f["id"])
            floors.append({**f, "rooms": len(doc["plan"].get("rooms", {})), "version": doc["version"]})
        out.append({**b, "floors": floors})
    return {"buildings": out, "default_floor": DEFAULT_FLOOR, "editor": editor}


# --- validation ---

def _num(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _rect(o):
    return isinstance(o, dict) and all(_num(o.get(k)) for k in ("x", "y", "w", "h"))


def _inside(o):
    return o["x"] >= 0 and o["y"] >= 0 and o["w"] > 0 and o["h"] > 0 and o["x"] + o["w"] <= BOX[0] and o["y"] + o["h"] <= BOX[1]


def _overlap(a, b):
    """True when two rectangles share area; touching edges do not count."""
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def _name_ok(name):
    return isinstance(name, str) and 1 <= len(name.strip()) <= MAX_NAME


def label_of(item, lang="en"):
    """What a stair, exit or other space is called: its strings key in the page language, or the name typed in."""
    key = item.get("label")
    if isinstance(key, str) and key in STRINGS:
        return t(key, lang)
    return str(item.get("name") or "").strip()


def validate_plan(doc, floor_id, live_rooms=(), lang="en"):
    """Every problem with a plan, all at once, as [{"key": strings key, "values": {...}}]; [] when it can be saved.
    live_rooms: rooms with a sensor reporting now; one of them on this floor may not disappear from it."""
    errors = []

    def err(key, **values):
        errors.append({"key": key, "values": values})

    if not isinstance(doc, dict):
        return [{"key": "site.err_shape", "values": {}}]
    if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > MAX_PLAN_BYTES:
        return [{"key": "site.err_too_large", "values": {"kb": MAX_PLAN_BYTES // 1024}}]
    rooms, exits, other = doc.get("rooms"), doc.get("exits"), doc.get("other", [])
    if set(doc) - KEYS["plan"] or any(isinstance(doc.get(k), dict) and set(doc[k]) - KEYS["rect"] for k in ("outline", "corridor")):
        return [{"key": "site.err_shape", "values": {}}]
    if (doc.get("viewBox") != [0, 0, *BOX] or not _rect(doc.get("outline")) or not isinstance(rooms, dict)
            or not isinstance(exits, dict) or not isinstance(other, list)
            or (doc.get("corridor") is not None and not _rect(doc.get("corridor")))):
        return [{"key": "site.err_shape", "values": {}}]
    for key in ("outline", "corridor"):
        if doc.get(key) is not None and not _inside(doc[key]):
            err("site.err_outside", name=t("plan.corridor") if key == "corridor" else key)
    if len(rooms) > MAX_ROOMS:
        err("site.err_too_many", n=MAX_ROOMS)

    def shape(item, name, kind):
        if not _rect(item) or set(item) - KEYS[kind]:
            err("site.err_shape_of", name=name)
            return False
        if not _inside(item):
            err("site.err_outside", name=name)
        elif item["w"] < MIN_SIDE or item["h"] < MIN_SIDE:
            err("site.err_small", name=name, min=MIN_SIDE)
        door = item.get("door")
        if door is not None and not (isinstance(door, dict) and not set(door) - KEYS["door"] and _num(door.get("x")) and door.get("side") in ("n", "s")
                                     and item["x"] <= door["x"] <= item["x"] + item["w"]):
            err("site.err_door", name=name)
        return True

    exit_rects = {}
    if not exits:
        err("site.err_no_exit")
    for key, ex in exits.items():
        if not isinstance(ex, dict) or not EXIT_ID.fullmatch(str(key)):
            err("site.err_shape_of", name=str(key)[:32])
            continue
        name = label_of(ex) or str(key)
        if not ex.get("label") in STRINGS and not _name_ok(ex.get("name")):
            err("site.err_name", name=str(key)[:32], max=MAX_NAME)
        if ex.get("kind", "stair") not in ("stair", "exit"):
            err("site.err_shape_of", name=name)
        if shape(ex, name, "exit"):
            exit_rects[key] = (name, ex)
    for i, o in enumerate(other):
        name = (label_of(o) if isinstance(o, dict) else "") or f"#{i + 1}"
        if isinstance(o, dict) and not o.get("label") in STRINGS and not _name_ok(o.get("name")):
            err("site.err_name", name=name, max=MAX_NAME)
        shape(o, name, "other")
    elsewhere = {}  # room ID -> floor name, for every other floor of every building
    for b in buildings(lang=lang):
        for f in b["floors"]:
            if f["id"] != floor_id:
                for room_id in plan(f["id"])["plan"].get("rooms", {}):
                    elsewhere.setdefault(room_id, f"{b['name']}, {f['name']}")
    placed = []
    for room_id, room in rooms.items():
        if not ROOM_ID.fullmatch(str(room_id)):
            err("site.err_id", id=str(room_id)[:32])
            continue
        if not isinstance(room, dict):
            err("site.err_shape_of", name=room_id)
            continue
        name = room.get("name") if _name_ok(room.get("name")) else room_id
        if room.get("name") is not None and not _name_ok(room.get("name")):
            err("site.err_name", name=room_id, max=MAX_NAME)
        if room_id in elsewhere:
            err("site.err_taken", id=room_id, floor=elsewhere[room_id])
        if room.get("exit") not in exits:
            err("site.err_exit_missing", name=name)
        area = room.get("area_m2")
        if area is not None and not (_num(area) and 1 <= area <= 100000):
            err("site.err_area", name=name)
        capacity = room.get("capacity")  # optional: how many people the room is meant for (a line on the people chart)
        if capacity is not None and not (isinstance(capacity, int) and not isinstance(capacity, bool) and 1 <= capacity <= MAX_CAPACITY):
            err("site.err_capacity", name=name, max=MAX_CAPACITY)
        if not shape(room, name, "room"):
            continue
        link = room.get("link")
        if link is not None:
            ends = [link.get(k) if isinstance(link, dict) else None for k in ("send", "recv")]
            points = [(e["x"], e["y"]) for e in ends
                      if isinstance(e, dict) and not set(e) - KEYS["point"] and _num(e.get("x")) and _num(e.get("y"))
                      and room["x"] <= e["x"] <= room["x"] + room["w"] and room["y"] <= e["y"] <= room["y"] + room["h"]]
            # both ends well formed and inside the room, and far enough apart to measure anything
            good = isinstance(link, dict) and not set(link) - KEYS["link"] and len(points) == 2
            if not good or math.dist(points[0], points[1]) < MIN_LINK:
                err("site.err_link", name=name, min=MIN_LINK)
        for other_name, other_rect in placed:
            if _overlap(room, other_rect):
                err("site.err_overlap", a=other_name, b=name)
        for ex_name, ex in exit_rects.values():
            if _overlap(room, ex):
                err("site.err_overlap", a=name, b=ex_name)
        placed.append((name, room))
    background = doc.get("background")
    if background is not None:
        if not (isinstance(background, dict) and not set(background) - KEYS["background"] and image_path(background.get("image")) is not None
                and _num(background.get("opacity", 0.5)) and 0 <= background.get("opacity", 0.5) <= 1):
            err("site.err_background")
    try:
        before = plan(floor_id)["plan"].get("rooms", {})
    except NotFound:
        before = {}
    for room_id in sorted(set(before) & set(live_rooms) - set(rooms)):
        err("site.err_live", id=room_id, name=str(before[room_id].get("name") or room_id))
    return errors


def messages(errors, lang="en"):
    """The errors with their message in lang: [{"key", "values", "message"}]."""
    return [{**e, "message": t(e["key"], lang, **e["values"])} for e in errors]


# --- writing ---

NAME_MAX = 40
CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,15}")


def _versions_numbers(floor_id):
    return [int(p.stem[1:]) for p in _version_files(floor_id)]


def _check_writable(floor_id):
    b, f = floor_info(floor_id)
    if b["example"]:
        raise ReadOnly(floor_id)
    return b, f


def save_plan(floor_id, doc, by, note="", base_version=None, live_rooms=(), restored_from=None, lang="en"):
    """Store doc as the floor's next version, after every check. base_version: the version the editor started from;
    when another save came in between, Conflict. Returns the new version number. Nothing is written on any error."""
    with _lock:
        _check_writable(floor_id)
        current = plan(floor_id)["version"]
        if base_version is not None and base_version != current:
            raise Conflict(current)
        errors = validate_plan(doc, floor_id, live_rooms, lang)
        if errors:
            raise Invalid(errors)
        numbers = _versions_numbers(floor_id)
        version = max(numbers + [current]) + 1
        record = {"version": version, "saved_ts": int(time.time()), "saved_by": str(by)[:64], "note": str(note or "")[:200],
                  "plan": doc}
        if restored_from is not None:
            record["restored_from"] = restored_from
        _write(_plan_dir(floor_id) / f"v{version:06d}.json", record)
        for old in sorted(numbers + [version])[:-VERSIONS_KEPT]:  # keep the newest VERSIONS_KEPT
            (_plan_dir(floor_id) / f"v{old:06d}.json").unlink(missing_ok=True)
        _cache.pop(("plan", str(folder()), floor_id), None)
        return version


def restore(floor_id, version, by, live_rooms=(), lang="en"):
    """A new version with the content of an old one (the history stays a straight line), checked again against the
    floors as they are now. Raises NotFound for a version that is not kept."""
    with _lock:
        _check_writable(floor_id)
        old = version_plan(floor_id, version)
        return save_plan(floor_id, old, by, note="", live_rooms=live_rooms, restored_from=version, lang=lang)


def _site_for_write():
    """site.json as stored, with the built-in b1/f1 written out the first time anything is added or renamed."""
    stored = _stored_site()
    return {"buildings": [{"id": b["id"], "name": b.get("name"), "code": b.get("code") or "",
                           "floors": [{"id": f["id"], "name": f.get("name"), "level": f.get("level")} for f in b["floors"]]}
                          for b in stored["buildings"]]}


def _save_site(data):
    _write(folder() / "site.json", data)
    _cache.pop(("site", str(folder())), None)


def _next_id(prefix, used):
    numbers = [int(x[len(prefix):]) for x in used if re.fullmatch(prefix + r"\d+", x)]
    return f"{prefix}{max(numbers + [0]) + 1}"


def _check_names(name, code=None, level=None):
    errors = []
    if not _name_ok(name):
        errors.append({"key": "site.err_title", "values": {"max": NAME_MAX}})
    if code is not None and code != "" and not CODE.fullmatch(str(code)):
        errors.append({"key": "site.err_code", "values": {}})
    if level is not None and not (isinstance(level, int) and not isinstance(level, bool) and -10 <= level <= 300):
        errors.append({"key": "site.err_level", "values": {}})
    if errors:
        raise Invalid(errors)


def add_building(name, code="", floor_name="Level 1"):
    """A new building with one empty floor (floor_name: "Level 1" in the admin's language). Returns (building_id, floor_id)."""
    with _lock:
        _check_names(name, code)
        data = _site_for_write()
        building_id = _next_id("b", [b["id"] for b in data["buildings"]])
        floor_id = _next_id("f", [f["id"] for b in data["buildings"] for f in b["floors"]])
        data["buildings"].append({"id": building_id, "name": name.strip(), "code": (code or "").strip(),
                                  "floors": [{"id": floor_id, "name": floor_name, "level": 1}]})
        _save_site(data)
        return building_id, floor_id


def add_floor(building_id, name, level):
    """A new, empty floor in a building. Returns its ID."""
    with _lock:
        if building_id == EXAMPLE_ID:
            raise ReadOnly(building_id)
        _check_names(name, level=level)
        data = _site_for_write()
        b = next((x for x in data["buildings"] if x["id"] == building_id), None)
        if b is None:
            raise NotFound(building_id)
        floor_id = _next_id("f", [f["id"] for x in data["buildings"] for f in x["floors"]])
        b["floors"].append({"id": floor_id, "name": name.strip(), "level": level})
        b["floors"].sort(key=lambda f: (f["level"] if f["level"] is not None else _level_of(f["name"] or ""), f["id"]))
        _save_site(data)
        return floor_id


def rename_building(building_id, name, code=None):
    with _lock:
        if building_id == EXAMPLE_ID:
            raise ReadOnly(building_id)
        _check_names(name, code)
        data = _site_for_write()
        b = next((x for x in data["buildings"] if x["id"] == building_id), None)
        if b is None:
            raise NotFound(building_id)
        old = {"name": b["name"], "code": b["code"]}
        b["name"] = name.strip()
        if code is not None:
            b["code"] = code.strip()
        _save_site(data)
        return old


def rename_floor(floor_id, name, level=None):
    with _lock:
        if is_example(floor_id):
            raise ReadOnly(floor_id)
        _check_names(name, level=level)
        data = _site_for_write()
        f = next((x for b in data["buildings"] for x in b["floors"] if x["id"] == floor_id), None)
        if f is None:
            raise NotFound(floor_id)
        old = {"name": f["name"], "level": f["level"]}
        f["name"] = name.strip()
        if level is not None:
            f["level"] = level
        _save_site(data)
        return old


def store_image(cleaned, ext):
    """Keep an already cleaned image under its content hash. Returns its name."""
    import hashlib

    name = f"{hashlib.sha256(cleaned).hexdigest()}.{ext}"
    path = folder() / "images" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(cleaned)
        os.replace(tmp, path)
    return name
