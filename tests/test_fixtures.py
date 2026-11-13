"""The made-up answers behind the overview screenshots (scripts/redesign_screenshots.py) must agree with each other:
a screenshot where the card says 14 minutes and the feed says 10, or where a sensor is offline at 100% uptime, shows
a product that contradicts itself. Every state is checked in both languages. No browser, server or database needed."""
import re
import time

import pytest

from scripts import redesign_screenshots as shots

STATES = ("calm", "occupied", "waste", "offline", "emergency", "video")
# A fixed Wednesday afternoon, 14:00 Malaysia time. The made-up day starts at midnight, so with the real clock these
# tests failed in the first two hours of every day: the reports "labelled 107 minutes ago" did not exist yet.
NOW = 1794376800


@pytest.fixture(autouse=True)
def afternoon(monkeypatch):
    """The sample data reads the clock too (when the page opened, when the sensor stopped): the same fixed time."""
    monkeypatch.setattr(shots.time, "time", lambda: float(NOW))


def answers(state, lang):
    f = shots.Fixture(state, lang)
    now = NOW + 3  # the page asks a few seconds after it opens
    return f, now, f.rooms(now), f.signal(now), f.history(now, 420), f.uptime(now)


@pytest.mark.parametrize("lang", ["en", "ms"])
@pytest.mark.parametrize("state", STATES)
def test_count_signal_and_history_tell_the_same_story(state, lang):
    f, now, rooms, signal, history, uptime = answers(state, lang)
    room, points = rooms["rooms"][0], signal["points"]
    assert points[-1]["ts"] == room["count_ts"] == signal["last_report_ts"]
    assert points[-1]["headcount"] == room["headcount"]  # the tile's count is what the last report said
    for p in points:  # the threshold rule: above the line is occupied, below it is empty
        assert (p["motion_std"] > shots.THRESHOLD) == (p["headcount"] == 1)
    assert room["live"] == (now - room["count_ts"] <= rooms["stale_s"])
    buckets = history["rooms"]["room1"]
    assert {n for _, n in buckets} <= {0, 1}  # one threshold tells empty from occupied, never "2"
    assert buckets[-1][0] <= room["count_ts"]  # no history after the last report
    if room["live"]:
        assert buckets[-1][1] >= room["headcount"]
    assert uptime["pct"] is not None and uptime["pct"] < 100  # the outage in the feed is in the figure
    feed = [a["message"] for a in rooms["alerts"]]
    assert any(str(3 * shots.INTERVAL) in m for m in feed)  # "has not reported for 30 seconds"


@pytest.mark.parametrize("lang", ["en", "ms"])
def test_waste_card_feed_and_total_agree(lang):
    f, now, rooms, signal, history, uptime = answers("waste", lang)
    room, newest = rooms["rooms"][0], rooms["alerts"][0]
    waste = room["waste"]
    assert newest["kind"] == "waste" and room["headcount"] == 0 and all(p["headcount"] == 0 for p in signal["points"])
    minutes = int(re.search(r"(\d+) (?:minutes|minit)", newest["message"]).group(1))
    cost = float(re.search(r"RM\s?(\d+\.\d\d)", newest["message"]).group(1))
    assert minutes == waste["minutes"] == shots.WASTE_MIN  # the card and the feed name the same minutes
    assert cost == pytest.approx(waste["rm"], abs=0.005)  # and the same ringgit
    assert str(room["temp_c"]) in newest["message"]
    earlier = shots.rm(shots.EPISODE[0] - shots.EPISODE[1])
    assert rooms["waste_today_rm"] == pytest.approx(earlier + waste["rm"], abs=0.005)
    assert answers("occupied", lang)[2]["waste_today_rm"] == pytest.approx(earlier)


def test_offline_sensor_shows_everywhere_and_lowers_the_uptime():
    f, now, rooms, signal, history, uptime = answers("offline", "en")
    room, newest = rooms["rooms"][0], rooms["alerts"][0]
    assert room["live"] is False and room["headcount"] == 1  # the last known count, someone was inside
    assert newest["kind"] == "sensor" and newest["ts"] == room["count_ts"] + rooms["stale_s"]
    assert signal["points"][-1]["ts"] == room["count_ts"]  # the chart stops where the sensor did
    online = shots.Fixture("occupied").uptime(now)
    assert uptime["pct"] < online["pct"]
    assert f.uptime(now + 600)["pct"] < uptime["pct"]  # and keeps dropping while it stays offline


def test_calibration_fixture_has_labelled_empty_and_labelled_occupied_reports():
    f = shots.Fixture("calm")
    now = NOW + 3
    points = f.detector(now)["rooms"]["room1"]
    empty = [p for p in points if p["headcount_label"] == 0]
    occupied = [p for p in points if p["headcount_label"] > 0]
    assert len(empty) >= 10 and len(occupied) >= 10  # both columns of the chart have dots
    assert all(p["motion_std"] <= shots.THRESHOLD for p in empty) and all(p["motion_std"] > shots.THRESHOLD for p in occupied)
    assert {r["headcount"] for r in f.labels(now)["recent"]} == {0, 1}  # and the recent labels say the same


def test_the_overview_answers_agree_with_the_room_answers():
    """The overview reads every room's signal from one answer and the waste as money and energy: both must tell the
    same story as the per-room signal and the tariff."""
    fx = shots.Fixture("waste", "en")
    now = int(time.time())
    every = fx.answer("http://x/api/signals?minutes=5")
    one = fx.answer("http://x/api/rooms/room1/signal?minutes=5")
    assert every["truncated"] is False and list(every["rooms"]) == ["room1"]
    batch = every["rooms"]["room1"]
    assert batch["room_id"] == "room1" and batch["points"] and abs(len(batch["points"]) - len(one["points"])) <= 1  # a second may pass between the two
    assert every["threshold"] == one["threshold"]
    rooms = fx.rooms(now)
    assert rooms["waste_today_kwh"] == round(rooms["waste_today_rm"] / shots.TARIFF, 1) > 0
    assert fx.answer("http://x/api/incidents") == {"incidents": [], "active": None}
    s = fx.answer("http://x/api/energy/settings")  # the Energy page's settings card: the defaults, never changed
    assert s["source"] == "defaults" and s["settings"]["tariff_rm_per_kwh"] == shots.TARIFF and s["history"] == []
