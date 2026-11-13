"""Synthetic training data from the simulator, so the MindSpore pipeline runs end to end before real labels exist.

Writes simulated CSI feature rows into MySQL `occupancy` (room ids start with "synth-", timestamps in the past)
and the true headcount as label segments to ml/data/labels_synth.csv, in the same format teammates use
for ml/data/labels.csv: room_id,start_ts,end_ts,headcount.

    python ml/synth_labels.py            # 3 rooms x 1500 reports, replaces earlier synth rows
"""
import argparse
import csv
import random
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from server import logic, store  # noqa: E402
from sim.fake_sensor import Room  # noqa: E402

STEP_S = 20  # same spacing as REPORT_INTERVAL_S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rooms", type=int, default=3)
    ap.add_argument("--steps", type=int, default=1500, help="reports per room")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--labels", default=str(ROOT / "ml" / "data" / "labels_synth.csv"))
    args = ap.parse_args()
    random.seed(args.seed)

    start = int(time.time()) - 30 * 86400 - args.steps * STEP_S  # a month back, away from live data
    rows, segments = [], []
    for i in range(1, args.rooms + 1):
        room = Room(f"synth-room{i}")
        seg_start, seg_people = start, room.people
        for k in range(args.steps):
            ts = start + k * STEP_S
            room.step()
            if random.random() < 0.05:  # jump more often than the live sim so every class shows up
                room.people = random.randint(0, 5)
            if room.people != seg_people:
                segments.append((room.room_id, seg_start, ts - 1, seg_people))
                seg_start, seg_people = ts, room.people
            p = room.csi(ts)
            rows.append((room.room_id, ts, logic.headcount(p), p["motion_mean"], p["motion_std"],
                         p["amp_var"], p["rssi_mean"], p["n_packets"]))
        segments.append((room.room_id, seg_start, start + args.steps * STEP_S, seg_people))

    store.init()
    with store.mysql() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM occupancy WHERE room_id LIKE 'synth-%%'")
        cur.executemany(
            "INSERT INTO occupancy (room_id, ts, headcount, motion_mean, motion_std, amp_var, rssi_mean, n_packets)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", rows)

    Path(args.labels).parent.mkdir(parents=True, exist_ok=True)
    with open(args.labels, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["room_id", "start_ts", "end_ts", "headcount"])
        w.writerows(segments)
    print(f"{len(rows)} feature rows -> MySQL occupancy, {len(segments)} label segments -> {args.labels}")


if __name__ == "__main__":
    main()
