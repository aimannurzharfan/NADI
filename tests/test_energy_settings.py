"""Energy settings an admin changes in the console: who may read and change them, what is refused, how a change
applies from the second it is saved and never restates earlier figures, and what happens while MySQL is offline.
sqlite3 stands in for MySQL (the real INSERT and SELECT statements run); Redis is the in-memory one of every test."""
import time

import pymysql
import pytest
from fastapi.testclient import TestClient

from server import energy, health, logic, main, store, timeutil
from tests.test_scale import SqliteAsMysql
from tests.util import LOCAL_URL

TOKEN = "energy-token-0123456789"
WARDEN = "warden-token-0123456789"
H = {"X-Admin-Token": TOKEN}
T0 = 1_800_000_000  # 4 pm Malaysia time, far from midnight
DEFAULTS = {"tariff_rm_per_kwh": 0.2983, "ac_kw": 10.0, "ac_kw_rooms": {}, "ac_on_below_c": 26.0, "waste_after_min": 10.0,
            "co2_kg_per_kwh": 0.75}


class SettingsDb(SqliteAsMysql):
    """store.mysql() with the energy_settings table. `down = True` makes every connection fail like a stopped MySQL."""

    def __init__(self):
        import sqlite3

        self.down = False
        self.db = sqlite3.connect(":memory:", check_same_thread=False)  # the API answers from a worker thread
        self.db.execute("CREATE TABLE occupancy (room_id TEXT, ts INTEGER, motion_std REAL, source TEXT)")
        self.db.execute("CREATE TABLE climate (room_id TEXT, ts INTEGER, temp_c REAL, humidity REAL)")
        self.db.execute("CREATE TABLE energy_settings (id INTEGER PRIMARY KEY AUTOINCREMENT, effective_from INTEGER, "
                        "changed_by TEXT, tariff_rm_per_kwh REAL, ac_kw REAL, ac_kw_rooms TEXT, ac_on_below_c REAL, "
                        "waste_after_min REAL, co2_kg_per_kwh REAL)")

    def __enter__(self):
        if self.down:
            raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")
        return self

    def execute(self, sql, args=()):
        if sql.lstrip().startswith("CREATE TABLE"):  # MySQL wording; the table above is the same one for sqlite
            return 0
        return super().execute(sql, args)

    def saved(self):
        return self.db.execute("SELECT changed_by, tariff_rm_per_kwh FROM energy_settings ORDER BY id").fetchall()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("ADMIN_TOKENS", f"warden1:{WARDEN}")
    db = SettingsDb()
    monkeypatch.setattr(store, "mysql", lambda: db)
    energy.reset()  # read from this database from now on
    return db


def api(ip="192.168.1.40"):
    return TestClient(main.app, client=(ip, 5000), base_url=LOCAL_URL)


def new(**changes):
    return {**DEFAULTS, **changes}


# --- who may read and change ---

def test_everyone_reads_the_settings_and_only_an_admin_changes_them(db):
    out = api().get("/api/energy/settings")
    assert out.status_code == 200
    body = out.json()
    assert body["settings"] == DEFAULTS and body["source"] == "defaults" and body["database"] is True
    assert body["effective_from"] is None and body["changed_by"] is None and body["history"] == []
    assert body["limits"]["tariff_rm_per_kwh"] == [0.01, 5] and body["limits"]["waste_after_min"] == [1, 240]
    assert api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35)).status_code == 401  # no token
    assert api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35),
                     headers={"X-Admin-Token": "wrong-token-0123456789"}).status_code == 401
    assert db.saved() == []
    saved = api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    assert saved.status_code == 200 and saved.json()["changed"] is True
    assert saved.json()["settings"]["tariff_rm_per_kwh"] == 0.35 and saved.json()["source"] == "database"
    assert db.saved() == [("admin", 0.35)]
    seen = api().get("/api/energy/settings").json()  # a viewer sees the new values and who changed them
    assert seen["settings"]["tariff_rm_per_kwh"] == 0.35 and seen["changed_by"] == "admin" and seen["effective_from"]


@pytest.mark.parametrize("headers", [{"Origin": "http://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}])
def test_a_change_sent_from_another_website_is_refused(db, headers):
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    assert local.put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers={**H, **headers}).status_code == 403
    assert db.saved() == []


def test_the_31st_change_in_a_minute_is_refused(db):
    for _ in range(30):
        assert api().put("/api/energy/settings", json=DEFAULTS, headers=H).status_code == 200
    out = api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    assert out.status_code == 429 and out.headers["Retry-After"]
    assert db.saved() == []


def test_a_body_over_the_limit_is_refused(db):
    big = new(ac_kw_rooms={f"room{i}": 1.0 for i in range(400)})
    assert api().put("/api/energy/settings", json=big, headers=H).status_code == 413


# --- what is refused ---

@pytest.mark.parametrize("field,value,en,ms", [
    ("tariff_rm_per_kwh", -1, "Electricity tariff must be between 0.01 and 5 RM per kWh.",
     "Tarif elektrik mesti antara 0.01 dan 5 RM sekWj."),
    ("ac_kw", 0, "Air conditioner power must be between 0.1 and 500 kW.", "Kuasa penghawa dingin mesti antara 0.1 dan 500 kW."),
    ("ac_on_below_c", 60, "Air conditioning counts as on below must be between 16 and 35 °C.",
     "Penghawa dingin dikira hidup di bawah mesti antara 16 dan 35 °C."),
    ("waste_after_min", 0.5, "Waste flagged after must be between 1 and 240 minutes.",
     "Pembaziran ditanda selepas mesti antara 1 dan 240 minit."),
    ("co2_kg_per_kwh", 3, "CO2 factor must be between 0.01 and 2 kg per kWh.", "Faktor CO2 mesti antara 0.01 dan 2 kg sekWj."),
    ("tariff_rm_per_kwh", "0.35", "Electricity tariff must be a number.", "Tarif elektrik mesti berupa nombor."),
    ("ac_kw", True, "Air conditioner power must be a number.", "Kuasa penghawa dingin mesti berupa nombor."),
    ("waste_after_min", None, "Waste flagged after must be a number.", "Pembaziran ditanda selepas mesti berupa nombor."),
])
def test_a_value_outside_its_range_or_not_a_number_is_refused_in_the_page_language(db, field, value, en, ms):
    for lang, message in (("en", en), ("ms", ms)):
        out = api().put(f"/api/energy/settings?lang={lang}", json=new(**{field: value}), headers=H)
        assert out.status_code == 422
        assert out.json()["errors"] == {field: message} and out.json()["detail"] == message
    assert db.saved() == []


def test_every_field_is_required_and_all_messages_come_back_at_once(db):
    out = api().put("/api/energy/settings", json={"tariff_rm_per_kwh": 9}, headers=H)
    assert out.status_code == 422
    assert set(out.json()["errors"]) == {"tariff_rm_per_kwh", "ac_kw", "ac_on_below_c", "waste_after_min", "co2_kg_per_kwh",
                                         "ac_kw_rooms"}
    for bad in ([], "x", 5):
        assert api().put("/api/energy/settings", json=bad, headers=H).status_code == 422
    assert db.saved() == []


def test_a_room_with_its_own_power_must_be_known_and_in_range(db):
    out = api().put("/api/energy/settings", json=new(ac_kw_rooms={"room1": 3.5, "nowhere": 2, "room2": 900, "room3": "4"}),
                    headers=H)
    assert out.status_code == 422
    errors = out.json()["errors"]
    assert errors["ac_kw_rooms.nowhere"] == "nowhere is not a known room."
    assert errors["ac_kw_rooms.room2"] == "Hall A must be between 0.1 and 500 kW."
    assert errors["ac_kw_rooms.room3"] == "Room 3 must be a number."
    assert "ac_kw_rooms.room1" not in errors
    ms = api().put("/api/energy/settings?lang=ms", json=new(ac_kw_rooms={"nowhere": 2}), headers=H).json()["errors"]
    assert ms["ac_kw_rooms.nowhere"] == "nowhere bukan bilik yang dikenali."
    too_many = {f"r{i}": 1.0 for i in range(101)}
    out = api().put("/api/energy/settings", json=new(ac_kw_rooms=too_many), headers=H)
    assert out.status_code == 422 and out.json()["errors"] == {"ac_kw_rooms": "At most 100 rooms can have their own power."}
    ok = api().put("/api/energy/settings", json=new(ac_kw_rooms={"room1": 3.5}), headers=H)
    assert ok.status_code == 200 and ok.json()["settings"]["ac_kw_rooms"] == {"room1": 3.5}


# --- history, audit, saving the same values again ---

def test_history_is_newest_first_with_who_and_what_changed(db):
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35, ac_kw=12, ac_kw_rooms={"room1": 3.5}),
              headers={"X-Admin-Token": WARDEN})
    body = api().get("/api/energy/settings").json()
    assert [h["changed_by"] for h in body["history"]] == ["warden1", "admin"] and body["history_total"] == 2
    assert body["history"][0]["changes"] == {"ac_kw": [10.0, 12.0], "ac_kw_rooms.room1": [None, 3.5]}
    assert body["history"][1]["changes"] == {"tariff_rm_per_kwh": [0.2983, 0.35]}
    assert body["changed_by"] == "warden1" and body["settings"]["ac_kw"] == 12.0


def test_a_change_is_audit_logged_with_old_and_new_values(db):
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35, waste_after_min=1), headers=H)
    log = store.audit_log()
    assert len(log) == 1 and log[0]["action"] == "energy_settings" and log[0]["by"] == "admin"
    assert log[0]["ip"] == "192.168.1.40"
    assert log[0]["changes"] == {"tariff_rm_per_kwh": [0.2983, 0.35], "waste_after_min": [10.0, 1.0]}
    assert api().get("/api/audit", headers=H).json()["audit"][0]["changes"]["tariff_rm_per_kwh"] == [0.2983, 0.35]


def test_saving_the_same_values_changes_nothing(db):
    first = api().put("/api/energy/settings", json=DEFAULTS, headers=H).json()
    assert first["ok"] and first["changed"] is False and db.saved() == [] and store.audit_log() == []
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    again = api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H).json()
    assert again["changed"] is False and len(db.saved()) == 1 and len(store.audit_log()) == 1


# --- a change applies from the second it is saved ---

def test_a_stretch_across_one_change_costs_each_part_at_its_own_rate(db):
    energy.save(new(tariff_rm_per_kwh=0.5), "admin", T0)  # the tariff changes at T0
    c = energy.cost(T0 - 3600, T0 + 1800, "room1")        # an hour before, half an hour after
    assert c["kwh"] == pytest.approx(15.0)
    assert c["rm"] == pytest.approx(10 * 1.0 * 0.2983 + 10 * 0.5 * 0.5)
    assert c["co2_kg"] == pytest.approx(15.0 * 0.75)
    assert energy.cost(T0 - 7200, T0 - 3600)["rm"] == pytest.approx(2.983)  # wholly before: the old rate
    assert energy.cost(T0 + 3600, T0 + 7200)["rm"] == pytest.approx(5.0)    # wholly after: the new one


def test_a_stretch_across_two_changes_and_a_room_with_its_own_power(db):
    energy.save(new(tariff_rm_per_kwh=0.5), "admin", T0)
    energy.save(new(tariff_rm_per_kwh=0.5, co2_kg_per_kwh=0.6, ac_kw_rooms={"room1": 4.0}), "admin", T0 + 3600)
    c = energy.cost(T0 - 3600, T0 + 7200, "room1")  # one hour in each of the three versions
    assert c["kwh"] == pytest.approx(10 + 10 + 4)
    assert c["rm"] == pytest.approx(10 * 0.2983 + 10 * 0.5 + 4 * 0.5)
    assert c["co2_kg"] == pytest.approx(10 * 0.75 + 10 * 0.75 + 4 * 0.6)
    other = energy.cost(T0 - 3600, T0 + 7200, "room2")  # no power of its own: the building value throughout
    assert other["kwh"] == pytest.approx(30) and other["rm"] == pytest.approx(10 * 0.2983 + 20 * 0.5)
    assert energy.current(T0 - 1) == DEFAULTS and energy.current(T0)["tariff_rm_per_kwh"] == 0.5
    assert energy.current(T0 + 3600)["ac_kw_rooms"] == {"room1": 4.0}


def test_a_running_waste_flag_shows_the_piecewise_cost(db):
    energy.save(new(tariff_rm_per_kwh=0.5), "admin", T0)
    w = energy.waste(T0 - 3600, T0 + 3600, "room1")
    assert w == {"since": T0 - 3600, "minutes": 120, "rm": round(2.983 + 5.0, 2), "kwh": 20.0}
    assert energy.waste(T0 - 600, T0, "room1") is None      # exactly the delay: not flagged yet
    assert energy.waste(None, T0, "room1") is None


def test_day_totals_are_kept_in_three_units_and_a_later_change_leaves_them_alone(db):
    yesterday = T0 - 86400
    energy.add_ended(energy.ended(yesterday - 3600, None, yesterday, "room1"), yesterday, "room1")
    before = (energy.day_amounts(T0, 1), energy.day_amounts(T0, 1, "room1"))
    assert before[0] == before[1] == {"rm": 2.98, "kwh": pytest.approx(10.0), "co2_kg": pytest.approx(7.5)}
    energy.save(new(tariff_rm_per_kwh=0.9, co2_kg_per_kwh=0.1, ac_kw=50), "admin", T0)
    assert (energy.day_amounts(T0 + 60, 1), energy.day_amounts(T0 + 60, 1, "room1")) == before
    energy.add_ended(energy.ended(T0, None, T0 + 3600, "room2"), T0 + 3600, "room2")  # an hour at the new values
    assert energy.day_amounts(T0 + 3600, 0, "room2") == {"rm": 45.0, "kwh": pytest.approx(50.0), "co2_kg": pytest.approx(5.0)}
    assert energy.day_amounts(T0 + 3600, 0, "room1") == {"rm": 0.0, "kwh": 0.0, "co2_kg": 0.0}


def test_a_stretch_that_was_never_flagged_adds_nothing(db):
    assert energy.ended(T0 - 300, None, T0, "room1") is None   # shorter than the delay
    assert energy.ended(T0 - 3600, T0 - 3600, T0, "room1") is None  # still running
    assert energy.ended(None, None, T0, "room1") is None
    energy.add_ended(None, T0, "room1")
    assert store.waste_day(T0) == 0.0


def test_a_day_stored_in_rm_only_gets_its_kwh_from_the_tariff_in_force_at_its_end(db):
    yesterday = T0 - 86400
    store.add_waste_today(2.983, yesterday, "room1")  # as stored before kWh and CO2 were kept
    assert energy.day_amounts(T0, 1) == {"rm": 2.983, "kwh": pytest.approx(10.0), "co2_kg": pytest.approx(7.5)}
    energy.save(new(tariff_rm_per_kwh=0.9), "admin", T0)  # today's change does not restate yesterday
    assert energy.day_amounts(T0 + 60, 1)["kwh"] == pytest.approx(10.0)
    before_midnight = timeutil.midnight(T0) - 10
    energy.reset()
    db.db.execute("DELETE FROM energy_settings")
    energy.save(new(tariff_rm_per_kwh=0.5966), "admin", before_midnight)  # a change before that day ended does count
    assert energy.day_amounts(T0, 1)["kwh"] == pytest.approx(5.0)


def test_todays_rm_only_total_is_given_its_kwh_before_new_amounts_are_added(db):
    store.add_waste_today(2.983, T0, "room1")  # ended earlier today, stored in RM only
    energy.add_ended({"rm": 1.0, "kwh": 2.0, "co2_kg": 1.5}, T0 + 60, "room1")
    for room in (None, "room1"):
        assert energy.day_amounts(T0 + 60, 0, room) == {"rm": pytest.approx(3.983), "kwh": pytest.approx(12.0),
                                                        "co2_kg": pytest.approx(9.0)}


# --- the pages that show the figures ---

def test_energy_page_names_recent_rate_changes_and_uses_the_live_values(db):
    assert api().get("/api/energy").json()["rate_changes"] == []
    now = int(time.time())
    energy.save(new(tariff_rm_per_kwh=0.5), "old-admin", now - 20 * 86400)  # too long ago to mention
    energy.save(new(tariff_rm_per_kwh=0.4, co2_kg_per_kwh=0.6), "admin", now - 3600)
    out = api().get("/api/energy").json()
    assert out["rate_changes"] == [{"ts": now - 3600, "by": "admin"}]
    assert out["tariff_rm_per_kwh"] == 0.4 and out["co2_kg_per_kwh"] == 0.6 and out["ac_kw"] == 10.0


def test_energy_page_totals_come_from_the_stored_kwh_and_co2(db, monkeypatch):
    monkeypatch.setattr(main, "refresh_live", lambda now, lang=None: None)
    monkeypatch.setattr(main, "_last", {**main._last, "rooms": []})
    now = int(time.time())
    store.add_waste_today(4.0, now - 86400, "room1", 8.0, 2.0)   # yesterday, at some earlier rate
    store.add_waste_today(1.0, now - 9 * 86400, "room1", 3.0, 1.0)  # the week before
    energy.save(new(tariff_rm_per_kwh=5), "admin", now)
    out = api().get("/api/energy").json()
    assert out["yesterday"] == {"rm": 4.0, "kwh": 8.0, "co2_kg": 2.0} and out["week"] == {"rm": 4.0, "kwh": 8.0, "co2_kg": 2.0}
    assert out["previous_week"] == {"rm": 1.0, "kwh": 3.0, "co2_kg": 1.0} and out["today"]["rm"] == 0.0
    room1 = next(r for r in out["by_room"] if r["room_id"] == "room1")
    assert room1["rm_week"] == 4.0 and room1["rm_today"] == 0.0


def room_state(room_id, headcount, temp_c, now, since=None):
    store.r.sadd("rooms", room_id)
    store.r.hset(f"room:{room_id}", mapping={"headcount": headcount, "count_ts": now, "temp_c": temp_c, "temp_ts": now})
    if since is not None:
        store.r.hset(f"room:{room_id}", "empty_cold_since", since)


def test_the_waste_rule_follows_the_saved_temperature_and_delay(db, monkeypatch):
    now = int(time.time())
    room_state("room1", 0, 27.0, now)
    main.check_waste("room1", now)
    assert store.room("room1")["empty_cold_since"] is None  # 27 °C is not "on" with the default 26 °C
    api().put("/api/energy/settings", json=new(ac_on_below_c=28, waste_after_min=1), headers=H)
    main.check_waste("room1", now)
    assert store.room("room1")["empty_cold_since"] == now   # with 28 °C the timer starts on the next report
    info = api().get("/api/info").json()
    assert info["waste_minutes"] == 1.0 and info["ac_on_below_c"] == 28.0
    later = int(time.time()) + 90
    monkeypatch.setattr(main.time, "time", lambda: later)
    store.r.hset("room:room1", "count_ts", later)
    rooms = main.rooms_state("en")
    flagged = next(r for r in rooms["rooms"] if r["room_id"] == "room1")["waste"]
    assert flagged and flagged["minutes"] == 1 and flagged["kwh"] == pytest.approx(10 * (later - now) / 3600, abs=0.01)
    assert rooms["waste_today_kwh"] == round(flagged["kwh"], 1)


def test_the_demo_story_keeps_its_own_short_delay_whatever_is_saved(db, monkeypatch):
    energy.save(new(waste_after_min=30), "admin", T0 - 86400)
    assert energy.waste_after_s(T0) == 1800
    monkeypatch.setattr(energy, "delay_override_s", 60)
    assert energy.waste_after_s(T0) == 60 and energy.waste(T0 - 90, T0, "room1")["minutes"] == 1
    assert energy.current(T0)["waste_after_min"] == 30  # the saved value itself is not touched


def test_todays_total_in_kwh_adds_ended_and_running_stretches(db, monkeypatch):
    now = int(time.time())
    energy.add_ended({"rm": 2.0, "kwh": 6.0, "co2_kg": 4.0}, now, "room2")
    room_state("room1", 0, 24.0, now, since=now - 3600)
    out = main.rooms_state("en")
    assert out["waste_today_rm"] == pytest.approx(2.0 + 2.98, abs=0.011) and out["waste_today_kwh"] == 16.0


# --- MySQL offline ---

def test_mysql_offline_keeps_the_last_known_values_and_refuses_a_change(db):
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    db.down = True
    health.mark("mysql", False)
    body = api().get("/api/energy/settings").json()
    assert body["source"] == "last_known" and body["database"] is False and body["settings"]["tariff_rm_per_kwh"] == 0.35
    for lang, message in (("en", "The database is offline, so the change cannot be saved."),
                          ("ms", "Pangkalan data di luar talian, jadi perubahan tidak dapat disimpan.")):
        out = api().put(f"/api/energy/settings?lang={lang}", json=new(tariff_rm_per_kwh=0.5), headers=H)
        assert out.status_code == 503 and out.json()["detail"] == message
    assert energy.current()["tariff_rm_per_kwh"] == 0.35 and len(store.audit_log()) == 1
    assert energy.waste(T0 - 3600, T0, "room1") is not None  # the waste flag keeps working


def test_mysql_going_down_during_a_save_is_refused_too(db):
    db.down = True  # health still says "up": the save itself finds out
    out = api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.5), headers=H)
    assert out.status_code == 503 and not health.ok("mysql") and store.audit_log() == []


def test_a_cold_start_without_mysql_uses_the_defaults_until_it_is_back(db):
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    energy.reset()  # the server restarts ...
    db.down = True  # ... while MySQL is stopped
    body = api().get("/api/energy/settings").json()
    assert body["source"] == "defaults" and body["database"] is False and body["settings"] == DEFAULTS
    db.down = False
    health.reset()
    energy._state["next"] = 0.0  # the next re-read is due
    back = api().get("/api/energy/settings").json()
    assert back["source"] == "database" and back["settings"]["tariff_rm_per_kwh"] == 0.35


def test_the_defaults_come_from_the_server_configuration(db, monkeypatch):
    monkeypatch.setattr(logic, "TARIFF_RM_PER_KWH", 0.4)
    monkeypatch.setattr(logic, "AC_KW", 3.5)
    monkeypatch.setattr(logic, "WASTE_AFTER_S", 120)
    assert energy.current() == {**DEFAULTS, "tariff_rm_per_kwh": 0.4, "ac_kw": 3.5, "waste_after_min": 2.0}
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    assert energy.current()["tariff_rm_per_kwh"] == 0.35 and energy.current()["ac_kw"] == 10.0  # the database wins


def test_deleting_all_data_removes_the_saved_settings(db, monkeypatch, tmp_path):
    monkeypatch.setenv("LABELS_PATH", str(tmp_path / "labels.csv"))
    monkeypatch.setenv("INCIDENT_DIR", str(tmp_path / "incidents"))
    api().put("/api/energy/settings", json=new(tariff_rm_per_kwh=0.35), headers=H)
    store.add_waste_today(1.0, int(time.time()), "room1", 2.0, 1.0)
    out = api().post("/api/data/delete", json={"confirm": "DELETE ALL DATA"}, headers=H)
    assert out.status_code == 200 and db.saved() == []
    assert energy.current() == DEFAULTS and not list(store.r.scan_iter("waste_*"))
