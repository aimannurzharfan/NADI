"""Deleting every stored record for a PDPA request: the admin action and scripts/delete_all_data.py."""
import pytest
from fastapi.testclient import TestClient

from server import alerts, incident, labels, main, privacy, store
from tests.util import LOCAL_URL

TOKEN = "privacy-token-0123456789"


class FakeMySQL:
    """Counts DELETE statements per table."""

    def __init__(self):
        self.deleted = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.deleted.append(sql)
        return 7


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("LABELS_PATH", str(tmp_path / "labels.csv"))
    monkeypatch.setenv("INCIDENT_DIR", str(tmp_path / "incidents"))
    mysql = FakeMySQL()
    monkeypatch.setattr(store, "mysql", mysql)
    train = tmp_path / "train.csv"
    train.write_text("room_id,ts\n", encoding="utf-8")
    monkeypatch.setattr(privacy, "TRAIN", train)
    labels.add("room1", 2, 1000)
    alerts.send("info", "alert.audit_start_subject", "alert.audit_body", who="w", time="07:00:00")
    store.audit({"ts": 1, "action": "start", "by": "w", "ip": "10.0.0.1"})
    store.r.hset("room:room1", mapping={"headcount": 2, "count_ts": 1})
    store.r.sadd("rooms", "room1")
    store.r.sadd("devices", "nadi-recv-1")
    store.r.hset("device:nadi-recv-1", mapping={"last_seen": 1})
    (tmp_path / "incidents" / "20260101-000000-real-abcd").mkdir(parents=True)
    return {"mysql": mysql, "train": train, "tmp": tmp_path}


def api(ip="10.0.0.9"):
    return TestClient(main.app, client=(ip, 5000), base_url=LOCAL_URL)


def test_delete_needs_admin_and_the_typed_phrase(world):
    assert api().post("/api/data/delete", json={"confirm": "DELETE ALL DATA"}).status_code == 401
    h = {"X-Admin-Token": TOKEN}
    for wrong in ("", "delete all data", "DELETE ALL", "yes"):
        assert api().post("/api/data/delete", json={"confirm": wrong}, headers=h).status_code == 422
    assert store.audit_log() and labels.read()  # nothing touched


def test_delete_removes_everything_and_leaves_one_audit_entry(world):
    out = api().post("/api/data/delete", json={"confirm": "DELETE ALL DATA"}, headers={"X-Admin-Token": TOKEN}).json()
    assert out["ok"] and out["deleted"]["occupancy"] == 7 and out["deleted"]["climate"] == 7
    assert out["deleted"]["incidents"] == 1 and out["deleted"]["files"] == 2
    deleted = [sql for sql in world["mysql"].deleted if sql.startswith("DELETE")]
    assert deleted == ["DELETE FROM occupancy", "DELETE FROM climate", "DELETE FROM energy_settings"]  # who changed them goes too
    assert labels.read() == [] and not world["train"].exists()
    assert alerts.recent() == [] and not store.r.exists("room:room1", "rooms", "devices", "device:nadi-recv-1")
    assert incident.reports() == [] and not any((world["tmp"] / "incidents").iterdir())
    log = store.audit_log()
    assert len(log) == 1 and log[0]["action"] == "delete_all" and log[0]["by"] == "admin"


def test_the_malay_phrase_works_too(world):
    res = api().post("/api/data/delete", json={"confirm": "PADAM SEMUA DATA"}, headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200


def test_refused_during_an_emergency(world):
    store.start_emergency(1, "w", "drill", "20260101-000000-drill-abcd")
    res = api().post("/api/data/delete", json={"confirm": "DELETE ALL DATA"}, headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 409 and labels.read()


def test_script_asks_for_the_phrase(world, monkeypatch, capsys):
    from scripts import delete_all_data

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit):
        delete_all_data.main([])
    assert labels.read()
    out = delete_all_data.main(["--confirm", "DELETE ALL DATA"])
    assert out["occupancy"] == 7 and labels.read() == []
    assert store.audit_log()[0]["by"] == "script"
