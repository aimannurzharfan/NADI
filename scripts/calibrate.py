"""Suggest HEADCOUNT_THRESHOLDS for a room from its real readings and the labels.

Takes the last N minutes of csi readings for the room from MySQL and the label segments for that room (the /label page
or the team sheet): a "still room" period labelled 0 and a "walking" period labelled 1 or more. Each threshold sits in
the gap between the motion_std values of neighbouring counts. Counts with no labels get 99 (never reached), which
gives the empty-versus-occupied rule T,99,99 from firmware/README.md when only 0 and "walking" are labelled.

    python scripts/calibrate.py --room room1 [--minutes 60] [--labels ml/data/labels.csv]
Prints the exact .env line; it does not change .env. Readings from the simulator are skipped unless --include-sim.
"""
import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

NEVER = 99.0  # above any real motion_std: that count is never reached


def pct(values, p):
    s = sorted(values)
    if not s:
        return None
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def split(lower, upper, names, notes):
    """A threshold between two sets of motion_std values: the middle of the gap, or of the medians if they overlap."""
    lo, hi = pct(lower, 90), pct(upper, 10)
    if lo < hi:
        return (lo + hi) / 2
    notes.append(f"{names[0]} and {names[1]} overlap (90th percentile {lo:.4g} >= 10th percentile {hi:.4g}): "
                 "expect some mistakes between them")
    return (pct(lower, 50) + pct(upper, 50)) / 2


def suggest(groups):
    """groups: {headcount 0..3: [motion_std, ...]}. Returns (thresholds [t1, t2, t3], notes, mode).
    mode "occupied": only still (0) and walking (1 or more) are told apart, t2 = t3 = 99.
    mode "count": 0, 1, 2 (and 3+) all labelled; each threshold sits between neighbouring counts."""
    groups = {min(int(k), 3): list(v) for k, v in groups.items() if v}
    if 0 not in groups or len(groups) < 2:
        raise ValueError("need readings labelled 0 (still room) and at least one labelled 1 or more (walking)")
    notes = []
    present = sorted(groups)
    if len(present) == 2 or present != list(range(len(present))):
        walking = [v for k in present if k > 0 for v in groups[k]]
        return [split(groups[0], walking, ("still", "walking"), notes), NEVER, NEVER], notes, "occupied"
    thresholds = [split(groups[k - 1], groups[k], (f"count {k - 1}", f"count {k}"), notes) if k in groups else NEVER
                  for k in (1, 2, 3)]
    for i in (1, 2):  # each must be above the one before
        if thresholds[i] != NEVER and thresholds[i] <= thresholds[i - 1]:
            thresholds[i] = NEVER
            notes.append(f"count {i + 1} cannot be told from count {i}: left unreachable")
    return thresholds, notes, "count"


def headcount(motion, thresholds):
    return sum(motion > t for t in thresholds)


def accuracy(groups, thresholds, mode):
    """Share of readings the rule gets right: empty versus occupied in "occupied" mode, the exact count otherwise."""
    total = right = 0
    for k, values in groups.items():
        for v in values:
            pred = headcount(v, thresholds)
            total += 1
            right += (pred > 0) == (k > 0) if mode == "occupied" else pred == min(k, 3)
    return right / total if total else 0.0


def env_line(thresholds):
    return "HEADCOUNT_THRESHOLDS=" + ",".join("99" if t == NEVER else f"{t:.4g}" for t in thresholds)


def readings(room_id, since, include_sim):
    from server import store

    sims = {os.getenv("SIM_DEVICE_ID", "nadi-sim"), "sim-local"}
    store.init()  # adds the source column on a database made before it existed
    with store.mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT ts, motion_std, source FROM occupancy WHERE room_id=%s AND ts >= %s AND motion_std IS NOT NULL",
                    (room_id, since))
        rows = cur.fetchall()
    keep = [(ts, m) for ts, m, src in rows if include_sim or room_id.startswith("synth-") or (src and src not in sims)]
    return keep, len(rows) - len(keep)


def group_by_label(rows, segments, now):
    groups = {}
    for room_ts, motion in rows:
        for start, end, count in segments:
            if start <= room_ts <= (end or now):
                groups.setdefault(min(count, 3), []).append(motion)
                break
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True)
    ap.add_argument("--minutes", type=float, default=60, help="how far back to read")
    ap.add_argument("--labels", default=str(ROOT / "ml" / "data" / "labels.csv"))
    ap.add_argument("--include-sim", action="store_true", help="also use simulator readings (testing only)")
    args = ap.parse_args()

    import csv
    if not Path(args.labels).exists():
        sys.exit(f"No labels file at {args.labels}. Label a still period (0) and a walking period with the /label page first.")
    with open(args.labels, newline="", encoding="utf-8") as f:
        segments = [(int(r["start_ts"]), int(r["end_ts"]) if (r.get("end_ts") or "").strip() else None, int(r["headcount"]))
                    for r in csv.DictReader(f) if r["room_id"].strip() == args.room]
    now = int(time.time())
    rows, skipped = readings(args.room, now - int(args.minutes * 60), args.include_sim)
    if skipped:
        print(f"skipped {skipped} readings from the simulator or an unknown device")
    groups = group_by_label(rows, segments, now)
    print(f"room {args.room}: {len(rows)} readings in the last {args.minutes:g} min, {sum(map(len, groups.values()))} inside labels")
    for k in sorted(groups):
        v = groups[k]
        print(f"  labelled {'3+' if k == 3 else k}: {len(v):4d} readings, motion_std 10th/50th/90th percentile "
              f"{pct(v, 10):.4g} / {pct(v, 50):.4g} / {pct(v, 90):.4g}")
    try:
        thresholds, notes, mode = suggest(groups)
    except ValueError as e:
        sys.exit(f"Cannot suggest thresholds: {e}.")
    for n in notes:
        print("note:", n)
    what = "empty versus occupied" if mode == "occupied" else "exact count 0 / 1 / 2 / 3+"
    print(f"accuracy of the suggested rule ({what}) on these readings: {accuracy(groups, thresholds, mode):.1%}")
    print("\nPut this line in .env, then restart the server:")
    print(env_line(thresholds))


if __name__ == "__main__":
    main()
