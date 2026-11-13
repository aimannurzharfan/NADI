"""Counts from 0 to 1000 (the "count" service), the CSI "3 or more" flag, per-device message limits, the plausibility
check, pagination, retired devices and the demo reset. No Redis/MySQL needed."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import main, store, validate
from tests.test_alerts import FakeRedis

NOW = 1_800_000_000


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(validate, "clock", lambda: NOW)


def count(room="room2", n=40, ts=NOW):
    return {"service_id": "count", "properties": {"room_id": room, "ts": ts, "headcount": n}}


def test_count_service_bounds():
    assert validate.check(count(n=0))["properties"]["headcount"] == 0
    assert validate.check(count(n=1000))["properties"]["headcount"] == 1000
    for bad in (1001, -1, 2.5, "40", True, None):
        with pytest.raises(validate.Rejected):
            validate.check(count(n=bad))


@pytest.fixture
def ingest(monkeypatch):
    saved, live = [], {}

    def save_count(room, ts, n, p):
        saved.append((room, ts, n))
        live[room] = {"room_id": room, "headcount": n, "count_ts": ts}
        return True

    pending = {}
    monkeypatch.setattr(store, "save_count", save_count)
    monkeypatch.setattr(store, "room", lambda room: live.get(room))
    monkeypatch.setattr(store, "pending_count", lambda room: pending.get(room))
    monkeypatch.setattr(store, "set_pending_count", lambda room, n: pending.__setitem__(room, n))
    monkeypatch.setattr(store, "should_alert_suspicious", lambda room: True)
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    sent = []
    monkeypatch.setattr(main.alerts, "send", lambda *a, **k: sent.append((a, k)))
    return saved, sent


def test_jump_held_back_until_the_next_report_agrees(ingest, monkeypatch):
    saved, sent = ingest
    monkeypatch.setattr(main, "REPORT_INTERVAL_S", 20)
    assert main.process([count(n=10, ts=NOW - 40)])["saved"] == 1
    out = main.process([count(n=90, ts=NOW - 20)])  # +80 in one report: held, alert once
    assert out["suspicious"] == 1 and out["saved"] == 0 and saved[-1][2] == 10
    assert sent and sent[0][0][1] == "alert.suspicious_subject" and sent[0][1]["after"] == 90
    assert main.process([count(n=95, ts=NOW)])["saved"] == 1 and saved[-1][2] == 95  # confirmed a report later


def test_single_bad_reading_never_shows(ingest):
    saved, _ = ingest
    main.process([count(n=12, ts=NOW - 40)])
    main.process([count(n=500, ts=NOW - 20)])  # one forged spike
    main.process([count(n=13, ts=NOW)])        # back to normal: the spike is forgotten
    assert [n for _, _, n in saved] == [12, 13]


def test_small_changes_and_long_gaps_pass(ingest):
    saved, _ = ingest
    main.process([count(n=40, ts=NOW - 600)])
    main.process([count(n=55, ts=NOW - 580)])   # +15: fine
    main.process([count(n=200, ts=NOW)])        # 10 minutes later: anything can have happened
    assert [n for _, _, n in saved] == [40, 55, 200]


def test_device_flood_dropped(monkeypatch, ingest):
    saved, _ = ingest
    monkeypatch.setenv("DEVICE_MIN_GAP_S", "10")
    monkeypatch.setattr(main.health, "ok", lambda name: False)  # memory fallback
    main._device_seen.clear()
    outs = [main.process([count(n=40 + i, ts=NOW - 30 + i)], device_id="nadi-counter-1") for i in range(5)]
    assert [o["saved"] for o in outs] == [1, 0, 0, 0, 0] and [o["dropped"] for o in outs] == [0, 1, 1, 1, 1]
    assert main.process([count("room3", n=1)], device_id="nadi-counter-1")["saved"] == 1  # another room is separate


def test_empty_device_gap_means_the_default(monkeypatch, ingest):
    """.env.example ships DEVICE_MIN_GAP_S= (empty): that is half the report interval, not a crash on every report."""
    monkeypatch.setenv("DEVICE_MIN_GAP_S", "")
    monkeypatch.setattr(main.health, "ok", lambda name: False)
    main._device_seen.clear()
    outs = [main.process([count(n=40, ts=NOW - 30 + i)], device_id="nadi-counter-2") for i in range(2)]
    assert [o["saved"] for o in outs] == [1, 0] and outs[1]["dropped"] == 1 and not outs[0]["errors"]


def test_resend_is_a_duplicate_not_a_flood(monkeypatch, ingest):
    monkeypatch.setenv("DEVICE_MIN_GAP_S", "10")
    monkeypatch.setattr(main.health, "ok", lambda name: False)
    main._device_seen.clear()
    seen = set()
    monkeypatch.setattr(store, "already_seen", lambda svc, room, ts: (svc, room, ts) in seen)
    assert main.process([count(n=5)], device_id="d1")["saved"] == 1
    seen.add(("count", "room2", NOW))
    out = main.process([count(n=5)], device_id="d1")
    assert out["duplicate"] == 1 and out["dropped"] == 0


# --- room views and display ---

def test_room_views_carry_the_lower_bound_flag(monkeypatch):
    monkeypatch.setattr(store, "rooms", lambda: [
        {"room_id": "room1", "headcount": 3, "at_least": True, "count_ts": NOW, "temp_c": None, "humidity": None,
         "empty_cold_since": None, "waste_alert_ts": None},
        {"room_id": "room2", "headcount": 150, "at_least": False, "count_ts": NOW, "temp_c": None, "humidity": None,
         "empty_cold_since": None, "waste_alert_ts": None}])
    views = {v["room_id"]: v for v in main.room_views(NOW)}
    assert views["room1"]["at_least"] is True and views["room2"]["at_least"] is False
    assert main.logic.count_of(views["room2"]) == "100+" and main.logic.count_of(views["room1"]) == "3+"


def test_stored_rows_without_flag_read_as_csi():
    fake = FakeRedis()
    fake.sets = {"rooms": {"room1", "room2"}}
    fake.hashes = {"room:room1": {"headcount": "3", "count_ts": "1"}, "room:room2": {"headcount": "3", "at_least": "0", "count_ts": "1"}}

    class Pipe:
        def __init__(self):
            self.keys = []

        def hgetall(self, key):
            self.keys.append(key)

        def execute(self):
            return [fake.hashes.get(k, {}) for k in self.keys]

    fake.smembers = lambda key: fake.sets[key]
    fake.pipeline = lambda transaction=False: Pipe()
    old = store.r
    store.r = fake
    try:
        rooms = {r["room_id"]: r for r in store.rooms()}
    finally:
        store.r = old
    assert rooms["room1"]["at_least"] is True and rooms["room2"]["at_least"] is False


# --- API: pagination, devices, labels ---

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    monkeypatch.setenv("ADMIN_TOKENS", "")
    return TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)


def test_alerts_paginated(api, monkeypatch):
    kept = [{"id": f"a{i:03d}", "ts": i} for i in range(130)]
    monkeypatch.setattr(main.alerts, "recent", lambda lang="en", limit=20: kept[:limit])
    page = api.get("/api/alerts?limit=50&offset=100").json()
    assert page["total"] == 130 and len(page["alerts"]) == 30 and page["alerts"][0]["id"] == "a100"
    assert api.get("/api/alerts?limit=5000").json()["limit"] == 100  # capped


def test_audit_paginated(api, monkeypatch):
    monkeypatch.setattr(store, "audit_log", lambda: [{"ts": i, "action": "start", "by": "x", "ip": "1"} for i in range(120)])
    page = api.get("/api/audit?limit=100&offset=100").json()
    assert page["total"] == 120 and len(page["audit"]) == 20


def test_retired_devices_hidden_and_cleared(api, monkeypatch):
    now = __import__("time").time()
    devs = [{"device_id": "nadi-recv-1", "service": "csi", "room_id": "room1", "rooms": ["room1"], "last_seen": int(now) - 5},
            {"device_id": "old-board", "service": "csi", "room_id": "room2", "rooms": ["room2"], "last_seen": int(now) - 3 * 86400},
            {"device_id": "nadi-sim", "service": "csi", "room_id": "room3", "rooms": ["room1", "room2", "room3"],
             "last_seen": int(now) - 5}]
    monkeypatch.setattr(store, "devices", lambda: [dict(d) for d in devs])
    out = api.get("/api/devices").json()
    assert [d["device_id"] for d in out["devices"]] == ["nadi-recv-1", "nadi-sim"] and out["retired_hidden"] == 1
    assert len(api.get("/api/devices?retired=true").json()["devices"]) == 3
    gone = []
    monkeypatch.setattr(store, "forget_devices", lambda ids: gone.extend(ids))
    assert api.post("/api/devices/clear").json() == {"cleared": 2}
    assert sorted(gone) == ["nadi-sim", "old-board"]
    lan = TestClient(main.app, client=("192.168.1.9", 5000), base_url=LOCAL_URL)
    assert lan.post("/api/devices/clear").status_code == 403  # admin only


def test_labels_up_to_100(api, monkeypatch, tmp_path):
    monkeypatch.setenv("LABELS_PATH", str(tmp_path / "labels.csv"))
    assert api.post("/api/labels", json={"room_id": "room1", "headcount": 42}).status_code == 200
    assert api.post("/api/labels", json={"room_id": "room1", "headcount": 100}).status_code == 200
    assert api.post("/api/labels", json={"room_id": "room1", "headcount": 101}).status_code == 422


def test_history_bucket_is_the_peak(monkeypatch):
    captured = {}

    class Cur:
        def execute(self, sql, args):
            captured["sql"] = sql

        def fetchall(self):
            return [("room2", 1000, 120)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class Conn(Cur):
        def cursor(self):
            return Cur()

    monkeypatch.setattr(store, "mysql", lambda: Conn())
    out = store.history(0, 900)
    assert "MAX(headcount)" in captured["sql"] and out == {"room2": [[1000, 120]]}


# --- demo reset ---

def test_reset_script_refuses_huawei_and_needs_yes(monkeypatch):
    import scripts.reset_demo_data as reset

    called = []
    monkeypatch.setattr(store, "clear_demo_data", lambda keep=None: called.append(1) or {"redis_keys": 0, "occupancy": 0, "climate": 0})
    monkeypatch.setenv("NADI_MODE", "huawei")
    monkeypatch.setattr("sys.argv", ["reset", "--yes"])
    with pytest.raises(SystemExit):
        reset.main()
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setattr("sys.argv", ["reset"])
    with pytest.raises(SystemExit):
        reset.main()
    assert not called
    monkeypatch.setattr("sys.argv", ["reset", "--yes"])
    reset.main()
    assert called == [1]


class SqliteAsMysql:
    """A real SQL engine behind store.mysql(), so the test checks which rows the DELETE leaves, not its text."""

    def __init__(self):
        import sqlite3

        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE occupancy (room_id TEXT, ts INTEGER, motion_std REAL, source TEXT)")
        self.db.execute("CREATE TABLE climate (room_id TEXT, ts INTEGER, temp_c REAL, humidity REAL)")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.db.commit()

    def cursor(self):
        return self

    def execute(self, sql, args=()):
        self.last = self.db.execute(sql.replace("%s", "?"), list(args))
        return self.last.rowcount

    def fetchone(self):
        return self.last.fetchone()

    def fetchall(self):
        return self.last.fetchall()

    def rows(self, table="occupancy"):
        return sorted(self.db.execute(f"SELECT room_id, ts FROM {table}").fetchall())


def test_reset_keeps_the_reports_inside_a_label(monkeypatch):
    db = SqliteAsMysql()
    for room, ts in [("room1", 90), ("room1", 100), ("room1", 150), ("room1", 200), ("room1", 201), ("room1", 320),
                     ("room1", 480), ("room2", 150), ("room2", 320)]:
        db.execute("INSERT INTO occupancy VALUES (%s, %s, 0.5, 'nadi-recv-1')", (room, ts))
    db.execute("INSERT INTO climate VALUES ('room1', 150, 24.0, 60.0)")
    monkeypatch.setattr(store, "mysql", lambda: db)
    store.r.set("rooms", "x")
    # room1 was labelled from 100 to 200, and a label is still running since 300; room2 has no label
    out = store.clear_demo_data(keep={"room1": [(100, 200, 0), (300, None, 1)]}, now=500)
    assert db.rows() == [("room1", 100), ("room1", 150), ("room1", 200), ("room1", 320), ("room1", 480)]
    assert db.rows("climate") == [] and store.r.get("rooms") is None
    assert out["kept"] == 5 and out["occupancy"] == 4 and out["climate"] == 1


def test_reset_without_labels_clears_every_report(monkeypatch):
    db = SqliteAsMysql()
    db.execute("INSERT INTO occupancy VALUES ('room1', 100, 0.5, 'nadi-recv-1')")
    monkeypatch.setattr(store, "mysql", lambda: db)
    out = store.clear_demo_data(keep={})
    assert db.rows() == [] and out["kept"] == 0 and out["occupancy"] == 1


def test_reset_script_passes_the_labels_and_says_what_it_keeps(monkeypatch, tmp_path, capsys):
    import scripts.reset_demo_data as reset

    csv_path = tmp_path / "labels.csv"
    lines = ["room_id,start_ts,end_ts,headcount", "room1,100,200,0", "room1,300,,1", "room1,oops,400,1", ""]
    csv_path.write_text(chr(10).join(lines), encoding="utf-8")
    monkeypatch.setenv("LABELS_PATH", str(csv_path))
    monkeypatch.setenv("NADI_MODE", "local")
    got = {}
    monkeypatch.setattr(store, "clear_demo_data", lambda keep=None: got.update(keep=keep) or
                        {"redis_keys": 3, "occupancy": 4, "climate": 1, "kept": 5})
    monkeypatch.setattr("sys.argv", ["reset", "--yes"])
    reset.main()
    assert got["keep"] == {"room1": [(100, 200, 0), (300, None, 1)]}  # the row that does not parse is skipped
    assert "Kept 5 labelled reports" in capsys.readouterr().out
    assert csv_path.read_text(encoding="utf-8").count("room1") == 3  # the labels file is not touched
    monkeypatch.setattr("sys.argv", ["reset", "--help"])
    with pytest.raises(SystemExit):
        reset.main()
    help_text = " ".join(capsys.readouterr().out.split())
    assert "every stored report inside a label" in help_text and "Calibration chart survives" in help_text


def test_emergency_alert_names_unknown_rooms(monkeypatch):
    sent = []
    monkeypatch.setattr(main.alerts, "send", lambda kind, s, b, **v: sent.append((b, v)))
    monkeypatch.setattr(store, "start_emergency", lambda now, by, *rest: True)
    monkeypatch.setattr(store, "audit", lambda e: None)
    monkeypatch.setattr(store, "rooms", lambda: [
        {"room_id": "room1", "headcount": 2, "at_least": False, "count_ts": 10 ** 10, "temp_c": None, "humidity": None,
         "empty_cold_since": None, "waste_alert_ts": None},
        {"room_id": "room3", "headcount": 0, "at_least": False, "count_ts": 1, "temp_c": None, "humidity": None,
         "empty_cold_since": None, "waste_alert_ts": None}])
    monkeypatch.setattr(main.time, "time", lambda: 10 ** 10)
    main.set_emergency(True, "warden", "127.0.0.1")
    body, values = [s for s in sent if s[0].startswith("alert.emergency_body")][0]
    assert body == "alert.emergency_body_unknown" and values["n"] == 1 and values["total"] == 2
    msg = main.alerts.render({"subject_key": "alert.emergency_subject", "body_key": body, "values": values}, "en")[1]
    assert "At least 2 people" in msg and json.dumps(values)
