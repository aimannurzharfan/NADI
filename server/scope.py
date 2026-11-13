"""Which part of the site a chat question is about: one floor, or the whole building.

The scope is worked out before any rule runs, and the rules then see only that scope's rooms:
- emergency mode or a drill: the whole building, locked (and the answer gets a per-floor breakdown);
- a question that names a room: that room's floor (a room is the same room whatever floor the chip shows);
- a question that names a floor ("level 3", "floor 3", "aras 3", "tingkat 3"): that floor of the chip's building;
- otherwise the floor the viewer chose (the chip), or the whole building when none is chosen.

A floor with no sensors answers that it has none, and an example floor says it is example data; neither says 0
people. The scope's prefix ("Level 4: ", "Whole building: ") and the breakdown are added by chat.answer after any
model rewording has been checked, so a model can never drop or change them. CHAT_SCOPE=off: whole building, no prefix.
"""
import os
import re

from server import logic, plan, site
from server.strings import t

FLOOR_WORDS = re.compile(r"\b(?:level|floor|aras|tingkat)\s*(\d{1,3})\b", re.I)


def enabled():
    return os.getenv("CHAT_SCOPE", "on").strip().lower() not in ("off", "0", "false", "no")


def _floor_of(room_id):
    """The floor a room is drawn on; a reporting room on no plan belongs to the default floor."""
    return plan.floor_of(room_id) or site.DEFAULT_FLOOR


def _building_of(floor_id, lang):
    try:
        return site.floor_info(floor_id, lang)
    except site.NotFound:
        return None


def _floor_by_level(building, n):
    return next((f for f in building["floors"] if f.get("level") == n), None) or \
        next((f for f in building["floors"] if re.search(rf"(?<!\d){n}(?!\d)", f["name"])), None)


def resolve(question, chip_floor, data, lang):
    """{"kind": "floor" | "building", "floor_id", "label", "locked", "reason", "rooms", "fixed"}.
    rooms: the rooms the rules may use; fixed: an answer to give as it is (no sensors, example data, no such floor)."""
    rooms = data.get("rooms", [])
    em = data.get("emergency") or {}
    whole = {"kind": "building", "floor_id": None, "label": t("scope.whole", lang), "locked": False, "reason": None,
             "rooms": rooms, "fixed": None}
    if em.get("on"):
        return {**whole, "locked": True, "reason": t("scope.locked_drill" if em.get("drill") else "scope.locked_emergency", lang)}

    # a room named in the question: answer on its own floor
    rule, _ = logic.rule_answer(question, rooms, em, data.get("now"))
    if rule == "room":
        squashed = logic.squash(question.lower())
        named = [r for r in rooms for key in {logic.squash(r["room_id"]), logic.squash(logic.label(r))} if key in squashed]
        if named:
            chip_floor = _floor_of(max(named, key=lambda r: len(logic.label(r)))["room_id"])

    base = _building_of(chip_floor or site.DEFAULT_FLOOR, lang)
    m = FLOOR_WORDS.search(question)
    if m and base:
        building = base[0]
        found = _floor_by_level(building, int(m.group(1)))
        if not found:
            return {**whole, "kind": "floor", "label": building["name"],
                    "fixed": t("scope.no_such_floor", lang, n=m.group(1), building=building["name"])}
        chip_floor = found["id"]
        base = (building, found)
    if not chip_floor or not base:
        return whole

    building, floor = base
    scoped = [r for r in rooms if _floor_of(r["room_id"]) == floor["id"]]
    out = {"kind": "floor", "floor_id": floor["id"], "label": floor["name"], "locked": False, "reason": None,
           "rooms": scoped, "fixed": None}
    if building.get("example"):
        return {**out, "fixed": t("scope.example", lang)}
    if not scoped:
        drawn = site.plan(floor["id"])["plan"].get("rooms", {}) if not site.is_example(floor["id"]) else {}
        has_pair = any(r.get("link") for r in drawn.values())
        return {**out, "fixed": t("answer.no_data", lang) if has_pair else t("scope.no_sensors", lang)}
    return out


def breakdown(rooms, lang):
    """", by floor: Level 4: 3 people; Level 5: unknown." for an emergency or drill answer (every real floor with a
    reporting room, in plan order)."""
    by = {}
    for r in rooms:
        by.setdefault(_floor_of(r["room_id"]), []).append(r)
    parts = []
    for b in site.buildings(with_example=False, lang=lang):
        for f in b["floors"]:
            group = by.get(f["id"])
            if not group:
                continue
            live = [r for r in group if r.get("live") and r.get("headcount") is not None]
            if not live:
                parts.append(t("scope.floor_unknown", lang, floor=f["name"]))
                continue
            total = sum(r["headcount"] for r in live)
            at_least = any(logic.is_lower_bound(r) for r in live) or len(live) < len(group)
            parts.append(t("scope.floor_at_least" if at_least else "scope.floor_count", lang, floor=f["name"], count=total,
                           people=logic.people_word(2 if at_least else total, lang)))
    return t("scope.breakdown", lang, floors="; ".join(parts)) if parts else ""
