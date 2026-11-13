"""Clear test data before a demo: history (MySQL), live counts, alerts and air conditioning waste totals.

Local mode only, on the server computer (it talks to Redis/Valkey and MySQL directly, so it needs the .env
passwords: in effect admin only). Keeps the audit log, emergency state, devices, the trained model, the headcount
labels and the stored reports inside a label (so the labelled reports on the Calibration page are still there after
the reset). Run it before every demo, with the server stopped or running (counts reappear with the next report).

    python scripts/reset_demo_data.py --yes
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from server import config, guard, labels, store  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description="Clear history, live counts, alerts and waste totals before a demo.",
        epilog="Kept: the headcount labels (ml/data/labels.csv) and every stored report inside a label, so the "
               "Calibration chart survives; the audit log, the emergency state, devices and the trained model. "
               "Deleted: all other stored reports, all temperature readings, live counts, alerts and waste totals.")
    ap.add_argument("--yes", action="store_true", help="really delete (without it, nothing is changed)")
    args = ap.parse_args()
    if config.is_huawei():
        sys.exit("Refused: NADI_MODE=huawei. This script is for local demos only; it never touches cloud databases.")
    if not args.yes:
        sys.exit("This deletes history, live counts, alerts and waste totals (labels and the reports inside a label "
                 "are kept). Run again with --yes to do it.")
    out = store.clear_demo_data(keep=labels.segments())
    guard.reset()
    print(f"Cleared {out['occupancy']} occupancy rows, {out['climate']} climate rows and {out['redis_keys']} live keys "
          f"(counts, alerts, waste totals). Kept {out.get('kept', 0)} labelled reports, the labels, the audit log, "
          "the emergency state and devices.")


if __name__ == "__main__":
    main()
