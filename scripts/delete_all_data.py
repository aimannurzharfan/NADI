"""Delete every stored record for a PDPA request: readings, labels, alerts, the audit log, incident and drill reports
and snapshots, device health. What is kept and why: PRIVACY.md. The same as "Delete all stored data" on the Alerts
page (admin), for when the server is not running.

Talks to Redis/Valkey and MySQL directly with the .env settings (in effect admin only). Works in both modes; it makes
no Huawei Cloud API calls, only database connections. Refuses while emergency mode or a drill is on.

    python scripts/delete_all_data.py                          asks you to type DELETE ALL DATA
    python scripts/delete_all_data.py --confirm "DELETE ALL DATA"
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from server import config, privacy, store  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Delete every stored reading, label, alert, audit entry and report.")
    ap.add_argument("--confirm", help=f'the phrase "{privacy.CONFIRM}" (without it you are asked to type it)')
    args = ap.parse_args(argv)
    print(f"NADI_MODE={config.mode()}. This deletes every reading, label, alert, audit entry, incident report and "
          "snapshot. It cannot be undone.")
    phrase = args.confirm if args.confirm is not None else input(f"Type {privacy.CONFIRM} to go ahead: ").strip()
    try:
        out = privacy.delete_all(phrase)
    except privacy.Refused as e:
        if str(e) == "emergency":
            sys.exit("Refused: emergency mode or a drill is on. End it first.")
        sys.exit("Refused: the confirmation did not match. Nothing was deleted.")
    store.audit({"ts": int(time.time()), "action": "delete_all", "by": "script", "ip": "this computer"})
    print(f"Deleted {out['occupancy']} occupancy rows, {out['climate']} climate rows, {out['redis_keys']} live keys "
          f"(alerts, audit, counts, devices), {out['incidents']} incident reports and {out['files']} label files.")
    print("Log files (LOG_FILE, Docker container logs) are not touched: see PRIVACY.md.")
    return out


if __name__ == "__main__":
    main()
