"""The floor plans as the rest of the server sees them: one merged, current view over every floor of every real
building (server/site.py; the example building is left out). PLAN keeps the shape of dashboard/plan.json, so the
nearest exit of each room, the stair names the chat may use, the known rooms and the name a room goes by when
ROOM_NAMES has no entry for it all follow the saved plans. refresh() rebuilds it after every save.

With nothing saved (an empty SITE_DIR), PLAN is dashboard/plan.json, exactly as before."""
from server import site

PLAN = {}        # merged view: viewBox, outline, corridor (default floor), rooms (each with its "floor"), exits, other
_FLOORS = {}     # floor ID -> that floor's plan


def refresh():
    """Re-read every real floor's current plan. A site folder that cannot be read leaves the built-in plan in force."""
    try:
        site.reset()
        plans = site.current_plans()
    except Exception as e:  # never stop the server over a bad file: the built-in plan still draws the default floor
        print(f"floor plans not read, using the built-in plan: {e}", flush=True)
        plans = {site.DEFAULT_FLOOR: site.builtin_plan()}
    first = plans.get(site.DEFAULT_FLOOR) or next(iter(plans.values()), site.builtin_plan())
    rooms, exits = {}, {}
    for floor_id, p in sorted(plans.items(), key=lambda kv: kv[0] != site.DEFAULT_FLOOR):
        for room_id, room in p.get("rooms", {}).items():
            rooms.setdefault(room_id, {**room, "floor": floor_id})
        for key, ex in p.get("exits", {}).items():
            exits[key if key not in exits else f"{floor_id}:{key}"] = ex
    _FLOORS.clear()
    _FLOORS.update(plans)
    PLAN.clear()
    PLAN.update({"viewBox": first.get("viewBox", [0, 0, *site.BOX]), "outline": first.get("outline"),
                 "corridor": first.get("corridor"), "rooms": rooms, "exits": exits, "other": first.get("other", [])})


def floor_of(room_id):
    """The floor a room is drawn on, or None."""
    room = PLAN["rooms"].get(room_id)
    return room["floor"] if room else None


def exit_label(ex, lang="en"):
    """"Stair A" / "Tangga A" for a built-in label, or the name an admin typed (shown as written in both languages)."""
    return site.label_of(ex, lang) or None


def exit_name(room_id, lang="en"):
    """Display name of the room's nearest stairwell ("Stair A" / "Tangga A"), or None if the room isn't on a plan."""
    room = PLAN["rooms"].get(room_id)
    ex = room and _FLOORS.get(room["floor"], {}).get("exits", {}).get(room.get("exit"))
    return exit_label(ex, lang) if ex else None


def room_names():
    """{"room1": "Lab 2", ...}: the names written on the plans. Used as they are in both languages, like ROOM_NAMES."""
    out = {}
    for room_id, room in PLAN["rooms"].items():
        name = str(room.get("name") or "").strip()
        if name:
            out[room_id] = name[:40]
    return out


def default_floor_rooms():
    """The rooms on the default floor, in plan order (the demo story plays there)."""
    return list(_FLOORS.get(site.DEFAULT_FLOOR, {}).get("rooms", {}))


refresh()
