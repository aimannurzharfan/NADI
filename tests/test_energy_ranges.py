"""The Energy page's period (GET /api/energy?range=today|7d|30d): totals in RM, kWh and CO2 for the period and the
period of the same length before it, RM per room and RM per hour (today) or per day (7 and 30 days). Days with no
waste are 0, days before the first report are None, and each part of a stretch keeps the rate in force while it ran.
sqlite3 stands in for MySQL (the first report and the saved settings); Redis is the in-memory one of every test."""
import time

import pytest

from server import energy, main, store, timeutil
from tests.test_energy_settings import api, db, new  # noqa: F401  (db is a fixture)

NOW = 1_800_000_000  # 4 pm Malaysia time
MIDNIGHT = timeutil.midnight(NOW)


@pytest.fixture
def clock(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(main, "refresh_live", lambda now, lang=None: None)
    monkeypatch.setattr(main, "_last", {**main._last, "rooms": []})
    monkeypatch.setattr(main, "_first_report", {"at": -1e9, "ts": None, "known": False})
    return db


def first_report(db, ts):  # noqa: F811
    db.db.execute("INSERT INTO occupancy (room_id, ts, motion_std, source) VALUES ('room1', ?, 0.1, 'recv-1')", (ts,))


def day_total(days_ago, rm, room_id="room1"):
    """A stretch that ended at noon that many days ago, stored in RM, kWh (RM / 0.2983) and CO2."""
    ts = MIDNIGHT - days_ago * 86400 + 12 * 3600
    store.add_waste_today(rm, ts, room_id, rm / 0.2983, rm / 0.2983 * 0.75)


def energy_range(rng):
    out = api().get(f"/api/energy?range={rng}")
    assert out.status_code == 200, out.text
    return out.json()["range"]


def test_thirty_days_add_up_and_are_set_against_the_thirty_before(clock):
    first_report(clock, NOW - 70 * 86400)
    for d in range(65):
        day_total(d, 1.0 if d < 30 else 0.5, "room1" if d % 2 else "room2")
    out = energy_range("30d")
    assert out["id"] == "30d" and out["days"] == 30
    assert out["total"]["rm"] == pytest.approx(30.0) and out["total"]["kwh"] == pytest.approx(30 / 0.2983, abs=0.1)
    assert out["total"]["co2_kg"] == pytest.approx(30 / 0.2983 * 0.75, abs=0.1)
    assert out["previous"]["rm"] == pytest.approx(15.0)  # days 30 to 59 only: day 60 and older are not in it
    points = out["series"]["points"]
    assert out["series"]["unit"] == "day" and len(points) == 30
    assert points[0]["day"] == timeutil.day(MIDNIGHT - 29 * 86400) and points[-1]["day"] == timeutil.day(NOW)
    assert all(p["rm"] == 1.0 for p in points)
    rooms = {r["room_id"]: r["rm"] for r in out["by_room"]}
    assert rooms["room1"] == 15.0 and rooms["room2"] == 15.0


def test_days_without_waste_are_zero_and_days_before_the_first_report_are_empty(clock):
    first_report(clock, MIDNIGHT - 3 * 86400 + 9 * 3600)  # 9 am three days ago
    day_total(1, 2.5)
    out = energy_range("30d")
    rm = [p["rm"] for p in out["series"]["points"]]
    assert rm[:26] == [None] * 26  # before the first report: nothing to show
    assert rm[26:] == [0.0, 0.0, 2.5, 0.0]  # the day of the first report counts, later days without waste are 0
    assert out["previous"] is None  # nothing was reported in the 30 days before
    assert out["total"]["rm"] == 2.5
    assert energy_range("7d")["previous"] is None
    clock.db.execute("DELETE FROM occupancy")
    main._first_report["at"] = -1e9
    first_report(clock, NOW - 10 * 86400)
    day_total(8, 1.25)
    week = energy_range("7d")
    assert week["previous"] == {"rm": 1.25, "kwh": pytest.approx(4.2), "co2_kg": pytest.approx(3.1)}
    assert week["total"]["rm"] == 2.5 and [p["rm"] for p in week["series"]["points"]] == [0.0] * 5 + [2.5, 0.0]


def test_today_is_per_hour_with_each_part_at_its_own_rate(clock):
    first_report(clock, NOW - 5 * 86400)
    energy.save(new(tariff_rm_per_kwh=0.5), "admin", MIDNIGHT + 14 * 3600)  # the tariff changes at 2 pm
    # empty with the air conditioning on from 1 pm to 3:30 pm: one hour before the change, 1.5 hours after it
    energy.add_ended(energy.ended(MIDNIGHT + 13 * 3600, None, MIDNIGHT + 15 * 3600 + 1800, "room1"),
                     MIDNIGHT + 15 * 3600 + 1800, "room1")
    out = energy_range("today")
    hours = [p["rm"] for p in out["series"]["points"]]
    assert out["series"]["unit"] == "hour" and len(hours) == 24
    assert hours[13] == pytest.approx(2.98) and hours[14] == pytest.approx(5.0) and hours[15] == pytest.approx(2.5)
    assert hours[:13] == [0.0] * 13 and hours[16] == 0.0 and hours[17:] == [None] * 7  # later today: not yet
    assert out["total"]["rm"] == pytest.approx(10.48)
    assert out["total"]["kwh"] == pytest.approx(25.0) and out["total"]["co2_kg"] == pytest.approx(18.8, abs=0.1)
    assert sum(h for h in hours if h) == pytest.approx(out["total"]["rm"], abs=0.01)
    assert out["previous"] == {"rm": 0.0, "kwh": 0.0, "co2_kg": 0.0}  # yesterday
    day_total(1, 3.0)
    assert energy_range("today")["previous"]["rm"] == 3.0


def test_a_running_stretch_counts_in_its_hours_today_and_in_the_room(clock, monkeypatch):
    first_report(clock, NOW - 5 * 86400)
    store.r.sadd("rooms", "room1")
    store.r.hset("room:room1", mapping={"headcount": 0, "count_ts": NOW, "temp_c": 22.0, "temp_ts": NOW,
                                        "empty_cold_since": NOW - 5400})  # since 2:30 pm, still running
    monkeypatch.setattr(main, "_last", {**main._last, "rooms": store.rooms()})
    out = energy_range("today")
    hours = [p["rm"] for p in out["series"]["points"]]
    assert hours[14] == pytest.approx(1.49, abs=0.01) and hours[15] == pytest.approx(2.98, abs=0.01)
    assert out["total"]["rm"] == pytest.approx(4.47, abs=0.01)
    assert {r["room_id"]: r["rm"] for r in out["by_room"]}["room1"] == pytest.approx(4.47, abs=0.01)
    assert energy_range("30d")["series"]["points"][-1]["rm"] == pytest.approx(4.47, abs=0.01)


def test_mysql_offline_leaves_no_day_out(clock):
    clock.down = True
    day_total(20, 1.0)
    out = energy_range("30d")
    assert out["series"]["points"][9]["rm"] == 1.0 and out["first_ts"] is None
    assert out["previous"] == {"rm": 0.0, "kwh": 0.0, "co2_kg": 0.0}


def test_the_older_fields_stay_and_a_bad_range_is_refused(clock):
    out = api().get("/api/energy").json()
    assert out["range"]["id"] == "7d" and {"today", "week", "previous_week", "by_room", "daily"} <= set(out)
    for bad in ("90d", "1h", "", "today;"):
        assert api().get(f"/api/energy?range={bad}").status_code == 422, bad


def test_day_totals_are_kept_long_enough_for_thirty_days_and_the_thirty_before():
    assert store.waste_keep_s() >= 61 * 86400


def test_rooms_carry_kwh_and_hours_and_a_room_filters_the_day_series(clock):
    first_report(clock, NOW - 20 * 86400)
    day_total(1, 2.983, "room1")  # 10 kWh at RM 0.2983: one hour of a 10 kW air conditioner
    day_total(2, 5.966, "room2")
    out = energy_range("7d")
    rooms = {r["room_id"]: r for r in out["by_room"]}
    assert rooms["room1"]["kwh"] == pytest.approx(10.0) and rooms["room1"]["hours"] == pytest.approx(1.0)
    assert rooms["room2"]["kwh"] == pytest.approx(20.0) and rooms["room2"]["hours"] == pytest.approx(2.0)
    assert out["series_room"] is None and sum(p["rm"] for p in out["series"]["points"]) == pytest.approx(8.95, abs=0.01)
    one = api().get("/api/energy?range=7d&room=room1").json()["range"]
    assert one["series_room"] == "room1"
    assert [p["rm"] for p in one["series"]["points"]] == [0.0, 0.0, 0.0, 0.0, 0.0, 2.98, 0.0]
    assert one["total"] == out["total"] and one["by_room"] == out["by_room"]  # the figures and the list stay the building's
    assert api().get("/api/energy?range=7d&room=nowhere").status_code == 422


def test_hours_use_the_rooms_own_power(clock):
    first_report(clock, NOW - 20 * 86400)
    energy.save(new(ac_kw_rooms={"room2": 5.0}), "admin", MIDNIGHT - 10 * 86400)
    day_total(1, 2.983, "room2")  # 10 kWh from a 5 kW unit: two hours
    rooms = {r["room_id"]: r for r in energy_range("7d")["by_room"]}
    assert rooms["room2"]["hours"] == pytest.approx(2.0)


def test_todays_hours_are_also_kept_per_room(clock):
    first_report(clock, NOW - 86400)
    energy.add_ended({"rm": 1.0, "kwh": 3.0, "co2_kg": 2.0, "since": NOW - 5400}, NOW, "room1")   # 14:30 to 16:00
    energy.add_ended({"rm": 0.5, "kwh": 1.5, "co2_kg": 1.0, "since": NOW - 1800}, NOW, "room2")   # 15:30 to 16:00
    hour = lambda out, h: out["series"]["points"][h]["rm"]  # noqa: E731
    both = energy_range("today")
    one = api().get("/api/energy?range=today&room=room1").json()["range"]
    two = api().get("/api/energy?range=today&room=room2").json()["range"]
    assert hour(one, 14) > 0 and hour(one, 15) > 0 and hour(two, 14) == 0 and hour(two, 15) > 0
    assert hour(both, 15) == pytest.approx(hour(one, 15) + hour(two, 15), abs=0.011)
    assert hour(both, 14) == pytest.approx(hour(one, 14), abs=0.011)
