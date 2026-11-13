"""Energy settings an admin can change from the console: tariff, air conditioner power (one value, or one per
room), the temperature below which the air conditioning counts as on, the waste delay and the CO2 factor.

Every save is a new version with the time it took effect (MySQL table energy_settings). The cost of a waste stretch
is worked out piecewise over the versions, so a new rate applies from the second it is saved and never restates
what came before. With no version stored, the values from the server configuration (.env) apply.

The versions are kept in memory and re-read every RELOAD_S seconds. While MySQL is offline the versions in memory
stay in force; after a cold start without MySQL the configuration defaults apply until it is back.
"""
import json
import math
import os
import threading
import time

from server import health, logic, store, timeutil
from server.strings import t

CO2_KG_PER_KWH = float(os.getenv("CO2_KG_PER_KWH", "0.75"))  # grid emission factor: an estimate
NUMBERS = ("tariff_rm_per_kwh", "ac_kw", "ac_on_below_c", "waste_after_min", "co2_kg_per_kwh")
LIMITS = {"tariff_rm_per_kwh": (0.01, 5), "ac_kw": (0.1, 500), "ac_on_below_c": (16, 35), "waste_after_min": (1, 240),
          "co2_kg_per_kwh": (0.01, 2)}
LABELS = {"tariff_rm_per_kwh": ("es.tariff", "es.unit_tariff"), "ac_kw": ("es.ac_kw", "es.unit_kw"),
          "ac_on_below_c": ("es.ac_on_below", "es.unit_c"), "waste_after_min": ("es.waste_after", "es.unit_min"),
          "co2_kg_per_kwh": ("es.co2", "es.unit_co2")}
MAX_ROOMS = 100      # rooms with their own air conditioner power
HISTORY_SHOWN = 50
VERSIONS_KEPT = 500  # newest versions held in memory; older ones only matter for stretches older than them
RELOAD_S = 30
RATE_CHANGE_DAYS = 14

TABLE = """CREATE TABLE IF NOT EXISTS energy_settings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    effective_from INT NOT NULL,
    changed_by VARCHAR(64) NOT NULL,
    tariff_rm_per_kwh DOUBLE NOT NULL, ac_kw DOUBLE NOT NULL, ac_kw_rooms TEXT NOT NULL,
    ac_on_below_c DOUBLE NOT NULL, waste_after_min DOUBLE NOT NULL, co2_kg_per_kwh DOUBLE NOT NULL,
    INDEX (effective_from)
)"""
COLUMNS = "id, effective_from, changed_by, tariff_rm_per_kwh, ac_kw, ac_kw_rooms, ac_on_below_c, waste_after_min, co2_kg_per_kwh"

_lock = threading.Lock()
_state = {"versions": [], "total": 0, "loaded": False, "next": 0.0, "table": False}
delay_override_s = None  # the demo scenario flags waste after its own short delay while it runs


class Offline(Exception):
    """The change cannot be stored: MySQL is offline."""


def reset():
    """Forget what is in memory (tests, and after all data is deleted)."""
    with _lock:
        _state.update(versions=[], total=0, loaded=False, next=0.0, table=False)


def defaults():
    """The values from the server configuration. They apply until the first save and before it took effect."""
    return {"tariff_rm_per_kwh": logic.TARIFF_RM_PER_KWH, "ac_kw": logic.AC_KW, "ac_kw_rooms": {},
            "ac_on_below_c": logic.AC_ON_BELOW_C, "waste_after_min": logic.WASTE_AFTER_S / 60,
            "co2_kg_per_kwh": CO2_KG_PER_KWH}


def _rooms_kw(text):
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return {str(k): float(v) for k, v in value.items()} if isinstance(value, dict) else {}


def load():
    """Read the versions from MySQL into memory. A failure keeps what is in memory and marks MySQL offline."""
    with _lock:
        _state["next"] = time.monotonic() + RELOAD_S
        try:
            with store.mysql() as conn, conn.cursor() as cur:
                if not _state["table"]:  # MySQL may have been offline when the server created its tables
                    cur.execute(TABLE)
                    _state["table"] = True
                cur.execute("SELECT COUNT(*) FROM energy_settings")
                total = int(cur.fetchone()[0])
                cur.execute(f"SELECT {COLUMNS} FROM energy_settings ORDER BY effective_from DESC, id DESC LIMIT {VERSIONS_KEPT}")
                rows = cur.fetchall()
        except store.MYSQL_ERRORS as e:
            if health.ok("mysql"):
                print(f"energy settings not read, MySQL is offline: {e}", flush=True)
            health.mark("mysql", False)
            return False
        health.mark("mysql", True)
        versions = [{"id": int(row[0]), "effective_from": int(row[1]), "changed_by": str(row[2]),
                     "settings": {"tariff_rm_per_kwh": float(row[3]), "ac_kw": float(row[4]), "ac_kw_rooms": _rooms_kw(row[5]),
                                  "ac_on_below_c": float(row[6]), "waste_after_min": float(row[7]),
                                  "co2_kg_per_kwh": float(row[8])}} for row in reversed(rows)]
        _state.update(versions=versions, total=total, loaded=True)
        return True


def versions():
    """The stored versions, oldest first. Re-read from MySQL when RELOAD_S has passed and MySQL can be tried."""
    if time.monotonic() >= _state["next"] and health.should_try("mysql"):
        load()
    return _state["versions"]


def source():
    """"database": a stored version is in force. "defaults": none stored (or none read yet). "last_known": MySQL is
    offline and the versions read earlier stay in force."""
    if not _state["versions"]:
        return "defaults"
    return "database" if health.ok("mysql") else "last_known"


def current(now=None):
    """The settings in force at `now` (default: this moment)."""
    now = time.time() if now is None else now
    for v in reversed(versions()):
        if v["effective_from"] <= now:
            return v["settings"]
    return defaults()


def kw(settings, room_id=None):
    return settings["ac_kw_rooms"].get(room_id, settings["ac_kw"]) if room_id else settings["ac_kw"]


def periods(since, until):
    """[(start, end, settings)]: the stretch from since to until cut where a new version took effect."""
    line = [(-math.inf, defaults())] + [(v["effective_from"], v["settings"]) for v in versions()]
    out = []
    for i, (start, settings) in enumerate(line):
        end = line[i + 1][0] if i + 1 < len(line) else math.inf
        a, b = max(since, start), min(until, end)
        if b > a:
            out.append((a, b, settings))
    return out


def cost(since, until, room_id=None):
    """{"kwh", "rm", "co2_kg"} of an air conditioner running from since to until, each part at the values in
    force then: kW of the room x hours, x tariff, x CO2 factor."""
    kwh = rm = co2 = 0.0
    for a, b, s in periods(since, until):
        energy = kw(s, room_id) * (b - a) / 3600
        kwh += energy
        rm += energy * s["tariff_rm_per_kwh"]
        co2 += energy * s["co2_kg_per_kwh"]
    return {"kwh": kwh, "rm": rm, "co2_kg": co2}


def waste_after_s(now=None):
    """How long a room must be empty with the air conditioning on before it is flagged."""
    if delay_override_s is not None:
        return delay_override_s
    return current(now)["waste_after_min"] * 60


def waste(since, now, room_id=None):
    """None until the stretch is flagged; then when it began, its minutes and what it has cost so far."""
    if since is None or now - since <= waste_after_s(now):
        return None
    c = cost(since, now, room_id)
    return {"since": since, "minutes": int(now - since) // 60, "rm": round(c["rm"], 2), "kwh": round(c["kwh"], 2)}


def ended(old_since, new_since, now, room_id=None):
    """What to add to the day's totals when a stretch ends: {"rm", "kwh", "co2_kg", "since"}, or None when nothing
    ended or it was never flagged."""
    if old_since is None or new_since is not None or now - old_since <= waste_after_s(now):
        return None
    c = cost(old_since, now, room_id)
    return {"rm": round(c["rm"], 2), "kwh": round(c["kwh"], 3), "co2_kg": round(c["co2_kg"], 3), "since": old_since}


def hour_pieces(since, until, room_id=None):
    """[(start, rm)]: the stretch cut at each whole hour (Malaysia is a whole number of hours from UTC), each part
    at the values in force while it ran."""
    out, a = [], since
    while a < until:
        b = min(until, (int(a) // 3600 + 1) * 3600)
        out.append((a, cost(a, b, room_id)["rm"]))
        a = b
    return out


def _derived(rm, at):
    """kWh and CO2 of an amount stored in RM only, at the values in force at `at`."""
    s = current(at)
    kwh = rm / s["tariff_rm_per_kwh"] if s["tariff_rm_per_kwh"] else 0.0
    return kwh, kwh * s["co2_kg_per_kwh"]


def add_ended(amounts, now, room_id=None):
    """Add an ended stretch to today's totals in RM, kWh and CO2. A total that so far holds RM only (stored before
    kWh and CO2 were kept) first gets the kWh and CO2 of that RM, so the three stay in step."""
    if not amounts:
        return
    for scope in (None, room_id) if room_id else (None,):
        rm = store.waste_day(now, 0, scope)
        if rm > 0 and store.waste_day_extra(now, 0, scope)[0] is None:
            kwh, co2 = _derived(rm, now)
            store.seed_waste_extra(now, scope, kwh, co2)
    store.add_waste_today(amounts["rm"], now, room_id, amounts["kwh"], amounts["co2_kg"])
    if amounts.get("since") is not None:  # the Energy page's "Today" chart: each part in the hour it ran
        store.add_waste_hours(hour_pieces(amounts["since"], now, room_id), room_id)


def day_amounts(now, days_ago=0, room_id=None):
    """{"rm", "kwh", "co2_kg"} of the stretches that ended on that day (unrounded). A day stored in RM only gets its
    kWh from the tariff, and its CO2 from the factor, in force at the end of that day."""
    rm = store.waste_day(now, days_ago, room_id)
    kwh, co2 = store.waste_day_extra(now, days_ago, room_id)
    if rm > 0 and (kwh is None or co2 is None):
        end = now if days_ago == 0 else timeutil.midnight(now - days_ago * 86400) + 86399
        d_kwh, d_co2 = _derived(rm, min(end, now))
        kwh, co2 = d_kwh if kwh is None else kwh, d_co2 if co2 is None else co2
    return {"rm": rm, "kwh": kwh or 0.0, "co2_kg": co2 or 0.0}


def room_days(now, days, room_ids):
    """{room_id: {"rm", "kwh", "hours"}} over the last `days` days (today included) from the stored day totals. A day
    stored in RM only gets its kWh from the tariff in force at the end of that day. Hours: each day's kWh divided
    by the room's air conditioner power in force at the end of that day."""
    rm = store.waste_days_rm(now, days, room_ids)
    kwh = store.waste_days_kwh(now, days, room_ids)
    out = {}
    for room_id in rm:
        total = {"rm": 0.0, "kwh": 0.0, "hours": 0.0}
        for i, day_rm in enumerate(rm[room_id]):
            days_ago = days - 1 - i
            end = now if days_ago == 0 else timeutil.midnight(now - days_ago * 86400) + 86399
            day_kwh = kwh[room_id][i]
            if day_kwh is None:
                day_kwh = _derived(day_rm, end)[0] if day_rm > 0 else 0.0
            power = kw(current(end), room_id)
            total["rm"] += day_rm
            total["kwh"] += day_kwh
            total["hours"] += day_kwh / power if power else 0.0
        out[room_id] = total
    return out


def rate_changes(now):
    """Saves in the last RATE_CHANGE_DAYS days, oldest first: the Energy page says figures before them used the
    earlier values."""
    return [{"ts": v["effective_from"], "by": v["changed_by"]} for v in versions()
            if now - RATE_CHANGE_DAYS * 86400 <= v["effective_from"] <= now]


def _number(value):
    """value as a float, or None when it is not a plain finite number (true/false and text are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _fmt(n):
    return f"{n:g}"


def check(body, known_rooms, lang="en", names=None):
    """(settings, errors): the cleaned settings and {} when the body is valid, else None and {field: message in
    lang}. All six fields are required, numbers only, each inside LIMITS; a room with its own power must be known."""
    errors, out = {}, {}
    body = body if isinstance(body, dict) else {}
    for key in NUMBERS:
        label, unit = t(LABELS[key][0], lang), t(LABELS[key][1], lang)
        low, high = LIMITS[key]
        n = _number(body.get(key))
        if n is None:
            errors[key] = t("es.err_number", lang, label=label)
        elif not low <= n <= high:
            errors[key] = t("es.err_range", lang, label=label, min=_fmt(low), max=_fmt(high), unit=unit)
        else:
            out[key] = round(n, 4)
    rooms = body.get("ac_kw_rooms")
    low, high = LIMITS["ac_kw"]
    if not isinstance(rooms, dict):
        errors["ac_kw_rooms"] = t("es.err_number", lang, label=t("es.ac_kw_room", lang))
    elif len(rooms) > MAX_ROOMS:
        errors["ac_kw_rooms"] = t("es.err_too_many", lang, n=MAX_ROOMS)
    else:
        out["ac_kw_rooms"] = {}
        for room_id, value in rooms.items():
            n = _number(value)
            shown = str(room_id)[:32]
            if not isinstance(room_id, str) or room_id not in known_rooms:
                errors[f"ac_kw_rooms.{shown}"] = t("es.err_room", lang, room=shown)
            elif n is None:
                errors[f"ac_kw_rooms.{shown}"] = t("es.err_number", lang, label=(names or {}).get(room_id, shown))
            elif not low <= n <= high:
                errors[f"ac_kw_rooms.{shown}"] = t("es.err_range", lang, label=(names or {}).get(room_id, shown),
                                                   min=_fmt(low), max=_fmt(high), unit=t("es.unit_kw", lang))
            else:
                out["ac_kw_rooms"][room_id] = round(n, 4)
    return (None, errors) if errors else (out, {})


def changes(old, new):
    """{field: [old, new]} for every value that differs; a room's own power is "ac_kw_rooms.<room>" with None for
    "not set"."""
    out = {k: [old[k], new[k]] for k in NUMBERS if not math.isclose(old[k], new[k], rel_tol=0, abs_tol=1e-9)}
    for room_id in sorted(set(old["ac_kw_rooms"]) | set(new["ac_kw_rooms"])):
        a, b = old["ac_kw_rooms"].get(room_id), new["ac_kw_rooms"].get(room_id)
        if a != b and (a is None or b is None or not math.isclose(a, b, rel_tol=0, abs_tol=1e-9)):
            out[f"ac_kw_rooms.{room_id}"] = [a, b]
    return out


def save(settings, who, now):
    """Store `settings` (already checked) as the version in force from `now`. Returns the changes against the values
    in force before, {} when nothing differs (then nothing is stored). Raises Offline when MySQL cannot store it."""
    if not health.should_try("mysql") or not load():  # the newest stored values, not a copy up to 30 s old
        raise Offline()
    diff = changes(current(now), settings)
    if not diff:
        return {}
    try:
        with store.mysql() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO energy_settings (effective_from, changed_by, tariff_rm_per_kwh, ac_kw, ac_kw_rooms,"
                        " ac_on_below_c, waste_after_min, co2_kg_per_kwh) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (int(now), str(who)[:64], settings["tariff_rm_per_kwh"], settings["ac_kw"],
                         json.dumps(settings["ac_kw_rooms"], sort_keys=True), settings["ac_on_below_c"],
                         settings["waste_after_min"], settings["co2_kg_per_kwh"]))
    except store.MYSQL_ERRORS as e:
        health.mark("mysql", False)
        raise Offline() from e
    if not load():
        raise Offline()
    return diff


def view(now):
    """What GET /api/energy/settings answers: the values in force, where they come from, the limits and the change
    history (newest first, each with what it changed against the version before)."""
    all_versions = versions()
    latest = next((v for v in reversed(all_versions) if v["effective_from"] <= now), None)
    history, before = [], defaults()
    for v in all_versions:
        history.append({"id": v["id"], "effective_from": v["effective_from"], "changed_by": v["changed_by"],
                        "settings": v["settings"], "changes": changes(before, v["settings"])})
        before = v["settings"]
    return {"now": now, "settings": latest["settings"] if latest else defaults(),
            "effective_from": latest["effective_from"] if latest else None,
            "changed_by": latest["changed_by"] if latest else None,
            "source": source(), "database": health.ok("mysql"),
            "limits": {k: list(v) for k, v in LIMITS.items()}, "max_rooms": MAX_ROOMS,
            "history": history[::-1][:HISTORY_SHOWN], "history_total": max(_state["total"], len(history))}
