"""Chat backends, all through the same OpenAI-compatible client.

- huawei mode: Huawei ModelArts Studio (MaaS) when MAAS_BASE_URL, MAAS_API_KEY, MAAS_MODEL are set.
- local mode: Ollama on this machine (default qwen2.5:3b). Never Huawei.
- Neither available: built-in plain-text answers (logic.fallback_answer).

The label returned with each answer is what the dashboard shows, so it must name the real model.
"""
import concurrent.futures
import json
import os
import re
import threading
import time
import urllib.request

from server import config, logic, scope
from server.strings import t

FALLBACK_LABEL = t("model.builtin")
TIMEOUT_S = float(os.getenv("CHAT_TIMEOUT_S", "5"))  # a slow model falls back to the checked answer after this
_probe = {"ts": 0.0, "ok": False}
_probe_lock = threading.Lock()
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="nadi-chat")


def system_prompt():
    return (
        "You are NADI, a building occupancy assistant for fire wardens, fire and rescue services and facilities staff. "
        "The user message is JSON with the user's question and a checked_answer worked out by the server from live "
        "sensor data. Reply with the checked_answer in natural words, in one or two short, formal sentences. "
        "Do not add, remove or change any room name, number or yes/no, and add nothing else: no advice, no guesses. "
        "Plain text only: no emoji, no symbols, no lists, no bold. "
        "Use room names exactly as written. "
        "Reply in the same language as the question (Bahasa Melayu or English). "
        "In English, use British spelling and say \"air conditioning\" (the system) or \"air conditioner\" (the unit), "
        "never \"aircon\"; no slang or shorthand. "
        "In Bahasa Melayu, use standard Malay (bahasa baku) with no English words mixed in: \"penghawa dingin\", "
        "\"bilik kosong\", \"orang masih di dalam\", \"mod kecemasan\". Never put \"Bilik\" in front of a room name: "
        "write \"Lab 2 kosong.\", not \"Bilik Lab 2 kosong.\""
    )


def ollama_base():
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")


def backend(lang="en"):
    """The LLM to try for the current mode, or None to go straight to the built-in answers."""
    if config.is_huawei():
        if all(os.getenv(k) for k in ("MAAS_BASE_URL", "MAAS_API_KEY", "MAAS_MODEL")):
            model = os.environ["MAAS_MODEL"]
            return {"kind": "maas", "base_url": os.environ["MAAS_BASE_URL"], "api_key": os.environ["MAAS_API_KEY"],
                    "model": model, "label": t("model.maas", lang, model=model), "timeout": TIMEOUT_S}
        return None
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    if not model:
        return None
    return {"kind": "ollama", "base_url": ollama_base(), "api_key": "ollama",
            "model": model, "label": t("model.ollama", lang, model=model), "timeout": TIMEOUT_S}


def _probe_now():
    try:
        with urllib.request.urlopen(ollama_base().removesuffix("/v1") + "/api/tags", timeout=1) as resp:
            ok = resp.status == 200
    except Exception:
        ok = False
    _probe.update(ts=time.time(), ok=ok)
    return ok


def _probe_in_background():
    try:
        _probe_now()
    finally:
        _probe_lock.release()


def ollama_up(max_age_s=30):
    """Cheap reachability check for the footer, cached so /api/info stays fast. When the cached answer is old, one
    background thread checks again and callers get the cached answer meanwhile: a stopped Ollama makes the check
    take up to 1 s, and many dashboards must not all wait for it at once. max_age_s=0 checks now."""
    if max_age_s == 0 or not _probe["ts"]:
        return _probe_now()
    if time.time() - _probe["ts"] >= max_age_s and _probe_lock.acquire(blocking=False):
        threading.Thread(target=_probe_in_background, daemon=True, name="nadi-ollama-probe").start()
    return _probe["ok"]


def checked_answer(question, data):
    """The rule-based answer for the live data. The model may only rephrase this, never answer on its own."""
    return checked_rule(question, data)[1]


def checked_rule(question, data):
    return logic.rule_answer(question, data.get("rooms", []), data.get("emergency"), data.get("now"))


def llm_answer(be, question, checked):
    from openai import OpenAI

    client = OpenAI(base_url=be["base_url"], api_key=be["api_key"], timeout=be["timeout"], max_retries=0)
    resp = client.chat.completions.create(
        model=be["model"],
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": json.dumps({"question": question, "checked_answer": checked}, ensure_ascii=False)},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# Emoji and pictographs a model may add to a reply. The console shows words and its own icons only, so they are
# taken out of every model reply before it is checked and shown (an ordinary dash, degree sign or arrow stays).
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\u20E3]")


def plain(text):
    """The reply without emoji: the gaps they leave are closed, and so is a space left in front of punctuation."""
    text = EMOJI.sub(" ", text or "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


COUNT_RULES = {"total", "emergency", "first"}  # answers that get the per-floor breakdown in an emergency or drill


def answer(question, data, lang="en", floor=None):
    """The answer for one scope (server/scope.py): {"answer", "source", "model", "scope"}. floor: the floor the viewer
    chose in the chat panel, or None for the whole building. The scope's prefix and, in an emergency or drill, the
    per-floor breakdown are added after any model rewording was checked, so a model never touches them."""
    if not scope.enabled():
        out = _answer(question, data, lang)
        out.pop("rule", None)
        return out
    qlang = "ms" if logic.is_bm(question) else "en"
    sc = scope.resolve(question, floor, data, qlang)
    view = {"kind": sc["kind"], "floor_id": sc["floor_id"], "label": sc["label"], "locked": sc["locked"], "reason": sc["reason"]}
    if sc["fixed"]:
        out = {"answer": sc["fixed"], "source": "fallback", "model": t("model.builtin", lang)}
    else:
        out = _answer(question, {**data, "rooms": sc["rooms"]}, lang)
        if sc["locked"] and out.get("rule") in COUNT_RULES:
            extra = scope.breakdown(data.get("rooms", []), qlang)
            if extra:
                out["answer"] = f"{out['answer']} {extra}"
    out.pop("rule", None)
    return {**out, "answer": t("scope.prefix", qlang, scope=sc["label"], answer=out["answer"]), "scope": view}


def _answer(question, data, lang="en"):
    """data: {"now", "emergency", "rooms"}. Returns {"answer", "source", "model", "rule"}.
    Questions no rule matches, and "which room first" answers, are shown as built without touching the model.
    Otherwise the model
    rephrases the checked answer, and any reply that adds, drops or changes a room or number is thrown away."""
    rule, checked = checked_rule(question, data)
    builtin = {"answer": checked, "source": "fallback", "model": t("model.builtin", lang), "rule": rule}
    be = backend(lang)
    if be is None or rule in logic.MODEL_FREE_RULES:
        return builtin
    if be["kind"] == "ollama" and not ollama_up():  # known down: don't wait on a refused connection every question
        return builtin
    try:
        # hard deadline on top of the client timeout, which only limits each network read
        text = plain(_pool.submit(llm_answer, be, question, checked).result(timeout=be["timeout"] + 0.5))
    except Exception as e:
        print(f"{be['kind']} chat failed, using built-in answers: {e}", flush=True)
        if be["kind"] == "ollama":
            _probe.update(ts=time.time(), ok=False)  # the next questions skip it until the probe sees it again
        return builtin
    if not text or not logic.keeps_facts(checked, text, data.get("rooms", []), "ms" if logic.is_bm(question) else "en"):
        print(f"{be['kind']} reply changed the facts, using built-in answer: {text!r}", flush=True)
        return builtin
    return {"answer": text, "source": be["kind"], "model": be["label"], "rule": rule}


def source_now():
    """Who would word an answer right now: "rules" (no model: the checked answer as built), "ollama" or "maas"."""
    be = backend()
    if be is None or (be["kind"] == "ollama" and not ollama_up()):
        return "rules"
    return be["kind"]


def label_now(lang="en"):
    """What would answer right now, for the dashboard footer before anyone asks."""
    be = backend(lang)
    if be is None or (be["kind"] == "ollama" and not ollama_up()):
        return t("model.builtin", lang)
    return be["label"]
