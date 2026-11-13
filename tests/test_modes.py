"""Mode switch, admin token protection and model fallback. No Redis/MySQL/Ollama/cloud needed."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import alerts, chat, config, logic, main, model
from sim import fake_sensor

CLOUD_VARS = {"SMN_TOPIC_URN": "urn:smn:x", "HUAWEICLOUD_AK": "ak", "HUAWEICLOUD_SK": "sk",
              "MAAS_BASE_URL": "https://maas.example/v1", "MAAS_API_KEY": "k", "MAAS_MODEL": "qwen-maas"}


# --- mode switch ---

def test_mode_defaults_to_local(monkeypatch):
    monkeypatch.delenv("NADI_MODE", raising=False)
    assert config.mode() == "local"
    monkeypatch.setenv("NADI_MODE", " Huawei ")
    assert config.mode() == "huawei"
    monkeypatch.setenv("NADI_MODE", "cloud")
    with pytest.raises(ValueError):
        config.mode()


def test_local_mode_never_uses_huawei_even_with_keys(monkeypatch):
    for k, v in CLOUD_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    assert not alerts.smn_enabled()
    be = chat.backend()
    assert be["kind"] == "ollama" and "127.0.0.1" in be["base_url"]
    assert "Huawei" not in be["label"] and "MaaS" not in be["label"]


def test_huawei_mode_uses_smn_and_maas(monkeypatch):
    for k, v in CLOUD_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert alerts.smn_enabled()
    be = chat.backend()
    assert be["kind"] == "maas" and be["model"] == "qwen-maas" and "MaaS" in be["label"]
    monkeypatch.delenv("MAAS_API_KEY")
    assert chat.backend() is None  # huawei mode never falls back to a local LLM


def test_sim_target_follows_mode(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    assert fake_sensor.mode() == "local"
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert fake_sensor.mode() == "huawei"
    assert fake_sensor.report_topic("dev1") == "$oc/devices/dev1/sys/properties/report"


def test_chat_falls_back_when_ollama_is_down(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9/v1")  # nothing listens on port 9
    rooms = [{"room_id": "room1", "headcount": 2, "temp_c": 24.0, "live": True, "waste": None}]
    out = chat.answer("How many people inside?", {"now": 0, "emergency": {"on": False}, "rooms": rooms})
    assert out["scope"]["kind"] == "building"
    assert {k: out[k] for k in ("answer", "source", "model")} == {"answer": "Whole building: 2 people inside, in 1 room.",
                                                                    "source": "fallback", "model": chat.FALLBACK_LABEL}


# --- admin token on /api/emergency and /api/chat ---

@pytest.fixture
def api(monkeypatch):
    """Server routes with Redis/MySQL and the LLM stubbed out."""
    monkeypatch.setattr(main, "room_views", lambda now, rooms=None: [])
    monkeypatch.setattr(main.store, "rooms", lambda: [])
    state = {"on": False, "since": None}
    monkeypatch.setattr(main.store, "emergency", lambda: dict(state))

    def start(now, by, kind="real", incident_id=None):
        if state["on"]:
            return False
        state.update(on=True, since=now)
        return True

    def end():
        was = dict(state) if state["on"] else None
        state.update(on=False, since=None)
        return was

    monkeypatch.setattr(main.store, "start_emergency", start)
    monkeypatch.setattr(main.store, "end_emergency", end)
    monkeypatch.setattr(main.store, "audit", lambda entry: None)
    monkeypatch.setattr(main.alerts, "send", lambda *a, **k: "console")
    monkeypatch.setenv("OLLAMA_MODEL", "")  # chat goes straight to the built-in answers
    monkeypatch.setenv("NADI_MODE", "local")
    return state


def test_token_required_when_set(api, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token-0123456789")
    c = TestClient(main.app, base_url=LOCAL_URL)
    assert c.post("/api/chat", json={"question": "hi"}).status_code == 401
    assert c.post("/api/chat", json={"question": "hi"}, headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert c.post("/api/emergency", json={"on": True}).status_code == 401
    assert api["on"] is False
    ok = c.post("/api/chat", json={"question": "hi"}, headers={"X-Admin-Token": "s3cret-token-0123456789"})
    assert ok.status_code == 200 and ok.json()["source"] == "fallback"
    assert c.post("/api/emergency", json={"on": True}, headers={"X-Admin-Token": "s3cret-token-0123456789"}).json()["on"] is True


def test_no_token_means_localhost_only(api, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    remote = TestClient(main.app, client=("192.168.1.50", 50000), base_url=LOCAL_URL)
    assert remote.post("/api/chat", json={"question": "hi"}).status_code == 403
    assert remote.post("/api/emergency", json={"on": True}).status_code == 403
    local = TestClient(main.app, client=("127.0.0.1", 50000), base_url=LOCAL_URL)
    assert local.post("/api/chat", json={"question": "hi"}).status_code == 200
    assert local.post("/api/emergency", json={"on": True}).json()["on"] is True


def test_no_token_in_huawei_mode_refuses_even_localhost(api, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    monkeypatch.setenv("NADI_MODE", "huawei")
    local = TestClient(main.app, client=("127.0.0.1", 50000), base_url=LOCAL_URL)
    assert local.post("/api/chat", json={"question": "hi"}).status_code == 403
    assert local.post("/api/emergency", json={"on": True}).status_code == 403


def test_read_only_routes_stay_open(api, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token-0123456789")
    monkeypatch.setattr(main.alerts, "recent", lambda lang="en": [])
    monkeypatch.setattr(main.store, "waste_today", lambda now: 1.5)
    c = TestClient(main.app, client=("192.168.1.50", 50000), base_url=LOCAL_URL)
    res = c.get("/api/rooms")
    assert res.status_code == 200 and res.json()["waste_today_rm"] == 1.5


def test_info_admin_rule(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    assert main.admin_rule() == "localhost"
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert main.admin_rule() == "refused"
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token-0123456789")
    assert main.admin_rule() == "token"


def test_tests_do_not_read_the_developer_env():
    """conftest drops every documented setting, so a calibrated .env on the laptop cannot change a test."""
    import os
    assert logic.THRESHOLDS == [0.35, 0.95, 1.55] and logic.WASTE_AFTER_S == 600 and main.REPORT_INTERVAL_S == 20
    assert not os.getenv("ROOM_NAMES") and not os.getenv("ADMIN_TOKEN") and not os.getenv("MODEL_PATH")


# --- ROOM_NAMES, BUILDING_NAME, LEVEL_NAME ---

def test_room_names_parsing():
    assert config.room_names("room1:Lab 2,room2:Hall A,room3:Room 3") == {"room1": "Lab 2", "room2": "Hall A", "room3": "Room 3"}
    assert config.room_names(" room1 : Lab 2 , ,room2:,:Hall B,room3,room4:Bilik: Mesyuarat ") == {
        "room1": "Lab 2", "room4": "Bilik: Mesyuarat"}  # blanks and missing parts skipped; only the first colon splits
    assert config.room_names("") == {}
    assert len(config.room_names("room1:" + "x" * 100)["room1"]) == 40


def test_room_names_from_env_and_fallback(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2")
    assert config.room_name("room1") == "Lab 2"
    assert config.room_name("room9") == "room9"  # not in ROOM_NAMES and not on the floor plan: the ID is all there is
    assert config.room_name("room2") == "Hall A"  # not in ROOM_NAMES: the name written on the floor plan
    assert config.display_names() == {"room1": "Lab 2", "room2": "Hall A", "room3": "Room 3"}
    monkeypatch.setenv("ROOM_NAMES", "room2:Dewan Kuliah 1")
    assert config.room_name("room2") == "Dewan Kuliah 1" and config.room_name("room1") == "Lab 2"  # ROOM_NAMES wins
    assert config.display_names()["room2"] == "Dewan Kuliah 1"
    monkeypatch.delenv("ROOM_NAMES")
    assert config.room_names() == {}
    monkeypatch.delenv("BUILDING_NAME", raising=False)
    monkeypatch.setenv("LEVEL_NAME", "  ")
    assert (config.building_name(), config.level_name()) == ("Demo Building", "Level 4")
    monkeypatch.setenv("BUILDING_NAME", "Block N28")
    assert config.building_name() == "Block N28"


def test_room_views_keep_ids_and_add_names(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room2:Hall A")
    monkeypatch.setattr(main.store, "rooms", lambda: [
        {"room_id": "room2", "headcount": 1, "count_ts": 100, "temp_c": 24.0, "humidity": 60.0, "empty_cold_since": None},
        {"room_id": "room5", "headcount": 0, "count_ts": 100, "temp_c": None, "humidity": None, "empty_cold_since": None}])
    views = main.room_views(110)
    assert [(v["room_id"], v["name"]) for v in views] == [("room2", "Hall A"), ("room5", "room5")]


# --- model fallback ---

TINY = {  # 1 feature, identity hidden layer, picks class 1 when motion_std > 0.5
    "framework": "MindSpore test", "platform": "local", "trained_on": "synthetic",
    "features": ["motion_std"], "mean": [0.0], "std": [1.0], "classes": [0, 1],
    "layers": [{"W": [[1.0]], "b": [0.0]}, {"W": [[-1.0], [1.0]], "b": [0.5, -0.5]}],
}


def test_model_missing_uses_threshold(tmp_path):
    count, source = model.headcount({"motion_std": 1.25}, path=tmp_path / "none.json")
    assert (count, source) == (2, "threshold")
    assert model.info(path=tmp_path / "none.json") is None


def test_model_broken_uses_threshold(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"features": ["motion_std"]}')
    assert model.headcount({"motion_std": 1.25}, path=bad) == (2, "threshold")


def test_model_present_is_used(tmp_path):
    good = tmp_path / "m.json"
    good.write_text(json.dumps(TINY))
    assert model.headcount({"motion_std": 0.9}, path=good) == (1, "mindspore")
    assert model.headcount({"motion_std": 0.1}, path=good) == (0, "mindspore")
    assert model.info(path=good)["trained_on"] == "synthetic"


def test_ingest_uses_model_when_present(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(main.store, "save_csi", lambda room_id, ts, count, p: saved.append(count))
    monkeypatch.setattr(main, "check_waste", lambda room_id, now: None)
    svc = [{"service_id": "csi", "properties": {"room_id": "room1", "ts": 0, "motion_std": 0.9}}]
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "none.json"))
    main.ingest(svc)
    good = tmp_path / "m.json"
    good.write_text(json.dumps(TINY))
    monkeypatch.setenv("MODEL_PATH", str(good))
    main.ingest(svc)
    assert saved == [1, 1]  # threshold rule says 1 for 0.9; tiny model also says 1
    svc[0]["properties"]["motion_std"] = 0.4
    main.ingest(svc)
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "none.json"))
    main.ingest(svc)
    assert saved[2:] == [0, 1]  # model: 0.4 < 0.5 -> 0; threshold: 0.4 > 0.35 -> 1


def test_built_with_follows_dashboard_language(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "")  # no LLM badge, no network
    en, ms = main.built_with("en"), main.built_with("ms")
    assert "Console alerts" in en and "Redis (local)" in en
    assert "Amaran konsol" in ms and "Redis (tempatan)" in ms
    assert not any("aircon" in b.lower() for b in en + ms)


def test_info_says_who_would_word_an_answer(monkeypatch):
    """chat_source: "rules" while no model is reachable, "ollama" when the local model is up, never "maas" in local mode."""
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    for key, value in CLOUD_VARS.items():
        monkeypatch.setenv(key, value)
    c = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: False)
    assert chat.source_now() == "rules" and c.get("/api/info").json()["chat_source"] == "rules"
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: True)
    assert chat.source_now() == "ollama" and c.get("/api/info").json()["chat_source"] == "ollama"
    monkeypatch.setenv("OLLAMA_MODEL", "")
    assert chat.source_now() == "rules"
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert chat.source_now() == "maas"
