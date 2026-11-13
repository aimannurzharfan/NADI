"""User-facing wording, English and Malay, from dashboard/strings.json (the one file the dashboard also reads).

    t("answer.empty_list", "ms", rooms="Hall A")  ->  "Bilik kosong: Hall A."

Change wording in strings.json, then run python scripts/glossary.py to refresh docs/GLOSSARY.md.
"""
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "dashboard" / "strings.json"
LANGS = ("en", "ms")
STRINGS = {k: v for k, v in json.loads(PATH.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def t(key, lang="en", **values):
    """Phrase for key in lang ("en" or "ms"), with {placeholders} filled from values."""
    text = STRINGS[key]["ms" if lang == "ms" else "en"]
    return text.format(**values) if values else text
