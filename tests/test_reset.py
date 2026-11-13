"""The demo reset and the Calibration page: a reset must keep the stored reports inside BOTH kinds of label
(labelled empty and labelled occupied), and the detector must hand both back. sqlite3 stands in for MySQL, so the
real DELETE and SELECT statements run against a real SQL engine. No Redis or MySQL needed."""
import pytest

from server import labels, main, store
from tests.test_scale import SqliteAsMysql


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("LABELS_PATH", str(tmp_path / "labels.csv"))
    monkeypatch.setattr(main, "_detector_cache", {})
    db = SqliteAsMysql()
    monkeypatch.setattr(store, "mysql", lambda: db)
    return db


def stored(db, rows):
    for ts, std in rows:
        db.execute("INSERT INTO occupancy VALUES (%s, %s, %s, 'RECV-1')", ("room1", ts, std))


def test_a_reset_keeps_labelled_empty_and_labelled_occupied_reports(db):
    labels.add("room1", 0, 1000)   # labelled empty from 1000 ...
    labels.add("room1", 1, 1120)   # ... labelled "1 person" from 1120 ...
    labels.stop("room1", 1240)     # ... until 1240
    stored(db, [(900, 0.4), (1010, 0.31), (1060, 0.44), (1110, 0.52), (1130, 2.1), (1180, 2.6), (1230, 1.9), (1300, 0.3)])
    out = store.clear_demo_data(keep=labels.segments(), now=2000)
    assert [ts for _, ts in db.rows()] == [1010, 1060, 1110, 1130, 1180, 1230]  # inside a label: kept, of both kinds
    assert out["kept"] == 6 and out["occupancy"] == 2
    points = main.labelled_points(2000)["room1"]
    assert [(p["ts"], p["headcount_label"]) for p in points] == [(1010, 0), (1060, 0), (1110, 0), (1130, 1), (1180, 1), (1230, 1)]
    assert {p["headcount_label"] for p in points} == {0, 1}


def test_a_reset_keeps_an_occupied_label_that_is_still_running(db):
    labels.add("room1", 0, 1000)
    labels.add("room1", 2, 1100)   # still open when the reset runs
    stored(db, [(1050, 0.3), (1150, 2.2), (1900, 2.4)])
    store.clear_demo_data(keep=labels.segments(), now=2000)
    points = main.labelled_points(2000)["room1"]
    assert [(p["ts"], p["headcount_label"]) for p in points] == [(1050, 0), (1150, 2), (1900, 2)]


def test_the_boundary_report_between_two_labels_is_kept_once(db):
    labels.add("room1", 0, 1000)
    labels.add("room1", 1, 1100)
    labels.stop("room1", 1200)
    stored(db, [(1100, 0.9)])  # sent in the second the label changed: it belongs to the label that was running
    store.clear_demo_data(keep=labels.segments(), now=2000)
    assert main.labelled_points(2000)["room1"] == [{"ts": 1100, "headcount_label": 0, "motion_std": 0.9}]
