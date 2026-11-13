"""Write docs/GLOSSARY.md from dashboard/strings.json, the one file all user-facing wording comes from.

    python scripts/glossary.py           # rewrite the glossary
    python scripts/glossary.py --check   # exit 1 if the glossary is out of date (the tests run this too)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "dashboard" / "strings.json"
OUT = ROOT / "docs" / "GLOSSARY.md"

SECTIONS = {
    "ui": "Header and page", "kpi": "Summary strip", "plan": "Floor plan", "legend": "Floor plan key",
    "status": "Room status", "unit": "Units", "rooms": "Room cards", "card": "Room cards",
    "detail": "Room details", "time": "Times", "alerts": "Alerts panel", "alert": "Alert messages (SMN and console)",
    "chat": "Ask NADI", "answer": "Chat answers (built-in)", "model": "Chat model labels",
    "built": "Built with", "footer": "Footer", "start": "Start emergency dialog", "em": "Emergency view",
    "admin": "Admin", "api": "Server error messages",
}

TERMS = [
    ("air conditioning (the system)", "penghawa dingin", "Never \"aircon\". \"A/C\" only where space is tight."),
    ("air conditioner (the unit)", "penghawa dingin", ""),
    ("emergency mode", "mod kecemasan", ""),
    ("empty room, air conditioning still on", "bilik kosong, penghawa dingin masih hidup", ""),
    ("people still inside", "orang masih di dalam", ""),
    ("occupied", "berpenghuni", ""),
    ("sensor", "sensor", ""),
    ("online / offline", "dalam talian / luar talian", ""),
    ("floor plan", "pelan lantai", ""),
    ("exit", "keluar", "As on Malaysian exit signs: KELUAR"),
    ("headcount", "bilangan orang", ""),
    ("alert", "amaran", ""),
    ("warden", "warden", ""),
]


def esc(text):
    return text.replace("|", "\\|").replace("\n", " ")


def render():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not k.startswith("_")}
    checks = [(k, v) for k, v in entries.items() if v.get("check")]
    out = [
        "# NADI glossary",
        "",
        "Every phrase NADI shows to users and judges, in English and Bahasa Melayu.",
        "Generated from `dashboard/strings.json` by `python scripts/glossary.py`. Edit the JSON, not this file.",
        "The dashboard and the server both read the JSON, so a wording change there changes it everywhere.",
        "",
        "Rules: formal English with British/Malaysian spelling (colour, metres); standard Malay (bahasa baku), no mixing.",
        f"**[CHECK]** marks Malay wording a native speaker should confirm ({len(checks)} {'entry' if len(checks) == 1 else 'entries'}).",
        "`{name}` and similar are filled in at run time.",
        "",
        "## Key terms",
        "",
        "| English | Bahasa Melayu | Note |",
        "|---|---|---|",
    ]
    out += [f"| {esc(en)} | {esc(ms)} | {esc(note)} |" for en, ms, note in TERMS]
    current = None
    for key, v in entries.items():
        section = SECTIONS.get(key.split(".")[0], key.split(".")[0])
        if section != current:
            current = section
            out += ["", f"## {section}", "", "| Key | English | Bahasa Melayu |", "|---|---|---|"]
        ms = esc(v["ms"]) + (f" **[CHECK]** {esc(v['check'])}" if v.get("check") else "")
        out.append(f"| `{key}` | {esc(v['en'])} | {ms} |")
    return "\n".join(out) + "\n"


def main():
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("docs/GLOSSARY.md is out of date: run python scripts/glossary.py")
        print("glossary up to date")
        return
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
