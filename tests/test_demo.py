"""Demo scenario story: timings, which room is Lab 2, and readings that give the intended counts. No services needed."""
import pytest

from server import demo, model


def test_story_beats(monkeypatch):
    monkeypatch.delenv("DEMO_BIG_HALL", raising=False)
    assert demo.counts_at(0) == (1, 0, 0)
    assert demo.counts_at(22) == (3, 2, 1)  # rooms filled up
    assert demo.counts_at(35)[0] == 0  # Lab 2 empty, air conditioning still on
    assert 30 + demo.WASTE_AFTER_S < demo.ALARM_AT  # the waste flag shows before the alarm
    assert demo.counts_at(100) == (0, 3, 2)  # "at least 5 people, in 2 rooms"
    assert demo.counts_at(demo.ALL_CLEAR_AT) == (0, 0, 0)  # all clear means everyone out
    assert demo.counts_at(demo.ALARM_AT + 5) != (0, 0, 0)  # people still inside when the alarm starts
    assert demo.ALARM_AT == 120 and demo.ALL_CLEAR_AT == 165 and demo.LENGTH_S == 180
    assert demo.TEMPS[0] < 26  # Lab 2 cold enough to count as air conditioning on


def test_default_story_is_what_one_sensor_pair_can_tell(monkeypatch):
    """Every room on CSI: 0, 1, 2 or 3+, never an exact count, so totals stay small and honest."""
    monkeypatch.delenv("DEMO_BIG_HALL", raising=False)
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2,room2:Hall A,room3:Room 3")
    assert not demo.big_hall()
    for t in range(0, demo.LENGTH_S + 1, demo.STEP_S):
        assert all(0 <= n <= 3 for n in demo.counts_at(t)), t
        services = demo.report(t, 1_800_000_000)["services"]
        assert {s["service_id"] for s in services} == {"csi", "climate"}, t


def test_big_hall_only_when_switched_on(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2,room2:Hall A,room3:Room 3")
    monkeypatch.setenv("DEMO_BIG_HALL", "on")
    assert demo.big_hall() and demo.counts_at(130)[1] == demo.hall_at(130) and demo.hall_at(120) > 100  # "100+"
    steps = [demo.hall_at(t) for t in range(0, demo.LENGTH_S + 1, demo.STEP_S)]
    assert max(abs(a - b) for a, b in zip(steps, steps[1:])) <= demo.HALL_MAX_STEP  # passes the plausibility check
    hall = [s for s in demo.report(100, 1_800_000_000)["services"] if s["properties"]["room_id"] == "room2"]
    assert {s["service_id"] for s in hall} == {"count", "climate"}
    assert demo.counts_at(demo.ALL_CLEAR_AT) == (0, 0, 0)


def test_lab_2_found_by_name(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Hall A,room2:Lab 2,room3:Room 3")
    assert demo.rooms() == ("room2", "room1", "room3")
    monkeypatch.setenv("ROOM_NAMES", "")
    assert demo.rooms()[0] == "room1"


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_readings_give_the_intended_count(count, monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "none.json"))  # threshold rule
    demo._features.clear()
    assert model.headcount(demo.features_for(count))[0] == count
    demo._features.clear()


def test_report_is_one_small_message(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2,room2:Hall A,room3:Room 3")
    import json
    body = demo.report(70, 1_800_000_000)
    assert len(json.dumps(body)) < 4096 and len(body["services"]) == 6


def test_demo_only_in_local_mode(monkeypatch):
    monkeypatch.setenv("DEMO_SCENARIO", "on")
    monkeypatch.setenv("NADI_MODE", "local")
    assert demo.enabled()
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert not demo.enabled()
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("DEMO_SCENARIO", "")
    assert not demo.enabled()


def test_restart_keeps_the_waste_of_the_run_before(monkeypatch):
    """Each run cleared the waste timer without counting it, so the Energy page showed only the current run."""
    from server import energy, logic, store

    monkeypatch.setattr(logic, "WASTE_AFTER_S", demo.WASTE_AFTER_S)
    monkeypatch.setattr(energy, "delay_override_s", demo.WASTE_AFTER_S)  # what demo.start() sets while the story runs
    now = 1_800_000_000  # 4 pm Malaysia time: one clock for the test and reset_rooms(), far from midnight
    monkeypatch.setattr(demo.time, "time", lambda: now)
    lab, hall, third = demo.rooms()
    store.r.sadd("rooms", lab, third)
    store.r.hset(f"room:{lab}", mapping={"headcount": 0, "count_ts": now, "temp_c": 22.0,
                                         "empty_cold_since": now - 150, "waste_alert_ts": now - 60})
    store.r.hset(f"room:{third}", mapping={"headcount": 2, "count_ts": now, "temp_c": 27.5})
    demo.reset_rooms()
    expected = logic.ended_waste_rm(now - 150, None, now)
    assert expected > 0 and store.waste_today(now) == pytest.approx(expected, abs=0.011)
    assert store.r.hget(f"room:{lab}", "empty_cold_since") is None  # the next run starts its own timer
    demo.reset_rooms()
    assert store.waste_today(now) == pytest.approx(expected, abs=0.011)  # counted once, not again


def test_count_source_is_stored_and_shown(monkeypatch):
    """Which service gave a room's live count: "count" rooms are labelled as a simulated counter on every screen."""
    from server import incident, main, store

    monkeypatch.setattr(store, "_write", lambda *a, **k: None)  # history: not needed here
    store.save_csi("room1", 1_800_000_000, 3, {})
    store.save_count("room2", 1_800_000_000, 120, {})
    by_id = {r["room_id"]: r for r in store.rooms()}
    assert by_id["room1"]["counter"] == "csi" and by_id["room2"]["counter"] == "count"
    store.save_csi("room2", 1_800_000_020, 1, {})  # the same room back on CSI loses the label
    assert store.room("room2")["counter"] == "csi"
    store.r.hset("room:room3", mapping={"headcount": 2, "count_ts": 1_800_000_000})  # stored before the field existed
    store.r.sadd("rooms", "room3")
    assert store.room("room3")["counter"] == "csi"
    store.save_count("room2", 1_800_000_040, 120, {})
    views = {v["room_id"]: v for v in main.room_views(1_800_000_050, store.rooms())}
    assert views["room2"]["counter"] == "count" and views["room1"]["counter"] == "csi"
    snap = incident.build_snapshot({"on": True, "since": 1_800_000_000}, list(views.values()), {}, 1_800_000_050)
    page_en, page_ms = incident.snapshot_html(snap, "en"), incident.snapshot_html(snap, "ms")
    assert page_en.count("Simulated counter (phase 2)") == 1 and page_ms.count("Pembilang simulasi (fasa 2)") == 1
