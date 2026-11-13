"""One source of wording: dashboard/strings.json. Every key the code uses exists, both languages are filled in,
the house style holds, and docs/GLOSSARY.md matches the JSON."""
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from server.strings import STRINGS, t

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def used_keys():
    """Every quoted "section.name" string in the code, so keys picked in a ternary are caught too."""
    sections = {k.split(".")[0] for k in STRINGS}
    key_like = re.compile(r"""["']((?:%s)\.[a-z0-9_]+)["']""" % "|".join(sections))
    keys = set()
    web = [f for ext in ("*.ts", "*.tsx") for f in (ROOT / "web" / "src").rglob(ext) if "components/ui" not in f.as_posix()]
    for f in [*(ROOT / "server").glob("*.py"), *(ROOT / "dashboard").glob("*.js"), *web]:
        keys |= {k for k in key_like.findall(f.read_text(encoding="utf-8")) if k.split(".")[1] not in ("json", "js", "html", "css")}  # not file names
    keys |= {"status." + s for s in ("ok", "empty", "waste", "off")}  # T("status." + st)
    # keys the web console builds from a value: T(`alerts.sev_${severity}`) and the like
    keys |= {f"alerts.sev_{s}" for s in ("critical", "warning", "info")} | {f"alerts.type_{k}" for k in ("emergency", "waste", "info")}
    keys |= {f"sensors.type_{k}" for k in ("receiver", "sender", "climate", "simulator", "counter")}
    for page in (ROOT / "dashboard").glob("*.html"):
        keys |= set(re.findall(r'data-(?:t|t-aria|t-placeholder|q)="([^"]+)"', page.read_text(encoding="utf-8")))
    plan = (ROOT / "dashboard" / "plan.json").read_text(encoding="utf-8")
    keys |= set(re.findall(r'"label": "([^"]+)"', plan))
    return keys


def test_every_used_key_exists():
    missing = sorted(used_keys() - set(STRINGS))
    assert not missing, f"keys used in code but missing from strings.json: {missing}"


def test_both_languages_filled_and_placeholders_match():
    for key, v in STRINGS.items():
        assert v.get("en", "").strip() and v.get("ms", "").strip(), key
        # Malay may drop a placeholder ("orang" has no plural) but must not invent one
        assert set(PLACEHOLDER.findall(v["ms"])) <= set(PLACEHOLDER.findall(v["en"])), key


def test_house_style():
    banned_en = re.compile(r"aircon|air-con|\bppl\b|\bcolor|\bcenter\b|\bmeters?\b|\w+iz(e|ed|ing|ation)\b|behavior", re.I)
    for key, v in STRINGS.items():
        assert not banned_en.search(v["en"]), (key, v["en"])
        assert "aircon" not in v["ms"].lower() and "air con" not in v["ms"].lower(), (key, v["ms"])
        assert "—" not in v["en"] + v["ms"], key  # no em dashes


def test_t_fills_placeholders_and_picks_language():
    assert t("answer.empty_list", "ms", rooms="Hall A") == "Hall A kosong."
    assert t("answer.empty_list", rooms="Hall A") == "Empty rooms: Hall A."
    assert t("legend.waste", "ms") == "Kosong, A/C hidup"  # the short form for tiles and legends; alerts keep the full phrase
    assert t("alert.waste_subject", "ms", name="Hall A") == "NADI: Bilik kosong, penghawa dingin masih hidup (Hall A)"


def test_glossary_is_up_to_date():
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "glossary.py"), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr or res.stdout


# --- one language at a time ---

# Words that are English only. Words Malay shares with English (data, status, label, log, token, audit, sensor,
# simulator, demo, port, warden) are fine in Malay. Code identifiers (ADMIN_TOKEN, service_id, file names) are not
# wording and are left out before the check.
ENGLISH_ONLY = {"the", "and", "of", "is", "are", "to", "for", "with", "from", "this", "that", "room", "rooms", "people",
                "person", "emergency", "drill", "report", "alert", "alerts", "sensors", "devices", "online", "offline",
                "broker", "snapshot", "export", "clear", "help", "search", "waste", "empty", "inside", "floor",
                "building", "minutes", "seconds", "ago", "now", "start", "end", "save", "delete", "open", "close",
                "sign", "in", "out", "admin", "viewer", "page", "next", "previous", "none", "not", "yes", "no",
                "air", "conditioning", "conditioner", "aircon", "count", "counts", "unknown", "live", "last", "known"}
MALAY_ONLY = {"bilik", "orang", "kosong", "penghawa", "dingin", "tiada", "untuk", "kecemasan", "masih", "latihan",
              "sekurang", "kurangnya", "tidak", "diketahui", "penggera", "pelan", "lantai", "dalam", "talian", "bomba",
              "amaran", "laporan", "bilangan", "pentadbir", "pemerhati", "petikan", "eksport", "padam", "tamatkan",
              "mulakan", "semua", "sahaja", "dan", "atau", "dengan", "pada", "oleh", "kWj"}
IDENTIFIER = re.compile(r"\{\w+\}|\b\w*_\w*\b|\b[A-Z0-9]{2,}\b|[\w./-]+\.(?:md|json|py|csv)\b|\.env\b|=\w+")
# names kept in their own language on purpose: the language switch says "Bahasa Melayu" / "English"
OWN_NAME = {"top.other_lang", "chat.languages"}


def words(text):
    return {w.lower() for w in re.findall(r"[A-Za-z]+", IDENTIFIER.sub(" ", text))}


def test_no_english_left_in_malay():
    mixed = {k: sorted(words(v["ms"]) & ENGLISH_ONLY) for k, v in STRINGS.items() if k not in OWN_NAME}
    assert not {k: w for k, w in mixed.items() if w}


def test_no_malay_left_in_english():
    lower = {w.lower() for w in MALAY_ONLY}
    mixed = {k: sorted(words(v["en"]) & lower) for k, v in STRINGS.items() if k not in OWN_NAME}
    assert not {k: w for k, w in mixed.items() if w}


def _pictographs(text):
    """Emoji and other picture symbols in a text. The degree sign is the one symbol the interface uses."""
    return sorted({ch for ch in text if ch != "\u00B0" and (
        unicodedata.category(ch) == "So" or ord(ch) >= 0x1F000 or 0x2600 <= ord(ch) <= 0x27BF
        or 0x2B00 <= ord(ch) <= 0x2BFF or 0x2300 <= ord(ch) <= 0x23FF or ch in "\uFE0F\u200D\u20E3")})


def test_no_emoji_in_any_string_or_component():
    """The interface uses words and its own icon set (lucide), never emoji: not in a string (English or Malay), a
    component, a style sheet, the page shell, or the server code that writes alerts and chat answers."""
    found = []
    for key, entry in STRINGS.items():
        for lang in ("en", "ms"):
            bad = _pictographs(entry.get(lang, ""))
            if bad:
                found.append(f"strings.json {key} ({lang}): {[f'U+{ord(c):04X}' for c in bad]}")
    files = [ROOT / "web" / "index.html", ROOT / "dashboard" / "plan.json"]
    files += [f for f in (ROOT / "web" / "src").rglob("*") if f.suffix in (".tsx", ".ts", ".css")]
    files += [f for f in (ROOT / "server").glob("*.py")]
    assert len(files) > 60
    for f in files:
        bad = _pictographs(f.read_text(encoding="utf-8"))
        if bad:
            found.append(f"{f.relative_to(ROOT).as_posix()}: {[f'U+{ord(c):04X}' for c in bad]}")
    assert not found, found


def test_the_emoji_check_sees_emoji():
    assert _pictographs("ok \U0001F525 done") and _pictographs("\u2705") and _pictographs("\u26A0\uFE0F")
    assert not _pictographs("24.6 \u00B0C, 3+ people \u2013 Lab 2, RM 1.20, 50%")


def test_no_bomba_in_the_interface():
    """The export is for any emergency service, not one agency: no "Bomba" in what users see."""
    assert not [k for k, v in STRINGS.items() if "bomba" in (v["en"] + v["ms"]).lower()]
    web = [f for ext in ("*.ts", "*.tsx") for f in (ROOT / "web" / "src").rglob(ext)]
    assert not [f.name for f in web if "bomba" in f.read_text(encoding="utf-8").lower()]
    assert "bomba" not in (ROOT / "server" / "chat.py").read_text(encoding="utf-8").lower()
    built = list((ROOT / "web" / "dist" / "assets").glob("*.js"))
    assert built and not [f.name for f in built if "Bomba" in f.read_text(encoding="utf-8")]


PAGE_DESCRIPTIONS = ("alerts.description", "cal.description", "design.description", "energy.description", "floor.description",
                     "rooms.description", "sensors.description", "sum.description", "ed.version", "ed.version_builtin")
DESCRIPTION_MAX = 75  # one line under the page title at 1366 px with the sidebar open, in either language


def test_page_descriptions_fit_on_one_line():
    """The line under each page title: short enough for one line, never cut with an ellipsis."""
    too_long = {f"{key} ({lang})": len(STRINGS[key][lang]) for key in PAGE_DESCRIPTIONS for lang in ("en", "ms")
                if len(STRINGS[key][lang]) > DESCRIPTION_MAX}
    assert not too_long, too_long
    assert not [k for k in PAGE_DESCRIPTIONS if "…" in STRINGS[k]["en"] + STRINGS[k]["ms"] or "..." in STRINGS[k]["en"] + STRINGS[k]["ms"]]
