"""30 days of history for the live signal card: one point per Malaysian day, days with no report left out (gaps, not
0), and the buckets in which an empty, cold room wasted air conditioning. sqlite3 stands in for MySQL (with FLOOR
added), so the real SELECT statements run."""
import math
import sqlite3

import pytest
from fastapi.testclient import TestClient

from server import main, store, timeutil
from tests.util import LOCAL_URL

DAY = 86400


class Db:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.create_function("FLOOR", 1, math.floor)
        self.db.execute("CREATE TABLE occupancy (room_id TEXT, ts INTEGER, headcount INTEGER, motion_std REAL, source TEXT)")
        self.db.execute("CREATE TABLE climate (room_id TEXT, ts INTEGER, temp_c REAL, humidity REAL)")

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.db.commit()

    def cursor(self):
        return self

    def execute(self, sql, args=()):
        self.last = self.db.execute(sql.replace("%s", "?"), list(args))
        return self.last.rowcount

    def fetchall(self):
        return self.last.fetchall()


@pytest.fixture
def db(monkeypatch):
    d = Db()
    monkeypatch.setattr(store, "mysql", d)
    monkeypatch.setattr(main, "_history_cache", {})
    return d


def api():
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


def test_thirty_days_one_point_per_malaysian_day_with_gaps_and_waste(db, monkeypatch):
    now = int(main.time.time())
    today = timeutil.midnight(now)
    rows, climate = [], []
    for d in range(1, 29):
        if d in (5, 6, 7):  # three days without a single report: the sensor was off
            continue
        day = today - d * DAY
        busy = d % 2 == 0
        for h in (9, 12, 15):
            rows.append(("room1", day + h * 3600, 2 if busy and h == 12 else 0, 0.3, "RECV-1"))
            climate.append(("room1", day + h * 3600, 23.0 if not busy else 27.0, 60.0))
    db.db.executemany("INSERT INTO occupancy VALUES (?, ?, ?, ?, ?)", rows)
    db.db.executemany("INSERT INTO climate VALUES (?, ?, ?, ?)", climate)
    out = api().get("/api/history?minutes=43200&room=room1").json()
    assert out["bucket_s"] == DAY
    points = out["rooms"]["room1"]
    assert all(timeutil.midnight(ts) == ts for ts, _ in points)  # each point starts at midnight Malaysia time
    days = {(today - ts) // DAY for ts, _ in points}
    assert days == set(range(1, 29)) - {5, 6, 7}  # the three silent days are missing (drawn as gaps), not 0
    assert dict(points)[today - 2 * DAY] == 2 and dict(points)[today - 3 * DAY] == 0  # the busiest moment of the day
    # waste: empty all day and below 26 °C (the odd days); a busy day, or a day with no report, is never shaded
    assert set(out["waste"]) == {today - d * DAY for d in range(1, 29) if d % 2 and d not in (5, 7)}


def test_a_day_is_shaded_only_when_it_was_cold_by_the_temperature_in_force_then(db, monkeypatch):
    from server import energy
    now = int(main.time.time())
    day = timeutil.midnight(now) - 3 * DAY
    db.db.execute("INSERT INTO occupancy VALUES ('room1', ?, 0, 0.3, 'RECV-1')", (day + 3600,))
    db.db.execute("INSERT INTO climate VALUES ('room1', ?, 26.5, 60.0)", (day + 3600,))
    assert api().get("/api/history?minutes=43200&room=room1").json()["waste"] == []  # 26.5 °C is not below 26
    monkeypatch.setattr(energy, "current", lambda now=None: {**energy.defaults(), "ac_on_below_c": 27.0})
    main._history_cache.clear()
    assert api().get("/api/history?minutes=43200&room=room1").json()["waste"] == [day]


def test_the_range_is_capped_at_thirty_days(db):
    out = api().get("/api/history?minutes=999999").json()
    assert out["bucket_s"] >= DAY
