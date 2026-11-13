"""Merge CSI features from MySQL with headcount labels into one training CSV.

Labels file (filled in by teammates): room_id,start_ts,end_ts,headcount
Each feature row whose ts falls inside a label segment for the same room gets that headcount (3 or more -> 3: CSI tells 0, 1, 2 or 3+; labels may go up to 100).
Only readings from real boards are used: rows from the simulator (SIM_DEVICE_ID, sim-local) or with no recorded
device (stored before the source column existed) are skipped, so simulated numbers are never trained on as real.

    python ml/prepare.py                                   # ml/data/labels.csv -> ml/data/train.csv
    python ml/prepare.py --labels ml/data/labels_synth.csv
"""
import argparse
import csv
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ["motion_mean", "motion_std", "amp_var", "rssi_mean", "n_packets"]


def sim_devices():
    return {os.getenv("SIM_DEVICE_ID", "nadi-sim"), "sim-local"}


def read_labels(path):
    """Closed segments only. An empty end_ts is a label still running on the /label page: tap Stop to close it."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    open_rows = [r for r in rows if not (r.get("end_ts") or "").strip()]
    if open_rows:
        print(f"skipped {len(open_rows)} label(s) still running (no end_ts): "
              + ", ".join(f"{r['room_id']} from {r['start_ts']}" for r in open_rows))
    return [(r["room_id"].strip(), int(r["start_ts"]), int(r["end_ts"]), int(r["headcount"]))
            for r in rows if (r.get("end_ts") or "").strip()]


def main():
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(ROOT / "ml" / "data" / "labels.csv"))
    ap.add_argument("--out", default=str(ROOT / "ml" / "data" / "train.csv"))
    args = ap.parse_args()

    labels = read_labels(args.labels)
    import sys
    sys.path.insert(0, str(ROOT))
    from server import store
    store.init()  # adds the source column on a database made before it existed
    conn = pymysql.connect(host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
                           user=os.getenv("MYSQL_USER", "nadi"), password=os.getenv("MYSQL_PASSWORD", ""),
                           database=os.getenv("MYSQL_DATABASE", "nadi"))
    out, counts, skipped = [], [0, 0, 0, 0], 0
    with conn, conn.cursor() as cur:
        for room_id, start, end, headcount in labels:
            cur.execute(f"SELECT ts, source, {', '.join(FEATURES)} FROM occupancy WHERE room_id=%s AND ts BETWEEN %s AND %s",
                        (room_id, start, end))
            for ts, source, *feats in cur.fetchall():
                if not room_id.startswith("synth-") and (source is None or source in sim_devices()):
                    skipped += 1
                    continue
                if any(v is None for v in feats):
                    continue
                label = min(headcount, 3)
                out.append([room_id, ts, *feats, label, f"{room_id}@{start}"])  # one labelling session = one segment
                counts[label] += 1

    out.sort(key=lambda r: (r[0], r[1]))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["room_id", "ts", *FEATURES, "label", "session"])
        w.writerows(out)
    print(f"{len(out)} labelled rows from {len(labels)} segments -> {args.out}")
    print("per class 0/1/2/3+:", counts)
    if skipped:
        print(f"skipped {skipped} readings from the simulator or an unknown device (not real board data)")
    if not out:
        raise SystemExit("no rows matched: check room_id and timestamps in the labels file")


if __name__ == "__main__":
    main()
