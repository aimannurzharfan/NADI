"""Chat safety: the model never answers on its own. Questions no rule matches never reach it, and whatever it
replies, the answer shown never has a room or number that isn't in the live data."""
import re

import pytest


@pytest.fixture(autouse=True)
def core_without_scope(monkeypatch):
    """These tests check the rules and the model check themselves, on the rooms they are given. The scope that wraps
    them (prefix, floor, breakdown) is tested in tests/test_chat_scope.py."""
    monkeypatch.setenv("CHAT_SCOPE", "off")

from server import chat, logic

NOW = 1_800_000_000
ROOMS = [
    {"room_id": "room1", "name": "Lab 2", "headcount": 1, "temp_c": 24.0, "humidity": 60.0, "live": True, "waste": None},
    {"room_id": "room2", "name": "Hall A", "headcount": 0, "temp_c": 23.5, "humidity": 61.0, "live": True,
     "waste": {"since": NOW - 1200, "minutes": 20, "rm": 0.99}},
    {"room_id": "room3", "name": "Room 3", "headcount": 3, "temp_c": 29.0, "humidity": 58.0, "live": True, "waste": None},
]
DATA = {"now": NOW, "emergency": {"on": True, "since": NOW - 300}, "rooms": ROOMS}
FAKE_BE = {"kind": "ollama", "label": "fake model", "model": "fake", "base_url": "", "api_key": "", "timeout": 1}

UNMATCHED = ["Who is the building manager?", "What's the weather like?", "Should I open the windows?",
             "Siapa pengurus bangunan ini?", "Apa khabar?"]
MATCHED = ["How many people are inside?", "Berapa orang di dalam bangunan?", "Which rooms are empty?",
           "Bilik mana yang kosong?", "Is the air conditioning on in any empty room?",
           "Adakah penghawa dingin masih hidup di mana-mana bilik kosong?", "How many people in Lab 2?",
           "Is emergency mode on?", "Adakah mod kecemasan aktif?"]
FIRST = ["Which room should rescuers check first?", "Bilik mana perlu diperiksa dahulu?", "Which room has the most people?"]


@pytest.fixture
def model(monkeypatch):
    """A fake model: records every call and replies with whatever the test sets."""
    calls, reply = [], {"text": None}
    monkeypatch.setattr(chat, "backend", lambda lang="en": FAKE_BE)

    def fake(be, question, checked):
        calls.append((question, checked))
        return reply["text"](checked) if callable(reply["text"]) else reply["text"]
    monkeypatch.setattr(chat, "llm_answer", fake)
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: True)
    return calls, reply


def live_numbers(data):
    """Every number the live data can justify: counts, temperatures, waste, totals, room names, alarm minutes."""
    live = [r for r in data["rooms"] if r["live"]]
    nums = {str(r["headcount"]) for r in live} | {f"{r['temp_c']:.1f}" for r in live}
    for r in live:
        if r["waste"]:
            nums |= {str(r["waste"]["minutes"]), f"{r['waste']['rm']:.2f}"}
        nums |= set(re.findall(r"\d+", logic.label(r)))
    nums |= {str(sum(r["headcount"] for r in live)), str(sum(r["headcount"] > 0 for r in live)),
             f"{sum(r['waste']['rm'] for r in live if r['waste']):.2f}",
             str((data["now"] - data["emergency"]["since"]) // 60)}
    nums |= {str(i) for i in range(1, len(data["rooms"]) + 1)}  # priority ranks 1, 2, 3
    return nums


@pytest.mark.parametrize("question", UNMATCHED)
def test_unmatched_question_never_reaches_the_model(model, question):
    calls, reply = model
    reply["text"] = "Rescuers should check Room 3 first, it is the only occupied room."  # what qwen2.5:3b once said
    out = chat.answer(question, DATA)
    assert calls == []
    assert out["source"] == "fallback"
    assert out["answer"] == (logic.HELP_BM if logic.is_bm(question) else logic.HELP_EN)


def test_unmatched_help_is_in_the_users_language(model):
    assert chat.answer("Siapa pengurus bangunan ini?", DATA)["answer"].startswith("Saya boleh menjawab")
    assert chat.answer("Who manages this building?", DATA)["answer"].startswith("I can answer")


def test_model_only_sees_the_question_and_checked_answer(model):
    calls, reply = model
    reply["text"] = lambda checked: checked
    out = chat.answer("Which rooms are empty?", DATA)
    assert calls == [("Which rooms are empty?", "Empty rooms: Hall A.")]
    assert out == {"answer": "Empty rooms: Hall A.", "source": "ollama", "model": "fake model"}


BAD_REPLIES = [
    lambda c: c + " Room 9 also has 7 people.",           # invents a room and a number
    lambda c: re.sub(r"\d+", "8", c, count=1) if re.search(r"\d", c) else c + " 8",  # changes a number
    lambda c: c.replace("Hall A", "Lab 2") if "Hall A" in c else c + " Lab 2 too.",  # swaps a room
    lambda c: "Bilik " + c,                                # "Bilik Lab 2" style in Malay
    lambda c: "Everyone has left the building.",           # drops every fact
]


@pytest.mark.parametrize("question", MATCHED)
@pytest.mark.parametrize("bad", BAD_REPLIES)
def test_reply_never_has_a_room_or_number_not_in_live_data(model, question, bad):
    calls, reply = model
    reply["text"] = bad
    out = chat.answer(question, DATA)
    assert len(calls) == 1
    allowed_rooms = logic._rooms_named(chat.checked_answer(question, DATA), ROOMS)
    assert set(re.findall(r"\d+(?:\.\d+)?", out["answer"])) <= live_numbers(DATA), out
    assert logic._rooms_named(out["answer"], ROOMS) <= allowed_rooms, out
    assert "room 9" not in out["answer"].lower()


@pytest.mark.parametrize("question", MATCHED)
def test_faithful_rephrasing_is_kept(model, question):
    calls, reply = model
    reply["text"] = lambda checked: "Here is the answer: " + checked if not logic.is_bm(question) else "Jawapannya: " + checked
    out = chat.answer(question, DATA)
    assert out["source"] == "ollama", out


@pytest.mark.parametrize("question", MATCHED)
def test_emoji_in_a_model_reply_never_reach_the_chat_panel(model, question):
    calls, reply = model
    fire, tick, warn = "\U0001F525", "\u2705", "\u26A0\uFE0F"
    lead = "Jawapannya" if logic.is_bm(question) else "Here is the answer"
    reply["text"] = lambda checked: f"{tick} {lead}: {checked} {fire}{warn}"
    out = chat.answer(question, DATA)
    assert out["source"] == "ollama", out          # still the model's wording: only the pictographs are gone
    assert not chat.EMOJI.search(out["answer"]) and out["answer"].startswith(lead)
    assert "  " not in out["answer"] and not out["answer"].endswith(" ")


def test_plain_text_keeps_ordinary_signs():
    assert chat.plain("Lab 2 is 24.6 \u00B0C \u2013 empty \U0001F60A .") == "Lab 2 is 24.6 \u00B0C \u2013 empty."
    assert chat.plain(None) == "" and chat.plain("\U0001F916") == ""
    assert "no emoji" in chat.system_prompt()


# Replies qwen2.5:3b really gave during testing on 24 Oct 2026, with Lab 2: 0, Hall A: 1, Room 3: 0
REAL_ROOMS = [dict(r, headcount=h, waste=None) for r, h in zip(ROOMS, (0, 1, 0))]
REAL_BAD = [
    ("1 person inside, in 1 room.", "1 person is inside, in Room 1.", "en"),              # invented "Room 1"
    ("1 orang di dalam, di 1 bilik.", "1 bilik kosong, tetapi ada 1 orang di dalam.", "ms"),  # 2 rooms were empty
    ("Lab 2 dan Room 3 kosong.", "Bilik Lab 2 kosong dan Bilik 3 kosong.", "ms"),        # "Bilik" + invented "Bilik 3"
    ("1 orang di dalam, di 1 bilik.", "1 orang masih di dalam bilik Lab 2.", "ms"),       # wrong room
    ("Emergency mode is off.", "Emergency mode is not activated.", "en"),                # new negative word
    ("No rooms are empty.", "No rooms are occupied.", "en"),                             # opposite meaning
    ("No empty room has the air conditioning on.",
     "No room has its air conditioning turned on, and all rooms are occupied.", "en"),   # wider claim
]
REAL_GOOD = [
    ("Lab 2 dan Room 3 kosong.", "Lab 2 dan Room 3 kosong.", "ms"),
    ("3 people inside, in 2 rooms.", "There are 3 people inside, in 2 rooms.", "en"),
    ("Empty rooms: Lab 2 and Room 3.", "The empty rooms are Lab 2 and Room 3.", "en"),
]


@pytest.mark.parametrize("checked,reply,lang", REAL_BAD)
def test_real_bad_model_replies_are_rejected(checked, reply, lang):
    assert not logic.keeps_facts(checked, reply, REAL_ROOMS, lang)


@pytest.mark.parametrize("checked,reply,lang", REAL_GOOD)
def test_faithful_replies_pass(checked, reply, lang):
    assert logic.keeps_facts(checked, reply, REAL_ROOMS, lang)


def test_dropping_the_plus_is_rejected():
    assert not logic.keeps_facts("Periksa Lab 2 dahulu: 3+ orang, melalui Tangga B.",
                                 "Periksa Lab 2 dahulu: 3 orang, melalui Tangga B.", REAL_ROOMS, "ms")



@pytest.mark.parametrize("emergency_on", [True, False])
@pytest.mark.parametrize("question", FIRST)
def test_check_first_answers_never_reach_the_model(model, question, emergency_on):
    """An ordered rescue list with a stair per room is shown exactly as built: a rewrite could reorder it or swap
    stairs in ways the reply check can't see."""
    calls, reply = model
    reply["text"] = lambda checked: checked  # even a perfect echo is not used
    data = dict(DATA, emergency={"on": emergency_on, "since": NOW - 300})
    out = chat.answer(question, data)
    assert calls == []
    assert out["source"] == "fallback" and out["answer"] == chat.checked_answer(question, data)
    assert ("Stair" in out["answer"]) or ("Tangga" in out["answer"])


def test_swapped_or_added_stair_is_rejected():
    checked = "Hall A: 1 person, via Stair A."
    assert not logic.keeps_facts(checked, "Hall A: 1 person, via Stair B.", REAL_ROOMS)
    assert not logic.keeps_facts(checked, "Hall A: 1 person, via Stair A or Stair B.", REAL_ROOMS)
    assert not logic.keeps_facts("Hall A: 1 orang, melalui Tangga A.", "Hall A: 1 orang, melalui Tangga B.", REAL_ROOMS, "ms")
    assert logic.keeps_facts(checked, "Hall A has 1 person; use Stair A.", REAL_ROOMS)


def test_failed_model_call_marks_ollama_down(monkeypatch):
    """After one failed call the next questions get the checked answer at once, not after another time-out."""
    import time

    monkeypatch.setenv("NADI_MODE", "local")
    calls = []

    def boom(be, question, checked):
        calls.append(question)
        raise ConnectionError("refused")

    monkeypatch.setattr(chat, "llm_answer", boom)
    monkeypatch.setattr(chat, "_probe", {"ts": time.time(), "ok": True})
    first = chat.answer("How many people are inside?", DATA)
    second = chat.answer("How many people are inside?", DATA)
    assert first["source"] == second["source"] == "fallback" and first["answer"] == second["answer"]
    assert len(calls) == 1 and chat._probe["ok"] is False
