"""Unit tests for the pure rules in server/logic.py (no Redis/MySQL needed)."""
from server import logic

T = [0.35, 0.95, 1.55]
NOW = 1_800_000_000


# --- headcount ---

def test_headcount_levels():
    assert logic.headcount({"motion_std": 0.05}, T) == 0
    assert logic.headcount({"motion_std": 0.65}, T) == 1
    assert logic.headcount({"motion_std": 1.25}, T) == 2
    assert logic.headcount({"motion_std": 3.0}, T) == 3


def test_headcount_boundary_and_missing():
    assert logic.headcount({"motion_std": 0.35}, T) == 0  # must exceed, not equal
    assert logic.headcount({}, T) == 0
    assert logic.headcount({"motion_std": None}, T) == 0


# --- aircon waste ---

def test_empty_cold_starts_and_keeps_timer():
    assert logic.update_empty_cold_since(None, 0, 24.0, NOW) == NOW
    assert logic.update_empty_cold_since(NOW - 300, 0, 24.0, NOW) == NOW - 300


def test_timer_resets_when_occupied_warm_or_no_temp():
    assert logic.update_empty_cold_since(NOW - 300, 1, 24.0, NOW) is None
    assert logic.update_empty_cold_since(NOW - 300, 0, 26.0, NOW) is None  # 26 C is not "below 26"
    assert logic.update_empty_cold_since(NOW - 300, 0, None, NOW) is None


def test_waste_flag_only_after_10_minutes():
    assert logic.waste_info(None, NOW, after_s=600) is None
    assert logic.waste_info(NOW - 600, NOW, after_s=600) is None  # exactly 10 min: not yet
    w = logic.waste_info(NOW - 601, NOW, after_s=600)
    assert w is not None and w["minutes"] == 10


def test_waste_rm_figure():
    # 10 kW for 1 hour at RM0.2983/kWh = RM2.98
    assert logic.waste_info(NOW - 3600, NOW, ac_kw=10, tariff=0.2983, after_s=600)["rm"] == 2.98


def test_waste_alert_once_per_hour():
    assert logic.should_alert_waste(None, NOW)
    assert not logic.should_alert_waste(NOW - 3599, NOW)
    assert logic.should_alert_waste(NOW - 3600, NOW)


# --- chat fallback ---

def rooms():
    waste = {"since": NOW - 1200, "minutes": 20, "rm": 0.99}
    return [
        {"room_id": "room1", "headcount": 2, "temp_c": 24.5, "live": True, "waste": None},
        {"room_id": "room2", "headcount": 0, "temp_c": 23.8, "live": True, "waste": waste},
        {"room_id": "room3", "headcount": 0, "temp_c": 29.0, "live": True, "waste": None},
        {"room_id": "room10", "headcount": 1, "temp_c": 25.0, "live": True, "waste": None},
        {"room_id": "lab", "headcount": 4, "temp_c": None, "live": False, "waste": None},
    ]


def test_chat_total_english_and_bm():
    # counts occupied rooms (room1, room10), not monitored rooms; the offline room makes the total a minimum
    assert logic.fallback_answer("How many people are inside?", rooms()) ==         "3 or more people inside, in 2 rooms. 1 room is not reporting, so its count is unknown: lab."
    assert logic.fallback_answer("Berapa orang di dalam?", rooms()) == "3 orang atau lebih di dalam, di 2 bilik. 1 bilik tidak menghantar data, jadi bilangannya tidak diketahui: lab."
    live = [r for r in rooms() if r["live"]]
    assert logic.fallback_answer("How many people are inside?", live) == "3 people inside, in 2 rooms."
    assert logic.fallback_answer("Berapa orang di dalam?", live) == "3 orang di dalam, di 2 bilik."


def test_chat_total_with_3_plus_room():
    r = rooms()
    r[0]["headcount"] = 3
    assert logic.fallback_answer("total inside?", r) == "4 or more people inside, in 2 rooms. 1 room is not reporting, so its count is unknown: lab."
    r = [x for x in r if x["live"]]
    assert logic.fallback_answer("total inside?", r) == "4 or more people inside, in 2 rooms."
    assert logic.fallback_answer("Berapa orang di dalam?", r) == "4 orang atau lebih di dalam, di 2 bilik."


def test_chat_total_when_nobody_inside():
    r = [dict(x, headcount=0) for x in rooms()]
    assert logic.fallback_answer("How many people are inside?", r) ==         "No one is inside the rooms that are reporting. 1 room is not reporting, so its count is unknown: lab."  # an offline room is unknown, never empty
    r = [x for x in r if x["live"]]
    assert logic.fallback_answer("How many people are inside?", r) == "No one is inside."
    assert logic.fallback_answer("Berapa orang di dalam?", r) == "Tiada orang di dalam."


def test_chat_specific_room():
    assert logic.fallback_answer("How many in room 1?", rooms()) == "room1: 2 people, 24.5°C."
    assert logic.fallback_answer("room10 now?", rooms()) == "room10: 1 person, 25.0°C."  # not room1
    assert logic.fallback_answer("Berapa orang dalam room1?", rooms()) == "room1: 2 orang, 24.5°C."
    assert "offline" in logic.fallback_answer("what about lab?", rooms())


def test_chat_empty_rooms():
    assert logic.fallback_answer("Which rooms are empty?", rooms()) == "Empty rooms: room2 and room3."
    assert logic.fallback_answer("Bilik mana kosong?", rooms()) == "room2 dan room3 kosong."


def test_chat_air_conditioning_waste():
    a = logic.fallback_answer("Is the air conditioning on in any empty room?", rooms())
    assert a == "Air conditioning is on in empty rooms: room2 (20 minutes, RM 0.99). RM 0.99 wasted so far."
    assert logic.fallback_answer("Is any aircon wasting power?", rooms()) == a  # typed shorthand still understood
    bm = logic.fallback_answer("Adakah penghawa dingin masih hidup di mana-mana bilik kosong?", rooms())
    assert bm == "Penghawa dingin masih hidup di bilik kosong: room2 (20 minit, RM 0.99). Sebanyak RM 0.99 telah dibazirkan setakat ini."


def test_chat_no_data_and_unknown_question():
    assert logic.fallback_answer("How many people?", []) == "There is no live room data at the moment."
    assert logic.fallback_answer("What's the weather?", rooms()) == logic.HELP_EN


def test_chat_uses_display_names():
    r = rooms()
    r[0]["name"], r[1]["name"] = "Lab 2", "Hall A"
    assert logic.fallback_answer("How many in Hall A?", r) == "Hall A: 0 people, 23.8°C."
    assert logic.fallback_answer("Berapa orang dalam lab 2?", r) == "Lab 2: 2 orang, 24.5°C."
    assert logic.fallback_answer("room1?", r) == "Lab 2: 2 people, 24.5°C."  # the ID still works
    assert logic.fallback_answer("Which rooms are empty?", r) == "Empty rooms: Hall A and room3."
    assert logic.fallback_answer("Bilik mana yang kosong?", r) == "Hall A dan room3 kosong."  # names as-is, no "Bilik"


def test_waste_today_counts_only_ended_flagged_stretches():
    assert logic.ended_waste_rm(None, None, NOW) == 0.0
    assert logic.ended_waste_rm(NOW - 3600, NOW - 3600, NOW) == 0.0  # still going
    assert logic.ended_waste_rm(NOW - 60, None, NOW) == 0.0  # ended before it was flagged
    assert logic.ended_waste_rm(NOW - 3600, None, NOW) == logic.waste_info(NOW - 3600, NOW)["rm"]


def test_keeps_facts_needs_exactly_the_same_rooms_and_numbers():
    r = rooms()
    r[0]["name"], r[1]["name"] = "Lab 2", "Hall A"
    assert logic.keeps_facts("Empty rooms: Hall A and room3.", "The empty rooms are room3 and Hall A.", r)
    assert not logic.keeps_facts("Empty rooms: Hall A and room3.", "Hall A is empty.", r)  # dropped a room
    assert not logic.keeps_facts("Empty rooms: Hall A.", "Hall A and Lab 2 are empty.", r)  # added a room
    assert not logic.keeps_facts("3 people inside, in 2 rooms.", "2 people are inside, in 2 rooms.", r)  # changed
    assert not logic.keeps_facts("3 people inside, in 2 rooms.", "3 people inside, in 2 rooms, 5 more coming.", r)
    assert logic.keeps_facts("3 orang di dalam, di 2 bilik.", "Terdapat 3 orang di dalam, di 2 bilik.", r, "ms")


def test_keeps_facts_rejects_bilik_before_a_room_name():
    r = rooms()
    r[0]["name"] = "Lab 2"
    assert logic.keeps_facts("Lab 2 kosong.", "Lab 2 kini kosong.", r, "ms")
    assert not logic.keeps_facts("Lab 2 kosong.", "Bilik Lab 2 kosong.", r, "ms")


def test_emergency_status_answer():
    on = {"on": True, "since": NOW - 300}
    assert logic.fallback_answer("Is emergency mode on?", rooms(), on, NOW) ==         "Emergency mode is on. The alarm started 5 minutes ago. 3 or more people inside, in 2 rooms. 1 room is not reporting, so its count is unknown: lab."
    assert logic.fallback_answer("Adakah mod kecemasan aktif?", rooms(), on, NOW).startswith(
        "Mod kecemasan sedang aktif. Penggera berbunyi 5 minit lalu.")
    assert logic.fallback_answer("Is there an emergency?", rooms(), {"on": False, "since": None}, NOW) ==         "Emergency mode is off."


def test_one_minute_is_singular():
    r = rooms()
    r[1]["waste"] = {"since": NOW - 70, "minutes": 1, "rm": 0.06}
    assert logic.fallback_answer("Is the air conditioning on in any empty room?", r) == \
        "Air conditioning is on in empty rooms: room2 (1 minute, RM 0.06). RM 0.06 wasted so far."


# --- "which room first" (nearest exit from dashboard/plan.json: room1 -> Stair B, room2 and room3 -> Stair A) ---

def first_rooms():
    return [
        {"room_id": "room1", "name": "Lab 2", "headcount": 1, "temp_c": 24.0, "live": True, "waste": None},
        {"room_id": "room2", "name": "Hall A", "headcount": 2, "temp_c": 24.0, "live": True, "waste": None},
        {"room_id": "room3", "name": "Room 3", "headcount": 3, "temp_c": 29.0, "live": False, "waste": None},
        {"room_id": "room9", "name": "Annex", "headcount": 1, "temp_c": None, "live": True, "waste": None},
    ]


def test_check_first_outside_emergency_is_busiest_live_room_with_stair():
    r = first_rooms()  # Room 3 has 3 but is offline: outside an emergency only live rooms count
    assert logic.fallback_answer("Which room should rescuers check first?", r) == "Check Hall A first: 2 people, via Stair A."
    assert logic.fallback_answer("Bilik mana perlu diperiksa dahulu?", r) == "Periksa Hall A dahulu: 2 orang, melalui Tangga A."
    assert logic.fallback_answer("Which room has the most people?", r).startswith("Check Hall A first")


def test_check_first_in_emergency_lists_full_priority_order():
    on = {"on": True, "since": NOW - 60}
    assert logic.fallback_answer("Which room should rescuers check first?", first_rooms(), on, NOW) == (
        "Emergency mode is on. Check the rooms in this order: 1. Room 3 (3+, last known count, via Stair A), "
        "2. Hall A (2, via Stair A), 3. Lab 2 (1, via Stair B), 4. Annex (1).")
    bm = logic.fallback_answer("Bilik mana perlu diperiksa dahulu?", first_rooms(), on, NOW)
    assert bm.startswith("Mod kecemasan sedang aktif. Periksa bilik mengikut susunan ini: "
                         "1. Room 3 (3+, bilangan terakhir diketahui, melalui Tangga A), 2. Hall A (2, melalui Tangga A)")
    assert "Annex (1)" in bm  # not on the floor plan: no stair named


def test_check_first_when_nobody_inside():
    r = [dict(x, headcount=0) for x in first_rooms()]
    assert logic.fallback_answer("Which room should rescuers check first?", r) == "No one is inside, so no room needs checking first."
    assert logic.fallback_answer("Bilik mana perlu diperiksa dahulu?", r, {"on": True, "since": NOW}, NOW) == \
        "Tiada orang di dalam, jadi tiada bilik yang perlu diperiksa dahulu."


def test_counts_above_3_and_100():
    assert logic.shown(3) == "3+" and logic.shown(3, False) == "3" and logic.shown(45) == "45"
    assert logic.shown(100) == "100" and logic.shown(101) == "100+" and logic.shown(2, True) == "2+"
    r = [{"room_id": "hall", "headcount": 150, "at_least": False, "temp_c": None, "live": True, "waste": None},
         {"room_id": "lab", "headcount": 3, "at_least": True, "temp_c": None, "live": True, "waste": None}]
    assert logic.fallback_answer("How many in hall?", r) == "hall: 100+ people."
    assert logic.fallback_answer("total inside?", r) == "153 or more people inside, in 2 rooms."
    r[1]["at_least"] = False
    assert logic.fallback_answer("total inside?", r) == "153 people inside, in 2 rooms."
