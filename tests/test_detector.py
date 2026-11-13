"""GET /api/detector: what is counting people right now (the calibrated rule or a trained model) and the labelled
reports behind the calibration chart. Read only, admin only like the labels it reads. No Redis or MySQL needed."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import health, labels, logic, main, model, store
from tests.util import LOCAL_URL

ADMIN = "detector-admin-token-0123456789"
VIEWER = "viewer-token-0123456789abcdef"


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("LABELS_PATH", str(tmp_path / "labels.csv"))
    for k in ("ADMIN_TOKEN", "ADMIN_TOKENS", "VIEWER_TOKEN"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(main, "_detector_cache", {})
    monkeypatch.setattr(model, "load", lambda path=None: None)  # the threshold rule is counting
    monkeypatch.setattr(model, "DEFAULT_PATH", tmp_path / "no_model.json")
    return TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)


@pytest.fixture
def rows(monkeypatch):
    """Stands in for MySQL: seven stored reports of room1, one from the simulator and one from no known device."""
    calls = []
    reports = [[100, 0.31, "RECV-1"], [110, 0.42, "RECV-1"], [120, 0.9, "nadi-sim"], [130, 0.5, None],
               [200, 2.25, "RECV-1"], [260, 1.9123456, "RECV-1"], [400, 3.3, "RECV-1"]]

    def labelled_reports(room_id, since, until):
        calls.append((room_id, since, until))
        return [list(r) for r in reports if since <= r[0] <= until] if room_id == "room1" else []

    monkeypatch.setattr(store, "labelled_reports", labelled_reports)
    return calls


def test_rule_mode_with_the_labelled_reports(api, rows):
    labels.add("room1", 0, 100)
    labels.add("room1", 1, 150)
    labels.stop("room1", 300)
    out = api.get("/api/detector").json()
    assert out["mode"] == "rule" and out["threshold"] == logic.THRESHOLDS[0] and out["model"] is None
    assert out["report_interval_s"] == main.REPORT_INTERVAL_S
    # inside a label and from a real board: the report from the simulator, the one from no known device and the one
    # after "Stop" are not labelled data
    assert out["rooms"] == {"room1": [
        {"ts": 100, "headcount_label": 0, "motion_std": 0.31}, {"ts": 110, "headcount_label": 0, "motion_std": 0.42},
        {"ts": 200, "headcount_label": 1, "motion_std": 2.25}, {"ts": 260, "headcount_label": 1, "motion_std": 1.9123}]}
    assert rows == [("room1", 100, 300)]


def test_same_matching_as_the_calibration_script(api, rows):
    """The points per label are the groups scripts/calibrate.py works from."""
    from scripts import calibrate
    labels.add("room1", 0, 100)
    labels.add("room1", 2, 150)
    labels.stop("room1", 300)
    segments = [(100, 150, 0), (150, 300, 2)]
    kept = [(ts, std) for ts, std, src in store.labelled_reports("room1", 100, 300) if src and src != "nadi-sim"]
    groups = calibrate.group_by_label(kept, segments, int(time.time()))
    mine = {}
    for p in api.get("/api/detector").json()["rooms"]["room1"]:
        mine.setdefault(p["headcount_label"], []).append(p["motion_std"])
    assert {k: [round(v, 4) for v in vs] for k, vs in groups.items()} == mine


def test_an_open_label_runs_until_now(api, rows):
    labels.add("room1", 1, 150)
    out = api.get("/api/detector").json()
    assert [p["ts"] for p in out["rooms"]["room1"]] == [200, 260, 400]


def test_no_labels_yet(api, rows):
    out = api.get("/api/detector").json()
    assert out["rooms"] == {} and rows == []


def test_rooms_that_are_not_known_are_left_out(api, rows):
    labels.add("room1", 0, 100)
    labels.add("../etc", 0, 100)
    assert list(api.get("/api/detector").json()["rooms"]) == ["room1"]


def test_model_facts_come_from_the_file_and_never_claim_to_be_active(api, rows, monkeypatch, tmp_path):
    f = tmp_path / "nadi_model.json"
    f.write_text(json.dumps({"framework": "MindSpore 2.10.0", "platform": "local", "trained_on": "synthetic",
                             "trained_at": 1792843820, "n_train": 3600, "accuracy": 1.0, "threshold_accuracy": 0.9967,
                             "layers": [{"W": [[1.0]], "b": [0.0]}], "something_else": "x"}), encoding="utf-8")
    monkeypatch.setattr(model, "DEFAULT_PATH", f)
    out = api.get("/api/detector").json()
    assert out["mode"] == "rule" and out["threshold"] is not None
    assert out["model"] == {"framework": "MindSpore 2.10.0", "platform": "local", "trained_on": "synthetic",
                            "accuracy": 1.0, "threshold_accuracy": 0.9967, "trained_at": 1792843820, "n_train": 3600,
                            "n_test": None, "active": False}


def test_a_broken_model_file_is_no_model(api, rows, monkeypatch, tmp_path):
    f = tmp_path / "nadi_model.json"
    f.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(model, "DEFAULT_PATH", f)
    assert api.get("/api/detector").json()["model"] is None
    f.write_text("[1, 2]", encoding="utf-8")
    assert api.get("/api/detector").json()["model"] is None


def test_model_mode_only_when_a_model_is_loaded(api, rows, monkeypatch):
    loaded = {"framework": "MindSpore 2.10.0", "trained_on": "real CSI", "accuracy": 0.97, "threshold_accuracy": 0.93,
              "n_train": 800, "n_test": 200, "features": ["motion_std"]}
    monkeypatch.setattr(model, "load", lambda path=None: loaded)
    out = api.get("/api/detector").json()
    assert out["mode"] == "model" and out["threshold"] is None
    assert out["model"]["active"] is True and out["model"]["trained_on"] == "real CSI" and "features" not in out["model"]


def test_admin_only(api, rows, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("VIEWER_TOKEN", VIEWER)
    far = TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)
    assert far.get("/api/detector").status_code in (401, 403)
    assert far.get("/api/detector", headers={"X-Viewer-Token": VIEWER}).status_code in (401, 403)
    assert far.get("/api/detector", headers={"X-Admin-Token": ADMIN, "X-Viewer-Token": VIEWER}).status_code == 200


def test_read_only_and_the_read_rate_bucket(api, rows):
    assert api.post("/api/detector", json={}).status_code == 405
    assert main.bucket_of("GET", "/api/detector") == "read"


def test_one_query_per_room_however_often_it_is_asked(api, rows):
    labels.add("room1", 0, 100)
    for _ in range(5):
        assert api.get("/api/detector").status_code == 200
    assert len(rows) == 1


def test_503_while_mysql_is_offline(api, rows):
    labels.add("room1", 0, 100)
    health.mark("mysql", False)
    assert api.get("/api/detector").status_code == 503
    assert rows == []  # MySQL is not asked while it is known to be down


def test_a_burst_while_mysql_is_down_waits_for_mysql_once(api, monkeypatch):
    labels.add("room1", 0, 100)
    calls, codes = [], []

    def slow_and_gone(*a, **k):
        calls.append(1)
        time.sleep(0.3)
        raise store.MYSQL_ERRORS[0]("gone away")

    monkeypatch.setattr(store, "labelled_reports", slow_and_gone)
    threads = [threading.Thread(target=lambda: codes.append(api.get("/api/detector").status_code)) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    assert codes == [503] * 6 and len(calls) == 1
    assert not health.ok("mysql")


def test_query_binds_its_values(monkeypatch):
    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, args):
            conn.sql, conn.args = sql, list(args)

        def fetchall(self):
            return [(40, 1.7, "RECV-1"), (20, float("nan"), "RECV-1"), (10, 0.2, None)]

    class Conn(Cur):
        def cursor(self):
            return Cur()

    conn = Conn()
    monkeypatch.setattr(store, "mysql", lambda: conn)
    assert store.labelled_reports("room1", 5, 50) == [[10, 0.2, None], [40, 1.7, "RECV-1"]]  # oldest first, no NaN
    assert conn.args == ["room1", 5, 50, store.LABELLED_MAX_ROWS] and "room1" not in conn.sql


# ---- the short form on GET /api/info, for the overview's Detection card ----

def test_info_names_the_rule_as_the_live_detector(api, rows, monkeypatch, tmp_path):
    f = tmp_path / "nadi_model.json"
    f.write_text(json.dumps({"framework": "MindSpore 2.10.0", "trained_on": "synthetic", "accuracy": 1.0,
                             "threshold_accuracy": 0.9967, "n_train": 3600, "layers": [{"W": [[1.0]], "b": [0.0]}]}),
                 encoding="utf-8")
    monkeypatch.setattr(model, "DEFAULT_PATH", f)
    d = api.get("/api/info").json()["detector"]
    assert set(d) == {"mode", "threshold", "model"}  # no labelled reports here: those stay admin only
    assert d["mode"] == "rule" and d["threshold"] == logic.THRESHOLDS[0]
    assert d["model"]["active"] is False and d["model"]["trained_on"] == "synthetic" and "layers" not in d["model"]


def test_info_names_the_model_only_when_one_is_loaded(api, rows, monkeypatch):
    monkeypatch.setattr(model, "load", lambda path=None: {"framework": "MindSpore 2.10.0", "trained_on": "real CSI"})
    d = api.get("/api/info").json()["detector"]
    assert d["mode"] == "model" and d["threshold"] is None and d["model"]["active"] is True


def test_info_detector_without_a_model_file(api, rows, monkeypatch, tmp_path):
    monkeypatch.setattr(model, "DEFAULT_PATH", tmp_path / "missing.json")
    d = api.get("/api/info").json()["detector"]
    assert d["mode"] == "rule" and d["model"] is None


def test_info_detector_needs_no_mysql_and_keeps_the_viewer_rule(api, rows, monkeypatch):
    health.mark("mysql", False)
    assert api.get("/api/info").json()["detector"]["mode"] == "rule"
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("VIEWER_TOKEN", VIEWER)
    far = TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)
    assert far.get("/api/info").status_code in (401, 403)
    assert "detector" in far.get("/api/info", headers={"X-Viewer-Token": VIEWER}).json()
