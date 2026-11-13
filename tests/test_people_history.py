"""The people chart's history: peak and minutes occupied per bucket (1 min, 30 min, 3 h in Malaysian time, a Malaysian
day), gaps left out, and since when the room has been empty or occupied. sqlite3 stands in for MySQL."""
import pytest
from fastapi.testclient import TestClient

from server import main, store, timeutil
from tests.test_history_30d import Db
from tests.util import LOCAL_URL


@pytest.fixture
def db(monkeypatch):
    d = Db()
    monkeypatch.setattr(store, "mysql", d)
    monkeypatch.setattr(main, "_history_cache", {})
    monkeypatch.setattr(main, "_since_cache", {})
    return d


def api():
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


def add(db, rows):
    db.db.executemany("INSERT INTO occupancy VALUES (?, ?, ?, 0.3, 'RECV-1')", rows)


def test_buckets_by_range():
    assert [main.people_bucket(m) for m in (60, 61, 1440, 1441, 10080, 10081, 43200)] == [60, 1800, 1800, 10800, 10800, 86400, 86400]


def test_one_hour_is_a_point_a_minute_with_peak_and_minutes_occupied(db):
    now = int(main.time.time())
    m = now // 60 * 60 - 600
    add(db, [("room1", m + s, 2 if s == 20 else 0) for s in (0, 10, 20, 30)]          # one minute: peak 2
        + [("room1", m + 120 + s, 0) for s in (0, 10)]                                 # an empty minute
        + [("room2", m, 5)])                                                           # another room: never mixed in
    out = api().get("/api/history?minutes=60&room=room1&view=people").json()
    assert out["bucket_s"] == 60 and out["room_id"] == "room1"
    assert out["people"] == [[m, 2, 1], [m + 120, 0, 0]]  # the minute between has no report: left out, a gap


def test_a_day_is_30_minute_points_and_minutes_occupied_counts_minutes_not_reports(db):
    now = int(main.time.time())
    b = now // 1800 * 1800 - 3600
    rows = [("room1", b + minute * 60 + s, 1) for minute in range(7) for s in (0, 10, 20, 30, 40, 50)]  # 7 minutes, 42 reports
    rows += [("room1", b + minute * 60, 0) for minute in range(7, 30)]
    add(db, rows)
    out = api().get("/api/history?minutes=1440&room=room1&view=people").json()
    assert out["bucket_s"] == 1800
    assert out["people"] == [[b, 1, 7]]


def test_seven_days_are_3_hour_points_on_malaysian_clock_hours(db):
    now = int(main.time.time())
    midnight = timeutil.midnight(now - 2 * 86400)
    add(db, [("room1", midnight + 3600, 1), ("room1", midnight + 2 * 3600, 3), ("room1", midnight + 3 * 3600 + 60, 0)])
    out = api().get("/api/history?minutes=10080&room=room1&view=people").json()
    assert out["bucket_s"] == 10800
    assert out["people"] == [[midnight, 3, 2], [midnight + 10800, 0, 0]]  # 00:00 and 03:00 Malaysia time


def test_thirty_days_are_malaysian_days(db):
    now = int(main.time.time())
    day = timeutil.midnight(now - 5 * 86400)
    add(db, [("room1", day + 60, 0), ("room1", day + 86400 - 60, 4)])
    out = api().get("/api/history?minutes=43200&room=room1&view=people").json()
    assert out["bucket_s"] == 86400 and out["people"] == [[day, 4, 1]]


def test_since_is_the_first_report_of_the_unbroken_state(db):
    now = int(main.time.time())
    add(db, [("room1", now - 500, 0), ("room1", now - 400, 1), ("room1", now - 300, 0), ("room1", now - 200, 2),
             ("room1", now - 100, 1), ("room1", now - 10, 3)])
    out = api().get("/api/history?minutes=60&room=room1&view=people").json()
    assert out["since"] == {"occupied": True, "ts": now - 200}  # occupied since the report after the last empty one


def test_since_for_an_empty_room_and_for_a_room_that_never_changed(db):
    now = int(main.time.time())
    add(db, [("room1", now - 300, 2), ("room1", now - 200, 0), ("room1", now - 100, 0)])
    add(db, [("room2", now - 300, 0), ("room2", now - 100, 0)])
    assert api().get("/api/history?minutes=60&room=room1&view=people").json()["since"] == {"occupied": False, "ts": now - 200}
    assert api().get("/api/history?minutes=60&room=room2&view=people").json()["since"] == {"occupied": False, "ts": None}


def test_a_room_without_reports_has_no_points_and_no_since(db):
    out = api().get("/api/history?minutes=60&room=room3&view=people").json()
    assert out["people"] == [] and out["since"] is None


def test_the_view_needs_a_known_room_and_the_plain_history_is_unchanged(db):
    now = int(main.time.time())
    add(db, [("room1", now - 100, 1)])
    assert api().get("/api/history?minutes=60&view=people").status_code == 422
    assert api().get("/api/history?minutes=60&room=nowhere&view=people").status_code == 422
    assert api().get("/api/history?minutes=60&room=room1&view=other").status_code == 422
    plain = api().get("/api/history?minutes=60&room=room1").json()
    assert "people" not in plain and plain["rooms"]["room1"] == [[(now - 100) // 60 * 60, 1]]
