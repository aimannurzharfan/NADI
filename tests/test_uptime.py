"""GET /api/uptime: the share of today in which each room's sensor was reporting, for the overview's "today so far"
strip. It must go down when a sensor has been offline, by the same rule that shows "offline" on the dashboard (no
report for STALE_S). Read only. No Redis or MySQL needed."""
import pytest
from fastapi.testclient import TestClient

from server import health, main, store, timeutil
from tests.util import LOCAL_URL

NOW = 1_794_000_037               # some time in November 2026
MIDNIGHT = timeutil.midnight(NOW)
STALE = 30                        # three missed reports at one every 10 s


def room(room_id, count_ts):
    return {"room_id": room_id, "count_ts": count_ts}


def test_midnight_is_malaysian():
    assert timeutil.clock(MIDNIGHT) == "00:00:00" and timeutil.day(MIDNIGHT) == timeutil.day(NOW)
    assert 0 < NOW - MIDNIGHT < 86400 and timeutil.midnight(MIDNIGHT) == MIDNIGHT
    assert timeutil.midnight(MIDNIGHT - 1) == MIDNIGHT - 86400


def test_a_sensor_that_never_stopped_is_at_100():
    first = NOW - 3600
    out = main.uptime_today(NOW, {"room1": [first, NOW - 4, 0]}, [room("room1", NOW - 4)], stale=STALE)
    assert out["rooms"]["room1"] == {"first_ts": first, "up_s": 3600, "expected_s": 3600}
    assert out["pct"] == 100 and out["since"] == MIDNIGHT and out["stale_s"] == STALE


def test_uptime_drops_while_a_sensor_is_offline():
    first, last = NOW - 3600, NOW - 900  # reported for 45 minutes, silent for the last 15
    out = main.uptime_today(NOW, {"room1": [first, last, 0]}, [room("room1", last)], stale=STALE)
    assert out["pct"] == 75
    later = main.uptime_today(NOW + 600, {"room1": [first, last, 0]}, [room("room1", last)], stale=STALE)
    assert later["pct"] < out["pct"]  # and it keeps dropping for as long as the sensor stays silent
    # from the moment the dashboard calls it offline (31 s without a report), not a second earlier
    assert main.uptime_today(last + STALE, {"room1": [first, last, 0]}, None, stale=STALE)["pct"] == 100
    assert main.uptime_today(last + STALE + 1, {"room1": [first, last, 0]}, None, stale=STALE)["pct"] < 100


def test_an_outage_earlier_today_still_counts():
    first = NOW - 6 * 3600
    out = main.uptime_today(NOW, {"room1": [first, NOW - 3, 90]}, [room("room1", NOW - 3)], stale=STALE)  # 90 s offline
    assert out["rooms"]["room1"]["up_s"] == 6 * 3600 - 90
    assert out["pct"] == pytest.approx(100 * (21600 - 90) / 21600, abs=0.01) and out["pct"] < 100


def test_a_report_that_is_merely_due_is_not_downtime():
    first = NOW - 600
    assert main.uptime_today(NOW, {"room1": [first, NOW - 19, 0]}, [room("room1", NOW - 19)], stale=STALE)["pct"] == 100


def test_rooms_are_weighed_by_time_and_a_sensor_silent_all_day_counts_from_midnight():
    first = NOW - 3600
    known = [room("room1", NOW - 5), room("room2", MIDNIGHT - 7200), room("room3", None)]
    out = main.uptime_today(NOW, {"room1": [first, NOW - 5, 0]}, known, stale=STALE)
    assert out["rooms"]["room2"] == {"first_ts": None, "up_s": 0, "expected_s": NOW - MIDNIGHT}
    assert "room3" not in out["rooms"]  # never reported at all: no sensor to judge
    assert out["pct"] == pytest.approx(100 * 3600 / (3600 + NOW - MIDNIGHT), abs=0.01)
    # a room that is live but has nothing stored today (history database was offline) is unknown, not down
    assert main.uptime_today(NOW, {}, [room("room1", NOW - 5)], stale=STALE) == {
        "now": NOW, "since": MIDNIGHT, "stale_s": STALE, "rooms": {}, "pct": None}


def test_nothing_to_judge_yet():
    out = main.uptime_today(NOW, {"room1": [NOW, NOW, 0]}, [room("room1", NOW)], stale=STALE)  # the very first report
    assert out["rooms"] == {} and out["pct"] is None
    assert main.uptime_today(NOW, {}, None, stale=STALE)["pct"] is None  # live state unreadable


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    for k in ("ADMIN_TOKEN", "ADMIN_TOKENS", "VIEWER_TOKEN"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(main, "_uptime_cache", {})
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


def test_viewer_token_is_required_when_set(api, monkeypatch):
    asked = []
    monkeypatch.setattr(store, "report_gaps", lambda since, stale: asked.append(1) or {})
    monkeypatch.setenv("VIEWER_TOKEN", "viewer-token-0123456789abcdef")
    assert api.get("/api/uptime").status_code == 401
    assert api.get("/api/uptime", headers={"X-Viewer-Token": "wrong-viewer-token-000000"}).status_code == 401
    assert asked == []  # nothing was read for a caller without access
    assert api.get("/api/uptime", headers={"X-Viewer-Token": "viewer-token-0123456789abcdef"}).status_code == 200


def test_endpoint_asks_mysql_once_and_reads_only(api, monkeypatch):
    calls = []

    def report_gaps(since, stale):
        calls.append((since, stale))
        return {"room1": [since + 60, since + 86400 * 2, 0]}  # last report "in the future": no tail whatever the time

    monkeypatch.setattr(store, "report_gaps", report_gaps)
    out = api.get("/api/uptime").json()
    since, stale = calls[0]
    assert stale == main.STALE_S and since == timeutil.midnight(out["now"]) == out["since"]
    assert out["rooms"]["room1"]["first_ts"] == since + 60 and out["pct"] in (100, None)
    assert api.get("/api/uptime").json() == out and len(calls) == 1  # a second dashboard costs MySQL nothing
    assert api.post("/api/uptime").status_code == 405


def test_endpoint_says_503_while_mysql_is_offline(api, monkeypatch):
    def down(*a):
        raise store.MYSQL_ERRORS[0]("gone")

    monkeypatch.setattr(store, "report_gaps", down)
    assert api.get("/api/uptime").status_code == 503
    assert not health.should_try("mysql")
    assert api.get("/api/uptime").status_code == 503  # and MySQL is not asked again straight away


def test_a_burst_asks_mysql_once_whether_it_answers_or_not(api, monkeypatch):
    import threading
    import time
    calls, out = [], []

    def slow(since, stale):
        calls.append(1)
        time.sleep(0.3)
        return {"room1": [since + 60, since + 86400 * 2, 0]}

    def burst():
        threads = [threading.Thread(target=lambda: out.append(api.get("/api/uptime").status_code)) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)

    monkeypatch.setattr(store, "report_gaps", slow)
    burst()
    assert out == [200] * 6 and len(calls) == 1  # the cache expired for six dashboards at once: one query

    def slow_and_gone(since, stale):
        calls.append(1)
        time.sleep(0.3)
        raise store.MYSQL_ERRORS[0]("gone")

    main._uptime_cache.clear()
    del calls[:], out[:]
    monkeypatch.setattr(store, "report_gaps", slow_and_gone)
    burst()
    assert out == [503] * 6 and len(calls) == 1  # MySQL gone: one request waits for it, the rest are told at once


def test_query_adds_up_the_gaps_longer_than_the_offline_rule(monkeypatch):
    captured = {}

    class Cur:
        def execute(self, sql, args):
            captured["sql"], captured["args"] = sql, args

        def fetchall(self):
            return [("room1", 1000, 5000, 90)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class Conn(Cur):
        def cursor(self):
            return Cur()

    monkeypatch.setattr(store, "mysql", lambda: Conn())
    assert store.report_gaps(900, 30) == {"room1": [1000, 5000, 90]}
    sql = captured["sql"]
    assert "LAG(ts) OVER (PARTITION BY room_id ORDER BY ts)" in sql and "gap > %s" in sql and "GROUP BY room_id" in sql
    assert tuple(captured["args"]) == (30, 900)
    assert sql.lstrip().upper().startswith("SELECT") and not any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE"))
