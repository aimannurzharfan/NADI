"""Alerts are stored once and shown in the dashboard's language; SMN and the console get both languages."""
import json

import pytest

from server import alerts
from server.strings import t


class FakeRedis:
    def __init__(self):
        self.lists, self.hashes = {}, {}

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def hkeys(self, key):
        return list(self.hashes.get(key, {}))

    def hdel(self, key, *fields):
        for f in fields:
            self.hashes.get(key, {}).pop(f, None)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    def lrange(self, key, start, end):
        return self.lists.get(key, [])[start:end + 1]


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(alerts.store, "r", fake)
    monkeypatch.setenv("NADI_MODE", "local")  # console only, never SMN
    return fake


def test_waste_alert_in_both_languages(redis, capsys):
    via = alerts.send("waste", "alert.waste_subject", "alert.waste_body", name="Hall A", minutes=1, temp="23.6", rm="0.06")
    assert via == "console"
    en, ms = alerts.recent("en")[0], alerts.recent("ms")[0]
    assert en["subject"] == "NADI: Air conditioning on in an empty room (Hall A)"
    assert en["message"] == ("Hall A has been empty with the air conditioning on for 1 minute (23.6 °C). "
                             "About RM 0.06 wasted so far.")
    assert ms["subject"] == "NADI: Bilik kosong, penghawa dingin masih hidup (Hall A)"
    assert ms["message"].startswith("Hall A kosong dengan penghawa dingin masih hidup selama 1 minit")
    assert en["kind"] == ms["kind"] == "waste"
    printed = capsys.readouterr().out
    assert "[ALERT] NADI: Air conditioning on" in printed and "[AMARAN] NADI: Bilik kosong" in printed


def test_one_person_is_not_one_people(redis):
    """The word after the number follows the number, in every alert that counts people, in both languages."""
    alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body", total=1, rooms="Lab 2: 1")
    assert alerts.recent("en")[0]["message"] == "1 person inside when the alarm started. Lab 2: 1"
    assert alerts.recent("ms")[0]["message"] == "1 orang di dalam semasa penggera berbunyi. Lab 2: 1"
    alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body", total=2, rooms="Lab 2: 2")
    assert alerts.recent("en")[0]["message"].startswith("2 people inside")
    alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body_unknown", total=1, rooms="Lab 2: 1", n=1, unknown="Hall A")
    assert alerts.recent("en")[0]["message"].startswith("At least 1 person inside")
    alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body", total=0, rooms="")
    assert alerts.recent("en")[0]["message"].startswith("0 people inside")
    alerts.send("info", "alert.suspicious_subject", "alert.suspicious_body", name="Hall A", before=40, after=1)
    assert "from 40 to 1 person in one report" in alerts.recent("en")[0]["message"]
    assert "kepada 1 orang" in alerts.recent("ms")[0]["message"]


def test_emergency_alert_uses_strings_and_plural(redis):
    alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body_plus", total=4, rooms="Room 3: 3+, Lab 2: 1")
    assert alerts.recent("en")[0]["subject"] == t("alert.emergency_subject", "en")
    assert alerts.recent("ms")[0]["subject"] == "NADI: Penggera kecemasan berbunyi"
    assert alerts.recent("ms")[0]["message"] == "4 orang atau lebih di dalam semasa penggera berbunyi. Room 3: 3+, Lab 2: 1"
    alerts.send("waste", "alert.waste_subject", "alert.waste_body", name="Lab 2", minutes=12, temp="24.0", rm="0.60")
    assert "for 12 minutes" in alerts.recent("en")[0]["message"]  # newest first


def test_alerts_saved_before_keys_still_show(redis):
    redis.lpush("alerts", json.dumps({"ts": 1, "subject": "NADI: old", "message": "old text", "via": "console"}))
    assert alerts.recent("ms")[0]["subject"] == "NADI: old" and alerts.recent("ms")[0]["kind"] == "info"


def test_smn_gets_both_languages(redis, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "smn_enabled", lambda: True)
    monkeypatch.setattr(alerts, "_smn_publish", lambda subject, message: sent.append((subject, message)))
    assert alerts.send("emergency", "alert.emergency_subject", "alert.emergency_body", total=2, rooms="Lab 2: 2") == "smn"
    subject, message = sent[0]
    assert subject == "NADI: Emergency mode started / NADI: Penggera kecemasan berbunyi"
    assert "when the alarm started" in message and "semasa penggera berbunyi" in message
