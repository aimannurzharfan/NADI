"""Record the signal strength of every packet between a room's two boards, for the "Recorded waves" charts in the
room panel of the console.

    python scripts/record_waves.py --room room1 --kind empty --seconds 15 --distance 3.5
    python scripts/record_waves.py --room room1 --kind walk  --seconds 15 --distance 3.5

Writes web/public/recordings/<room>-<kind>.json and lists it in web/public/recordings/index.json. Rebuild the console
(npm run build in web/) afterwards so the files ship with it.

Needs the receiver to print one line per packet on its serial port:

    P,<milliseconds since start-up>,<RSSI in dBm>

The normal receiver firmware does not print this (it sends one summary every report interval). A diagnostic build
that adds the line is flashed for the recording and the normal firmware is put back afterwards with
`python scripts/provision.py --role recv`. That build is a throw-away and is not part of this repository.

Only the packet time and RSSI are kept. Every other line the board prints is dropped unread, so no addresses, names
or settings can end up in a recording.
"""
import argparse
import datetime
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "web" / "public" / "recordings"
KINDS = ("empty", "walk", "hand", "moved")  # the console has wording for these (rec.kind.* in strings.json)
LINE = re.compile(r"^P,(\d{1,12}),(-?\d{1,3})$")
ROOM = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
MIN_RATE = 20   # packets a second: fewer means the sender is far, off, or on another channel
MAX_PACKETS = 6000


def parse_line(line):
    """(milliseconds, RSSI dBm) from one "P,<ms>,<rssi>" line, or None for anything else."""
    m = LINE.match(line.strip())
    if not m:
        return None
    ms, rssi = int(m.group(1)), int(m.group(2))
    return (ms, rssi) if -120 <= rssi <= 0 else None


def spread(values):
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def build(room_id, kind, date, distance_m, samples):
    """The recording as it is saved: times counted from the first packet, with the summary figures."""
    if not ROOM.match(room_id):
        raise ValueError(f"room id {room_id!r}: letters, digits, _ and - only")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    samples = sorted(samples)[:MAX_PACKETS]
    if len(samples) < 2:
        raise ValueError("fewer than two packets")
    t0 = samples[0][0]
    points = [[ms - t0, rssi] for ms, rssi in samples]
    rssi = [p[1] for p in points]
    return {"room_id": room_id, "name": f"{room_id}-{kind}", "kind": kind, "date": date,
            "distance_m": distance_m, "packets": len(points), "duration_ms": points[-1][0],
            "std_db": round(spread(rssi), 3), "mean_dbm": round(sum(rssi) / len(rssi), 2), "points": points}


def rate(rec):
    return (rec["packets"] - 1) / (rec["duration_ms"] / 1000) if rec["duration_ms"] > 0 else 0.0


def save(rec, out=OUT):
    """Write the recording and list it in index.json (one entry per file, sorted)."""
    out.mkdir(parents=True, exist_ok=True)
    name = f"{rec['name']}.json"
    (out / name).write_text(json.dumps(rec, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    index_path = out / "index.json"
    try:
        listed = json.loads(index_path.read_text(encoding="utf-8")).get("recordings", [])
    except (OSError, ValueError, AttributeError):
        listed = []
    listed = [r for r in listed if isinstance(r, dict) and r.get("file") != name]
    listed.append({"room_id": rec["room_id"], "file": name})
    listed.sort(key=lambda r: (r["room_id"], r["file"]))
    index_path.write_text(json.dumps({"recordings": listed}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out / name


def capture(ser, seconds, clock=time.monotonic):
    """Read "P" lines from the open serial port for `seconds`. Everything else is dropped."""
    samples, buf, end = [], b"", clock() + seconds
    while clock() < end:
        buf += ser.read(4096)
        *lines, buf = buf.split(b"\n")
        for raw in lines:
            got = parse_line(raw.decode("ascii", "ignore"))
            if got:
                samples.append(got)
    return samples


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record per-packet RSSI from the receiver for the console's recorded waves.")
    ap.add_argument("--room", required=True)
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--distance", type=float, default=None, help="distance between the two boards in metres")
    ap.add_argument("--port", default=None, help="serial port of the receiver (found automatically if left out)")
    ap.add_argument("--countdown", type=int, default=5)
    args = ap.parse_args(argv)
    if not 1 <= args.seconds <= 120:
        sys.exit("--seconds must be between 1 and 120")

    from scripts import provision
    try:
        port = args.port or provision.find_port()
    except provision.ProvisionError as e:
        sys.exit(str(e))
    ser = provision.open_serial(port)
    try:
        if not capture(ser, 3):
            sys.exit(f"No packet lines from {port} in 3 s. Is the diagnostic receiver build flashed, and the sender powered?")
        for n in range(args.countdown, 0, -1):
            print(f"recording '{args.kind}' for {args.seconds:g} s in {n}...", flush=True)
            capture(ser, 1)
        print("RECORDING", flush=True)
        samples = capture(ser, args.seconds)
    finally:
        ser.close()
    try:
        rec = build(args.room, args.kind, datetime.date.today().isoformat(), args.distance, samples)
    except ValueError as e:
        sys.exit(f"Not saved: {e}.")
    if rate(rec) < MIN_RATE:
        sys.exit(f"Not saved: only {rate(rec):.1f} packets a second (expected about 50). Check the sender.")
    path = save(rec)
    print(f"saved {path.relative_to(ROOT)}: {rec['packets']} packets, {rate(rec):.1f} per second, "
          f"mean {rec['mean_dbm']} dBm, spread (std) {rec['std_db']} dB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
