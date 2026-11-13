"""Pure rules (no Redis/MySQL) so they can be unit tested: headcount, air conditioning waste, chat fallback."""
import os
import re

from server.plan import PLAN, exit_label, exit_name
from server.strings import t

THRESHOLDS = [float(x) for x in os.getenv("HEADCOUNT_THRESHOLDS", "0.35,0.95,1.55").split(",")]
# The four values below are the defaults until an admin saves energy settings in the console (server/energy.py)
AC_KW = float(os.getenv("AC_KW", "10"))
TARIFF_RM_PER_KWH = float(os.getenv("TARIFF_RM_PER_KWH", "0.2983"))
AC_ON_BELOW_C = 26.0      # colder than this = air conditioning assumed on
WASTE_AFTER_S = int(float(os.getenv("WASTE_MINUTES", "10")) * 60)  # empty + cold for longer than this = flag
WASTE_ALERT_EVERY_S = 3600


def headcount(p, thresholds=THRESHOLDS):
    """Threshold rule until the model exists: count thresholds that motion_std exceeds.
    With 3 thresholds this gives 0, 1, 2 or 3 (meaning 3+)."""
    motion = float(p.get("motion_std") or 0)
    return sum(motion > t for t in thresholds)


# --- air conditioning waste ---

def update_empty_cold_since(since, headcount, temp_c, now, below_c=None):
    """Start time of the current 'empty with air conditioning on' stretch, or None if the room isn't in that state.
    below_c: the temperature below which the air conditioning counts as on (the live energy setting)."""
    if headcount == 0 and temp_c is not None and temp_c < (AC_ON_BELOW_C if below_c is None else below_c):
        return since or now
    return None


def waste_info(since, now, ac_kw=AC_KW, tariff=TARIFF_RM_PER_KWH, after_s=None):
    """Flag after WASTE_MINUTES. RM counts from when the room first went empty with the air conditioning on."""
    after_s = WASTE_AFTER_S if after_s is None else after_s  # read now: demo mode shortens it
    if since is None or now - since <= after_s:
        return None
    secs = now - since
    return {"since": since, "minutes": secs // 60, "rm": round(ac_kw * secs / 3600 * tariff, 2)}


def should_alert_waste(last_alert_ts, now):
    return last_alert_ts is None or now - last_alert_ts >= WASTE_ALERT_EVERY_S


def ended_waste_rm(old_since, new_since, now):
    """RM to add to today's total when an empty-with-air-conditioning-on stretch ends. Only flagged stretches count."""
    if old_since is None or new_since is not None:
        return 0.0
    w = waste_info(old_since, now)
    return w["rm"] if w else 0.0


# --- chat fallback (used when no LLM is configured or reachable). Wording lives in dashboard/strings.json ---

BM_WORDS = {"berapa", "bilik", "kosong", "orang", "ada", "adakah", "jumlah", "dalam", "mana", "yang", "penghawa",
            "dingin", "membazir", "pembaziran", "masih", "semua", "tiada", "berapakah", "siapa", "bangunan", "hidup",
            "apa", "apakah", "bagaimana", "ini", "itu", "di", "ke", "dan", "boleh", "sila", "tolong", "hari", "sekarang",
            "kecemasan", "penggera", "kebakaran"}
# what people type, not what NADI says: "aircon" and "AC" are still understood
WASTE_WORDS = (r"\b(air[\s-]?con\w*|conditioning|conditioner|ac|a/c|waste|wasted|wasting|penghawa|membazir"
               r"|pembaziran|rm)\b")
EMERGENCY_WORDS = r"\b(emergency|alarm|fire|evacuat\w*|kecemasan|penggera|kebakaran)\b"
FIRST_WORDS = (r"\b(first|priority|prioriti[sz]e|busiest|most people|rescuers?|dahulu|dulu|utamakan|keutamaan"
               r"|paling ramai)\b")
PEOPLE_WORDS = r"\b(total|how many|inside|people|anyone|berapa|jumlah|dalam|orang|ramai)\b"

HELP_EN = t("answer.help", "en")
HELP_BM = t("answer.help", "ms")
# rules whose answer is shown exactly as built, never rephrased: "first" is an ordered rescue list with a stair per
# room, and the reply check can't prove a rewrite kept that order and those room-stair links. "help" and "no_data"
# have nothing to rephrase, and an unmatched question must never get a free answer.
MODEL_FREE_RULES = {"help", "no_data", "first"}


def is_bm(question):
    return len(set(re.findall(r"[a-z]+", question.lower())) & BM_WORDS) >= 1


SHOWN_MAX = 100  # a room above this shows as "100+"


def is_lower_bound(r):
    """True if the room's count is a minimum: CSI's "3 or more". Rooms without the flag came from CSI (3 = 3+)."""
    if "at_least" in r:
        return bool(r["at_least"])
    return r.get("headcount") == 3


def shown(n, at_least=None):
    """How a count is shown: "3+" for a lower bound, "100+" above 100, else the number."""
    if n > SHOWN_MAX:
        return f"{SHOWN_MAX}+"
    if at_least is None:
        at_least = n == 3
    return f"{n}+" if at_least else str(n)


def count_of(r):
    return shown(r["headcount"], is_lower_bound(r))


def label(r):
    """Display name from ROOM_NAMES when set, else the room ID. Used as-is in both languages."""
    return r.get("name") or r["room_id"]


def squash(text):
    return re.sub(r"[\s_-]", "", text.lower())


def people_word(n, lang):
    return t("unit.person" if n == 1 else "unit.people", lang)


def minute_word(n, lang="en"):
    return t("unit.minute" if n == 1 else "unit.minutes", lang)


def join_names(names, lang):
    """["Lab 2", "Hall A", "Room 3"] -> "Lab 2, Hall A and Room 3" (or "dan" in Malay)."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + t("list.and", lang) + names[-1]


def _numbers(text):
    """Numbers with their "+": "3+" (3 or more) and "3" are different facts."""
    return set(re.findall(r"\d+(?:\.\d+)?\+?", text))


def _rooms_named(text, rooms):
    low = text.lower()
    return {r["room_id"] for r in rooms
            if any(re.search(r"(?<!\w)" + re.escape(n.lower()) + r"(?!\w)", low) for n in {label(r), r["room_id"]})}


# words that carry the meaning of an answer: the reply must use exactly the same ones as the checked answer
MEANING_WORDS = {"no", "not", "none", "nobody", "never", "zero", "empty", "vacant", "occupied", "on", "off", "all",
                 "every", "only", "more", "most", "less", "first", "active", "started",
                 "tiada", "tidak", "bukan", "belum", "tanpa", "kosong", "berpenghuni", "hidup", "mati", "aktif",
                 "semua", "setiap", "sahaja", "hanya", "lebih", "paling", "kurang", "dahulu", "berbunyi"}
ROOM_REF = re.compile(r"\b(?:room|rooms|bilik|lab|hall|dewan|makmal)\s+\d+\w*")


def _words(text):
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())


def _without_names(text, rooms):
    """Room names out of the way first: the 2 in "Lab 2" is part of a name, not a count."""
    low = text.lower()
    for n in sorted({x.lower() for r in rooms for x in (label(r), r["room_id"])}, key=len, reverse=True):
        low = re.sub(r"(?<!\w)" + re.escape(n) + r"(?!\w)", " roomname ", low)
    return low


def _number_pairs(text, rooms):
    """("3", "people"), ("2", "rooms"): each count with the word right after it, when there is one."""
    return set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)?) ([a-z]+)", _without_names(text, rooms)))


def _exits_named(text):
    """Stairwell names from the floor plans mentioned in text, in either language: "Stair A", "Tangga B"."""
    low = text.lower()
    return {key for key, ex in PLAN["exits"].items() for lang in ("en", "ms")
            if exit_label(ex, lang) and re.search(r"(?<!\w)" + re.escape(exit_label(ex, lang).lower()) + r"(?!\w)", low)}


def keeps_facts(checked, reply, rooms, lang="en"):
    """True only if a model's rephrasing keeps the meaning of the checked answer. Real qwen2.5:3b replies that this
    rejects: "1 person is inside, in Room 1." (no such room), "1 bilik kosong, tetapi ada 1 orang di dalam." (2 rooms
    were empty), "Bilik Lab 2 kosong dan Bilik 3 kosong." Checks:
    - exactly the same numbers and the same rooms: nothing dropped, nothing added
    - every "number word" pair survives ("2 rooms", "3 orang"), so a number can't move to another noun
    - the same meaning words (no, not, empty, occupied, on, off, all, kosong, tiada, ...), so the meaning can't
      flip: "No rooms are empty." must not become "No rooms are occupied."
    - no room reference such as "Room 1" or "Bilik 3" that isn't in the checked answer
    - in Malay, room names as-is: "Lab 2 kosong.", never "Bilik Lab 2"."""
    if _numbers(reply) != _numbers(checked) or _rooms_named(reply, rooms) != _rooms_named(checked, rooms):
        return False
    if _exits_named(reply) != _exits_named(checked):  # no stair dropped, added or swapped
        return False
    if not _number_pairs(checked, rooms) <= _number_pairs(reply, rooms):
        return False
    if set(_words(reply)) & MEANING_WORDS != set(_words(checked)) & MEANING_WORDS:
        return False
    if set(ROOM_REF.findall(_without_names(reply, rooms))) - set(ROOM_REF.findall(_without_names(checked, rooms))):
        return False
    if lang == "ms":
        for r in rooms:
            name = label(r).lower()
            if not name.startswith("bilik") and re.search(r"\bbilik\s+" + re.escape(name) + r"(?!\w)", reply.lower()):
                return False
    return True


def unknown_note(unknown, lang):
    """" 1 room is not reporting (count unknown): Lab 2." for rooms with no live count, or ""."""
    if not unknown:
        return ""
    return " " + t("answer.unknown_one" if len(unknown) == 1 else "answer.unknown_many", lang, n=len(unknown),
                   rooms=join_names([label(r) for r in unknown], lang))


def total_answer(live, lang, unknown=()):
    """People inside and how many rooms they are in (occupied rooms, not monitored rooms). Rooms not reporting
    make the total a minimum ("at least") and are named, never counted as empty."""
    total = sum(r["headcount"] for r in live)
    if total == 0 and not unknown:
        return t("answer.total_none", lang)
    plus = any(is_lower_bound(r) for r in live) or bool(unknown)  # a lower bound or an unknown room: a minimum
    occupied = sum(r["headcount"] > 0 for r in live)
    if total == 0:
        return t("answer.total_none_known", lang) + unknown_note(unknown, lang)
    return t("answer.total", lang, total=total, or_more=t("answer.or_more", lang) if plus else "",
             people=people_word(1 if total == 1 and not plus else 2, lang), rooms=occupied,
             room_word=t("unit.room" if occupied == 1 else "unit.rooms", lang)) + unknown_note(unknown, lang)


def _via(room_id, lang):
    exit_ = exit_name(room_id, lang)
    return t("answer.via", lang, exit=exit_) if exit_ else ""


def first_answer(rooms, emergency, lang):
    """Which room to check first. Normally the live room with the most people and its nearest stair. In emergency
    mode the full order, like the dashboard's "Go here first" list: offline rooms count with their last known number
    (safer for rescuers) and go first on a tie."""
    if emergency and emergency.get("on"):
        known = [r for r in rooms if r.get("headcount")]
        ranked = sorted(known, key=lambda r: (-r["headcount"], bool(r.get("live"))))
        if not ranked:
            return t("answer.first_none", lang)
        items = [t("answer.priority_item", lang, rank=i, name=label(r), count=count_of(r),
                   last_known="" if r.get("live") else t("answer.last_known", lang), via=_via(r["room_id"], lang))
                 for i, r in enumerate(ranked, 1)]
        return t("answer.priority", lang, rooms=", ".join(items))
    live = [r for r in rooms if r.get("live") and r.get("headcount")]
    if not live:
        return t("answer.first_none", lang)
    top = max(live, key=lambda r: r["headcount"])
    return t("answer.first", lang, name=label(top), count=count_of(top),
             people=people_word(top["headcount"], lang), via=_via(top["room_id"], lang))


def fallback_answer(question, rooms, emergency=None, now=None):
    """Rule-based answer text. See rule_answer."""
    return rule_answer(question, rooms, emergency, now)[1]


def rule_answer(question, rooms, emergency=None, now=None):
    """(rule, answer): which rule answered, and the answer in Malay when the question is in Malay, else English.
    rooms: dicts with room_id, name, headcount, temp_c, waste (None or waste_info dict), live (bool).
    emergency: {"on", "since"} or None. A question no rule matches gets rule "help", never a guess."""
    q = question.lower()
    lang = "ms" if is_bm(question) else "en"
    live = [r for r in rooms if r.get("live") and r.get("headcount") is not None]
    unknown = [r for r in rooms if not (r.get("live") and r.get("headcount") is not None)]
    if not live:
        return "no_data", t("answer.no_data", lang)

    # specific room by ID or display name: "room1", "room 1", "Hall A"; longest match wins so room10 beats room1
    squashed = squash(q)
    hits = [(len(key), r) for r in rooms for key in {squash(r["room_id"]), squash(label(r))} if key in squashed]
    if hits:
        r = max(hits, key=lambda h: h[0])[1]
        if not (r.get("live") and r.get("headcount") is not None):
            return "room", t("answer.room_offline", lang, name=label(r))
        temp = f", {r['temp_c']:.1f}°C" if r.get("temp_c") is not None else ""
        return "room", t("answer.room_count", lang, name=label(r), count=count_of(r),
                 people=people_word(r["headcount"], lang), temp=temp)

    if re.search(WASTE_WORDS, q):
        wasted = [r for r in live if r.get("waste")]
        if not wasted:
            return "waste", t("answer.waste_none", lang)
        parts = ", ".join(t("answer.waste_item", lang, name=label(r), minutes=r["waste"]["minutes"],
                            minute_word=minute_word(r["waste"]["minutes"], lang),
                            rm=f"{r['waste']['rm']:.2f}") for r in wasted)
        return "waste", t("answer.waste_list", lang, rooms=parts, total=f"{sum(r['waste']['rm'] for r in wasted):.2f}")

    if re.search(r"\b(empty|kosong|vacant|tiada orang)\b", q):
        empty = [label(r) for r in live if r["headcount"] == 0]
        return "empty", t("answer.empty_list", lang, rooms=join_names(empty, lang)) if empty else t("answer.empty_none", lang)

    if re.search(FIRST_WORDS, q):
        return "first", first_answer(rooms, emergency, lang)

    if re.search(EMERGENCY_WORDS, q):
        if not (emergency and emergency.get("on")):
            return "emergency", t("answer.emergency_off", lang)
        minutes = max(0, ((now or emergency["since"]) - emergency["since"]) // 60)
        key = "answer.drill_on" if emergency.get("drill") else "answer.emergency_on"
        return "emergency", t(key, lang, minutes=minutes, minute_word=minute_word(minutes, lang)) + " " + \
            total_answer(live, lang, unknown)

    if re.search(PEOPLE_WORDS, q):
        return "total", total_answer(live, lang, unknown)
    return "help", t("answer.help", lang)
