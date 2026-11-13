"""GET /api/rooms/{room_id}/signal: the motion figure behind the live signal chart on the overview. Read only, same
access rule as the other read endpoints. No Redis or MySQL needed."""
import time

import pytest
from fastapi.testclient import TestClient

from server import health, logic, main, model, store
from tests.util import LOCAL_URL

VIEWER = "viewer-token-0123456789abcdef"
ADMIN = "signal-admin-token-0123456789"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("DEMO_SCENARIO", "off")
    for k in ("ADMIN_TOKEN", "ADMIN_TOKENS", "VIEWER_TOKEN"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(main, "_signal_cache", {})
    monkeypatch.setattr(model, "load", lambda path=None: None)  # the threshold rule is counting
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


class Calls(list):
    """What MySQL was asked, and `base`: the time the three stored reports are counted back from."""
    base = 0


@pytest.fixture
def rows(monkeypatch):
    """Stands in for MySQL: remembers what was asked and answers with three reports, 17 min, 3 min and 20 s old
    when the test starts."""
    calls = Calls()
    calls.base = base = int(time.time())
    reports = [[base - 1000, 0.25, 0], [base - 200, 1.9, 1], [base - 20, 0.4012345, 0]]

    def signal_history(room_id, since, skip_sources=()):
        calls.append({"room": room_id, "since": since, "skip": tuple(skip_sources)})
        return [list(r) for r in reports if r[0] >= since]

    monkeypatch.setattr(store, "signal_history", signal_history)
    return calls


def test_points_threshold_and_last_report(api, rows, monkeypatch):
    monkeypatch.setattr(logic, "THRESHOLDS", [1.301, 99.0, 99.0])
    out = api.get("/api/rooms/room1/signal").json()
    assert out["room_id"] == "room1" and out["minutes"] == 5 and out["threshold"] == 1.301
    assert out["points"] == [{"ts": rows.base - 200, "motion_std": 1.9, "headcount": 1},
                             {"ts": rows.base - 20, "motion_std": 0.4012, "headcount": 0}]  # the 17-minute-old report is outside 5 min
    assert out["last_report_ts"] == rows.base - 20
    assert rows[0]["room"] == "room1"


def test_no_reports_yet(api, monkeypatch):
    monkeypatch.setattr(store, "signal_history", lambda *a, **k: [])
    out = api.get("/api/rooms/room1/signal").json()
    assert out["points"] == [] and out["last_report_ts"] is None


def test_viewer_token_is_required_when_set(api, rows, monkeypatch):
    monkeypatch.setenv("VIEWER_TOKEN", VIEWER)
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    assert api.get("/api/rooms/room1/signal").status_code == 401
    assert api.get("/api/rooms/room1/signal", headers={"X-Viewer-Token": "wrong-viewer-token-000000"}).status_code == 401
    assert rows == []  # nothing was read for a caller without access
    assert api.get("/api/rooms/room1/signal", headers={"X-Viewer-Token": VIEWER}).status_code == 200
    assert api.get("/api/rooms/room1/signal", headers={"X-Admin-Token": ADMIN}).status_code == 200


def test_read_only(api, rows):
    for method in (api.post, api.put, api.delete):
        assert method("/api/rooms/room1/signal").status_code in (403, 404, 405)
    assert rows == []


def test_unknown_room_is_refused(api, rows):
    assert api.get("/api/rooms/room99/signal").status_code == 422
    assert api.get("/api/rooms/<script>/signal").status_code in (404, 422)
    assert api.get("/api/rooms/room1' OR '1'='1/signal").status_code == 422
    assert rows == []


@pytest.mark.parametrize("asked,used,points", [("0", 1, 1), ("-5", 1, 1), ("1", 1, 1), ("5", 5, 2), ("60", 60, 3),
                                               ("61", 60, 3), ("999999", 60, 3)])
def test_minutes_are_clamped(api, rows, asked, used, points):
    out = api.get(f"/api/rooms/room1/signal?minutes={asked}").json()
    assert out["minutes"] == used and len(out["points"]) == points
    assert all(p["ts"] >= out["now"] - used * 60 for p in out["points"])
    assert time.time() - rows[0]["since"] == pytest.approx(60 * 60, abs=5)  # MySQL is never asked for more than an hour


def test_one_query_per_room_whatever_window_is_asked_and_however_often(api, rows, monkeypatch):
    """Changing "minutes" on every request must not get past the cache: MySQL sees one query per room per
    SIGNAL_CACHE_S, and the cache holds one entry per room."""
    for minutes in range(1, 61):
        assert api.get(f"/api/rooms/room1/signal?minutes={minutes}").status_code == 200
    assert len(rows) == 1
    api.get("/api/rooms/room2/signal")
    assert [c["room"] for c in rows] == ["room1", "room2"] and set(main._signal_cache) == {"room1", "room2"}
    monkeypatch.setattr(main, "SIGNAL_CACHE_S", 0)  # the cached rows have aged out
    api.get("/api/rooms/room1/signal?minutes=7")
    assert len(rows) == 3
    for i in range(main.SIGNAL_CACHE_ROOMS + 5):  # even a server set up with very many rooms: the cache stays bounded
        main.signal_rows(f"r{i}", rows.base)
    assert len(main._signal_cache) <= main.SIGNAL_CACHE_ROOMS


def test_minutes_must_be_a_number(api, rows):
    assert api.get("/api/rooms/room1/signal?minutes=abc").status_code == 422
    assert rows == []


def test_503_while_mysql_is_offline(api, rows):
    health.mark("mysql", False)
    res = api.get("/api/rooms/room1/signal")
    assert res.status_code == 503 and "detail" in res.json()
    assert rows == []  # MySQL is not asked again until the watcher says it is back


def test_503_when_the_query_fails(api, monkeypatch):
    def broken(*a, **k):
        raise store.MYSQL_ERRORS[0]("gone away")

    monkeypatch.setattr(store, "signal_history", broken)
    assert api.get("/api/rooms/room1/signal").status_code == 503
    assert not health.ok("mysql")


def test_a_burst_while_mysql_is_down_waits_for_mysql_once(api, monkeypatch):
    """Many dashboards ask at the moment MySQL goes away: one request waits for the failed query, the rest are told
    "offline" without asking again (they would otherwise each wait for the timeout in turn)."""
    import threading
    calls, codes = [], []

    def slow_and_gone(*a, **k):
        calls.append(1)
        time.sleep(0.3)
        raise store.MYSQL_ERRORS[0]("gone away")

    monkeypatch.setattr(store, "signal_history", slow_and_gone)
    threads = [threading.Thread(target=lambda: codes.append(api.get("/api/rooms/room1/signal").status_code)) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    assert codes == [503] * 6 and len(calls) == 1


def test_threshold_is_null_when_a_model_is_counting(api, rows, monkeypatch):
    monkeypatch.setattr(model, "load", lambda path=None: {"features": ["motion_std"]})
    out = api.get("/api/rooms/room1/signal?minutes=60").json()
    assert out["threshold"] is None and len(out["points"]) == 3


def test_simulator_rows_are_left_out_unless_the_demo_is_on(api, rows, monkeypatch):
    monkeypatch.setenv("SIM_DEVICE_ID", "nadi-sim")
    api.get("/api/rooms/room1/signal")
    assert set(rows[-1]["skip"]) == {"nadi-sim", "sim-local"}
    monkeypatch.setattr(main, "_signal_cache", {})
    monkeypatch.setenv("DEMO_SCENARIO", "on")
    api.get("/api/rooms/room1/signal")
    assert rows[-1]["skip"] == ()


class _Cursor:
    def __init__(self, table):
        self.table, self.sql, self.args = table, "", []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args):
        self.sql, self.args = sql, list(args)

    def fetchall(self):
        """Just enough SQL for this one query: room, time, "has a motion figure" and the skipped sources."""
        room, since, *skip = self.args[:-1]
        keep = [r for r in self.table if r["room_id"] == room and r["ts"] >= since and r["motion_std"] is not None
                and ("NOT IN" not in self.sql or r["source"] is None or r["source"] not in skip)]
        keep.sort(key=lambda r: -r["ts"])
        return [(r["ts"], r["motion_std"], r["headcount"]) for r in keep[:self.args[-1]]]


class _Conn(_Cursor):
    def cursor(self):
        return self


def test_query_keeps_csi_rows_only_and_skips_the_simulator(monkeypatch):
    table = [
        {"room_id": "room1", "ts": 10, "motion_std": 0.2, "headcount": 0, "source": "nadi-recv-1"},
        {"room_id": "room1", "ts": 20, "motion_std": 2.5, "headcount": 3, "source": "nadi-sim"},      # simulator
        {"room_id": "room1", "ts": 30, "motion_std": None, "headcount": 40, "source": "counter-1"},   # count service
        {"room_id": "room2", "ts": 30, "motion_std": 0.9, "headcount": 1, "source": "nadi-recv-2"},   # another room
        {"room_id": "room1", "ts": 40, "motion_std": 1.7, "headcount": 1, "source": None},            # sender unknown
        {"room_id": "room1", "ts": 5, "motion_std": 0.1, "headcount": 0, "source": "nadi-recv-1"},    # too old
    ]
    conn = _Conn(table)
    monkeypatch.setattr(store, "mysql", lambda: conn)
    assert store.signal_history("room1", 10, ("nadi-sim", "sim-local")) == [[10, 0.2, 0], [40, 1.7, 1]]
    assert "%s" in conn.sql and "nadi-sim" not in conn.sql and "room1" not in conn.sql  # values are bound, never pasted in
    assert store.signal_history("room1", 10) == [[10, 0.2, 0], [20, 2.5, 3], [40, 1.7, 1]]  # demo scenario: all shown


def test_rate_limit_is_the_read_bucket():
    assert main.bucket_of("GET", "/api/rooms/room1/signal") == "read"
