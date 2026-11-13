"""scripts/record_waves.py: per-packet RSSI lines from the receiver become a recording file for the console. No board
needed: the serial port is a stand-in."""
import json

import pytest

from scripts import record_waves as rw


def test_only_packet_lines_are_read():
    assert rw.parse_line("P,123456,-52") == (123456, -52)
    assert rw.parse_line("P,5,-7\r") == (5, -7)
    for other in ("", "I (1234) nadi_recv: Listening for 1a:00:00:00:00:00", "P,12,-52,extra", "P,x,-5", "P,12,20",
                  "P,12,-300", "wifi password: hunter2", "XP,1,-5"):
        assert rw.parse_line(other) is None


def test_recording_counts_time_from_the_first_packet_and_measures_the_spread():
    rec = rw.build("room1", "empty", "2026-11-12", 3.5, [(5020, -52), (5000, -50), (5040, -50), (5060, -52)])
    assert rec["points"] == [[0, -50], [20, -52], [40, -50], [60, -52]]
    assert rec["packets"] == 4 and rec["duration_ms"] == 60 and rec["std_db"] == 1.0 and rec["mean_dbm"] == -51.0
    assert rec["name"] == "room1-empty" and rec["kind"] == "empty" and rec["distance_m"] == 3.5
    assert rw.rate(rec) == pytest.approx(50)
    assert set(rec) == {"room_id", "name", "kind", "date", "distance_m", "packets", "duration_ms", "std_db", "mean_dbm", "points"}


def test_bad_names_and_empty_captures_are_refused():
    with pytest.raises(ValueError):
        rw.build("../room", "empty", "2026-11-12", None, [(0, -50), (20, -50)])
    with pytest.raises(ValueError):
        rw.build("room1", "party", "2026-11-12", None, [(0, -50), (20, -50)])
    with pytest.raises(ValueError):
        rw.build("room1", "empty", "2026-11-12", None, [(0, -50)])


def test_capture_keeps_nothing_but_time_and_rssi():
    class Port:
        chunks = [b"I (10) wifi: connected to MyHomeWifi\nP,100,-5", b"0\nP,120,-51\nmac 1a:00:00:00:00:00\nP,14", b"0,-49\n"]

        def read(self, n):
            return self.chunks.pop(0) if self.chunks else b""

    ticks = iter(range(100))
    assert rw.capture(Port(), 10, clock=lambda: next(ticks)) == [(100, -50), (120, -51), (140, -49)]


def test_save_writes_the_file_and_lists_it_once(tmp_path):
    rec = rw.build("room1", "walk", "2026-11-12", 3.5, [(0, -50), (20, -60), (40, -44)])
    path = rw.save(rec, tmp_path)
    rw.save(rec, tmp_path)  # recording again replaces the file and keeps one entry
    rw.save(rw.build("room1", "empty", "2026-11-12", 3.5, [(0, -50), (20, -50)]), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["points"][1] == [20, -60]
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index == {"recordings": [{"room_id": "room1", "file": "room1-empty.json"}, {"room_id": "room1", "file": "room1-walk.json"}]}


def test_the_committed_index_lists_only_files_that_exist():
    index = json.loads((rw.OUT / "index.json").read_text(encoding="utf-8"))
    for entry in index["recordings"]:
        rec = json.loads((rw.OUT / entry["file"]).read_text(encoding="utf-8"))
        assert rec["room_id"] == entry["room_id"] and rec["kind"] in rw.KINDS
        assert set(rec) == {"room_id", "name", "kind", "date", "distance_m", "packets", "duration_ms", "std_db", "mean_dbm", "points"}
        assert all(len(p) == 2 for p in rec["points"])  # time and RSSI, nothing else
