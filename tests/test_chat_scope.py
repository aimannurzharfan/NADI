"""Ask NADI's scope (server/scope.py): a floor or the whole building, a floor named in the question, emergency and
drill locking it to the whole building with a per-floor breakdown, a floor with no sensors, the example building,
and the model rewording only the checked, scoped body (never the prefix or the breakdown)."""
import json

import pytest
from fastapi.testclient import TestClient

from server import chat, main, plan, site
from tests.util import LOCAL_URL

NOW = 1_800_000_000
FAKE_BE = {"kind": "ollama", "label": "fake model", "model": "fake", "base_url": "", "api_key": "", "timeout": 1}


def room(room_id, name, headcount, live=True):
    return {"room_id": room_id, "name": name, "headcount": headcount, "temp_c": 24.0, "humidity": 60.0, "live": live, "waste": None}


ROOMS = [room("room1", "Lab 2", 2), room("room2", "Hall A", 1), room("l5-a", "Room 5.01", 2)]  # 2, not 3: a Wi-Fi 3 means "3 or more"
DATA = {"now": NOW, "emergency": {"on": False}, "rooms": ROOMS}


@pytest.fixture(autouse=True)
def floors(monkeypatch, tmp_path):
    """The demo floor (Level 4, built in), Level 5 drawn from the corridor template, and Level 6 with nothing drawn."""
    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "site.json").write_text(json.dumps({"buildings": [{"id": "b1", "name": None, "code": "", "floors": [
        {"id": "f1", "name": None, "level": None}, {"id": "f2", "name": "Level 5", "level": 5}, {"id": "f3", "name": "Level 6", "level": 6}]}]}),
        encoding="utf-8")
    (folder / "plans" / "f2").mkdir(parents=True)
    (folder / "plans" / "f2" / "v000001.json").write_text(json.dumps({"version": 1, "saved_ts": 1, "saved_by": "admin", "note": "",
                                                                      "plan": site.corridor_plan("l5", 5)}), encoding="utf-8")
    monkeypatch.setenv("SITE_DIR", str(folder))
    monkeypatch.delenv("CHAT_SCOPE", raising=False)
    monkeypatch.setattr(chat, "backend", lambda lang="en": None)  # built-in answers unless a test brings its own model
    plan.refresh()
    yield
    monkeypatch.undo()
    plan.refresh()


@pytest.fixture
def model(monkeypatch):
    calls, reply = [], {"text": None}
    monkeypatch.setattr(chat, "backend", lambda lang="en": FAKE_BE)

    def fake(be, question, checked):
        calls.append((question, checked))
        return reply["text"](checked) if callable(reply["text"]) else reply["text"]
    monkeypatch.setattr(chat, "llm_answer", fake)
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: True)
    return calls, reply


def ask(question, floor=None, data=DATA):
    return chat.answer(question, data, "en", floor)


def test_the_whole_building_or_the_chosen_floor_and_every_answer_says_which():
    out = ask("How many people are inside?")
    assert out["answer"] == "Whole building: 5 people inside, in 3 rooms."
    assert out["scope"] == {"kind": "building", "floor_id": None, "label": "Whole building", "locked": False, "reason": None}
    assert ask("How many people are inside?", "f1")["answer"] == "Level 4: 3 people inside, in 2 rooms."
    assert ask("How many people are inside?", "f2")["answer"] == "Level 5: 2 people inside, in 1 room."
    assert ask("Berapa orang di dalam?", "f1")["answer"] == "Level 4: 3 orang di dalam, di 2 bilik."
    assert ask("Berapa orang di dalam?")["answer"].startswith("Seluruh bangunan: ")
    assert ask("Who is the building manager?", "f1")["answer"].startswith("Level 4: I can answer")  # even the help line


@pytest.mark.parametrize("question", ["How many people on level 4?", "How many people on floor 4?", "Berapa orang di aras 4?",
                                      "Berapa orang di tingkat 4?"])
def test_a_floor_named_in_the_question_wins_over_the_chip(question):
    out = ask(question, "f2")
    assert out["answer"].startswith("Level 4: ") and out["scope"]["floor_id"] == "f1"
    assert "3" in out["answer"] and "5" not in out["answer"]


def test_a_floor_that_does_not_exist_is_said_so():
    out = ask("How many people on level 9?", "f1")
    assert out["answer"] == "Demo Building: There is no level 9 in Demo Building."


def test_a_room_named_in_the_question_is_answered_on_its_own_floor():
    out = ask("How many people in Lab 2?", "f2")
    assert out["answer"].startswith("Level 4: Lab 2") and out["scope"]["floor_id"] == "f1"


def test_emergency_or_drill_locks_the_whole_building_with_a_breakdown_by_floor():
    for drill, reason in ((False, "Emergency mode is on: answers cover the whole building."), (True, "A drill is on: answers cover the whole building.")):
        data = {**DATA, "emergency": {"on": True, "since": NOW - 120, "drill": drill}}
        out = ask("How many people are inside?", "f2", data)  # the chip says Level 5: the emergency wins
        assert out["scope"]["kind"] == "building" and out["scope"]["locked"] is True and out["scope"]["reason"] == reason
        assert out["answer"] == "Whole building: 5 people inside, in 3 rooms. By floor: Level 4: 3 people; Level 5: 2 people."
    data = {**DATA, "emergency": {"on": True, "since": NOW - 120}, "rooms": ROOMS + [room("room3", "Room 3", None, live=False)]}
    out = ask("Which room should rescuers check first?", None, data)
    assert out["answer"].endswith("By floor: Level 4: at least 3 people; Level 5: 2 people.")  # an unknown room: at least


def test_a_floor_with_no_sensors_never_says_zero_people():
    for q in ("How many people are inside?", "Which rooms are empty?", "Berapa orang di dalam?"):
        out = ask(q, "f3")
        assert out["answer"] in ("Level 6: No sensors on this floor.", "Level 6: Tiada sensor di tingkat ini."), out
        assert "0" not in out["answer"]


def test_the_example_building_says_it_is_example_data():
    out = ask("How many people are inside?", "ex-3")
    assert out["answer"] == "Level 3: Example data: this floor has no sensors."
    assert ask("Berapa orang di dalam?", "ex-3")["answer"] == "Aras 3: Data contoh: tingkat ini tiada sensor."


def test_the_model_rewords_only_the_scoped_body_and_is_checked_against_the_scoped_rooms(model):
    calls, reply = model
    reply["text"] = lambda checked: "There are " + checked
    out = ask("How many people are inside?", "f1")
    assert calls == [("How many people are inside?", "3 people inside, in 2 rooms.")]  # the scoped body, no prefix
    assert out["answer"] == "Level 4: There are 3 people inside, in 2 rooms." and out["source"] == "ollama"
    # the whole building's number is a changed fact for Level 4: thrown away, the checked answer shown
    reply["text"] = lambda checked: "5 people inside, in 3 rooms."
    out = ask("How many people are inside?", "f1")
    assert out["answer"] == "Level 4: 3 people inside, in 2 rooms." and out["source"] == "fallback"
    # a room of another floor is not a room of this scope
    reply["text"] = lambda checked: checked + " Room 5.01 has 3 people."
    assert ask("How many people are inside?", "f1")["source"] == "fallback"
    # the model never sees, and so can never drop, the prefix or the breakdown
    calls.clear()
    reply["text"] = lambda checked: checked
    data = {**DATA, "emergency": {"on": True, "since": NOW - 120}}
    out = ask("How many people are inside?", "f1", data)
    assert all("By floor" not in c[1] and not c[1].startswith("Whole building") for c in calls)
    assert out["answer"].startswith("Whole building: ") and out["answer"].endswith("Level 5: 2 people.")


def test_no_sensor_and_example_answers_never_reach_the_model(model):
    calls, reply = model
    reply["text"] = "There are 0 people."
    ask("How many people are inside?", "f3")
    ask("How many people are inside?", "ex-2")
    assert calls == []


def test_scope_off_answers_as_before(monkeypatch):
    monkeypatch.setenv("CHAT_SCOPE", "off")
    out = ask("How many people are inside?", "f1")
    assert out == {"answer": "5 people inside, in 3 rooms.", "source": "fallback", "model": chat.FALLBACK_LABEL}


def test_the_api_takes_the_chip_floor_and_ignores_anything_else(monkeypatch):
    monkeypatch.setattr(main, "room_views", lambda now, rooms=None: ROOMS)
    monkeypatch.setattr(main, "refresh_live", lambda now, lang=None: None)
    monkeypatch.setattr(chat, "backend", lambda lang="en": None)
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    out = local.post("/api/chat", json={"question": "How many people are inside?", "floor": "f2"}).json()
    assert out["answer"] == "Level 5: 2 people inside, in 1 room." and out["scope"]["floor_id"] == "f2"
    for bad in ("../site", "<b>", "f1; drop", ""):
        out = local.post("/api/chat", json={"question": "How many people are inside?", "floor": bad}).json()
        assert out["scope"]["kind"] == "building", bad
    assert local.post("/api/chat", json={"question": "x", "floor": "f" * 40}).status_code == 422
