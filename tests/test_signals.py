"""GET /api/signals: every sensing room's motion figure in one answer, so the overview makes one request per poll
whatever the number of rooms, and MySQL sees one query per two seconds whatever the number of dashboards. Read only,
same access rule as the other read endpoints. No Redis or MySQL needed (sqlite3 runs the real query in one test)."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import health, logic, main, model, store
from tests.test_scale import SqliteAsMysql
from tests.util import LOCAL_URL

VIEWER = "viewer-token-0123456789abcdef"
ROOMS = [f"r{i:02d}" for i in range(1, 14)]  # thirteen rooms


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("DEMO_SCENARIO", "off")
    monkeypatch.setenv("ROOM_NAMES", ",".join(f"{r}:Room {r}" for r in ROOMS))
    for k in ("ADMIN_TOKEN", "ADMIN_TOKENS", "VIEWER_TOKEN"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(main, "_signals_cache", {})
    monkeypatch.setattr(model, "load", lambda path=None: None)  # the threshold rule is counting
    monkeypatch.setattr(logic, "THRESHOLDS", [1.301, 99.0, 99.0])
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


@pytest.fixture
def rows(monkeypatch):
    """Stands in for MySQL: thirteen rooms, each with a report 7 min, 3 min and 20 s old. Remembers what was asked."""
    calls = []
    base = int(time.time())

    def signals_history(since, skip_sources=(), limit=store.SIGNALS_MAX_ROWS):
        calls.append({"since": since, "skip": tuple(skip_sources)})
        return {r: [[base - 420, 0.25, 0], [base - 180, 1.9, 1], [base - 20, 0.4012345, 0]] for r in ROOMS}

    monkeypatch.setattr(store, "signals_history", signals_history)
    calls.append(base)
    return calls


def test_every_room_in_one_answer_with_the_shape_of_the_room_endpoint(api, rows):
    base = rows[0]
    out = api.get("/api/signals").json()
    assert sorted(out["rooms"]) == ROOMS and out["minutes"] == 5 and out["threshold"] == 1.301 and out["truncated"] is False
    one = out["rooms"]["r07"]
    assert one["room_id"] == "r07" and one["minutes"] == 5 and one["threshold"] == 1.301
    assert one["points"] == [{"ts": base - 180, "motion_std": 1.9, "headcount": 1},
                             {"ts": base - 20, "motion_std": 0.4012, "headcount": 0}]  # the 7-minute-old report is outside 5 min
    assert one["last_report_ts"] == base - 20


def test_thirteen_rooms_cost_one_query_however_often_it_is_asked(api, rows):
    for minutes in (5, 1, 10, 5, 3):  # another window is cut from the same rows: it cannot get past the cache
        assert api.get(f"/api/signals?minutes={minutes}").status_code == 200
    assert len(rows) == 2  # the base time + one query
    assert rows[1]["since"] <= rows[0] - 10 * 60 + 2 and rows[1]["skip"] == ("nadi-sim", "sim-local")


def test_minutes_are_clamped(api, rows):
    assert api.get("/api/signals?minutes=0").json()["minutes"] == 1
    out = api.get("/api/signals?minutes=999").json()
    assert out["minutes"] == 10 and len(out["rooms"]["r01"]["points"]) == 3


def test_simulator_rows_count_only_while_the_demo_scenario_is_on(api, rows, monkeypatch):
    monkeypatch.setenv("DEMO_SCENARIO", "on")
    api.get("/api/signals")
    assert rows[1]["skip"] == ()


def test_no_threshold_while_a_model_is_counting(api, rows, monkeypatch):
    monkeypatch.setattr(model, "load", lambda path=None: {"framework": "MindSpore"})
    out = api.get("/api/signals").json()
    assert out["threshold"] is None and out["rooms"]["r01"]["threshold"] is None


def test_rooms_that_are_not_known_are_left_out_and_the_answer_is_capped(api, monkeypatch):
    base = int(time.time())
    many = {f"x{i:03d}": [[base - 10, 0.5, 0]] for i in range(80)}
    monkeypatch.setenv("ROOM_NAMES", ",".join(f"{r}:R" for r in many))
    monkeypatch.setattr(store, "signals_history", lambda since, skip_sources=(), limit=0: {**many, "ghost": [[base - 10, 0.5, 0]]})
    out = api.get("/api/signals").json()
    assert len(out["rooms"]) == main.SIGNALS_MAX_ROOMS and out["truncated"] is True and "ghost" not in out["rooms"]


def test_viewer_rule_and_the_read_bucket(api, rows, monkeypatch):
    assert main.bucket_of("GET", "/api/signals") == "read"
    monkeypatch.setenv("VIEWER_TOKEN", VIEWER)
    assert api.get("/api/signals").status_code == 401
    assert api.get("/api/signals", headers={"X-Viewer-Token": VIEWER}).status_code == 200
    assert api.post("/api/signals").status_code in (404, 405)  # read only


def test_503_while_mysql_is_offline(api, rows):
    health.mark("mysql", False)
    assert api.get("/api/signals").status_code == 503
    assert len(rows) == 1  # MySQL was not asked


def test_a_burst_while_mysql_is_down_waits_for_mysql_once(api, monkeypatch):
    asked = []

    def slow(since, skip_sources=(), limit=0):
        asked.append(1)
        time.sleep(0.2)
        raise store.MYSQL_ERRORS[0]("down")

    monkeypatch.setattr(store, "signals_history", slow)
    codes = []
    threads = [threading.Thread(target=lambda: codes.append(api.get("/api/signals").status_code)) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert codes == [503] * 6 and len(asked) == 1


def test_the_query_reads_all_rooms_at_once_and_binds_its_values(monkeypatch):
    db = SqliteAsMysql()
    db.db.execute("ALTER TABLE occupancy ADD COLUMN headcount INTEGER")
    for room, ts, std, src, count in [("room1", 100, 0.4, "RECV-1", 0), ("room2", 110, 2.2, "RECV-2", 1), ("room1", 120, 0.5, "nadi-sim", 0),
                                      ("room3", 130, None, "COUNT-1", 5), ("room1", 50, 0.3, "RECV-1", 0), ("room2", 140, 1.8, None, 1)]:
        db.db.execute("INSERT INTO occupancy (room_id, ts, motion_std, source, headcount) VALUES (?, ?, ?, ?, ?)", (room, ts, std, src, count))
    monkeypatch.setattr(store, "mysql", lambda: db)
    out = store.signals_history(100, ("nadi-sim", "x' OR '1'='1"))
    # since 100, simulator rows and rows with no motion figure (the "count" service) left out, oldest first per room
    assert out == {"room1": [[100, 0.4, 0]], "room2": [[110, 2.2, 1], [140, 1.8, 1]]}
    assert store.signals_history(100, (), limit=2) == {"room2": [[140, 1.8, 1]], "room1": [[120, 0.5, 0]]}  # the newest rows win
