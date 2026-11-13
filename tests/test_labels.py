"""/label page backend: taps write labels.csv in the teammates' format, undo, stop, admin rule. No services needed."""
import csv

import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from ml import prepare
from server import labels, main


@pytest.fixture
def csv_path(tmp_path, monkeypatch):
    p = tmp_path / "labels.csv"
    monkeypatch.setenv("LABELS_PATH", str(p))
    return p


def rows(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_tap_closes_previous_label_for_that_room_only(csv_path):
    labels.add("room1", 0, 100)
    labels.add("room2", 2, 110)
    labels.add("room1", 1, 160)
    assert rows(csv_path) == [
        {"room_id": "room1", "start_ts": "100", "end_ts": "160", "headcount": "0"},
        {"room_id": "room2", "start_ts": "110", "end_ts": "", "headcount": "2"},
        {"room_id": "room1", "start_ts": "160", "end_ts": "", "headcount": "1"},
    ]
    assert labels.open_segments() == {"room2": {"headcount": 2, "start_ts": 110}, "room1": {"headcount": 1, "start_ts": 160}}


def test_undo_removes_last_and_reopens_previous(csv_path):
    labels.add("room1", 0, 100)
    labels.add("room1", 3, 200)
    assert labels.undo()["headcount"] == "3"
    assert rows(csv_path) == [{"room_id": "room1", "start_ts": "100", "end_ts": "", "headcount": "0"}]
    labels.undo()
    assert rows(csv_path) == [] and labels.undo() is None


def test_stop_closes_without_new_label(csv_path):
    labels.add("room1", 2, 100)
    assert labels.stop("room1", 130) is True
    assert labels.stop("room1", 140) is False
    assert labels.open_segments() == {}
    assert labels.recent() == [{"room_id": "room1", "start_ts": 100, "end_ts": 130, "headcount": 2}]


def test_recent_is_last_five_newest_first(csv_path):
    for i in range(7):
        labels.add("room1", i % 4, 100 + i)
    assert [r["start_ts"] for r in labels.recent()] == [106, 105, 104, 103, 102]


def test_prepare_skips_running_labels(csv_path, capsys):
    labels.add("room1", 1, 100)
    labels.add("room1", 2, 200)
    assert prepare.read_labels(csv_path) == [("room1", 100, 200, 1)]
    assert "still running" in capsys.readouterr().out


@pytest.fixture
def api(csv_path, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "label-token-0123456789")
    monkeypatch.setenv("ADMIN_TOKENS", "")
    return TestClient(main.app, client=("192.168.1.20", 5000), base_url=LOCAL_URL)  # a teammate's phone


H = {"X-Admin-Token": "label-token-0123456789"}


def test_label_api_needs_admin_and_checks_input(api, csv_path):
    assert api.post("/api/labels", json={"room_id": "room1", "headcount": 1}).status_code == 401
    assert api.get("/api/labels").status_code == 401
    assert api.post("/api/labels", json={"room_id": "room99", "headcount": 1}, headers=H).status_code == 422
    assert api.post("/api/labels", json={"room_id": "room1", "headcount": 101}, headers=H).status_code == 422
    assert api.post("/api/labels", json={"room_id": "<script>", "headcount": 1}, headers=H).status_code == 422
    assert not csv_path.exists()
    out = api.post("/api/labels", json={"room_id": "room1", "headcount": 3}, headers=H).json()
    assert out["recent"][0]["headcount"] == 3 and out["open"]["room1"]["headcount"] == 3
    out = api.post("/api/labels", json={"room_id": "room1", "headcount": None}, headers=H).json()
    assert out["open"] == {} and out["recent"][0]["end_ts"] is not None
    assert api.post("/api/labels/undo", headers=H).json()["recent"] == []


def test_label_page_is_served(api):
    res = api.get("/label")
    assert res.status_code == 200 and '<div id="root">' in res.text  # the web console handles /label


def test_label_api_lists_up_to_fifty_recent_labels(api, csv_path):
    """The Calibration page shows ten and opens the rest on request: the answer carries the last 50, newest first."""
    for i in range(60):
        labels.add("room1", i % 3, 1000 + i * 10)
    out = api.get("/api/labels", headers=H).json()
    assert len(out["recent"]) == main.LABELS_SHOWN == 50
    assert [r["start_ts"] for r in out["recent"][:3]] == [1590, 1580, 1570]
    assert out["recent"][-1]["start_ts"] == 1100  # the ten oldest are not sent
    assert out["recent"][0]["name"] and out["open"]["room1"]["start_ts"] == 1590
