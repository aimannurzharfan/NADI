"""Calibration helper and model promotion, on simulated readings. No services needed."""
import random

import pytest

from scripts import calibrate, promote_model
from sim.fake_sensor import Room


def simulated(people, n=200, seed=1):
    """motion_std readings from the simulator's room model with a fixed headcount."""
    random.seed(seed + people)
    room = Room("room1")
    room.people = people
    return [room.csi(0)["motion_std"] for _ in range(n)]


def test_still_versus_walking_gives_t_99_99():
    groups = {0: simulated(0), 1: simulated(1)}
    thresholds, notes, mode = calibrate.suggest(groups)
    assert mode == "occupied" and thresholds[1:] == [calibrate.NEVER, calibrate.NEVER]
    assert max(groups[0]) * 0.6 < thresholds[0] < min(groups[1]) * 1.4
    assert calibrate.accuracy(groups, thresholds, mode) > 0.98
    assert calibrate.env_line(thresholds).startswith("HEADCOUNT_THRESHOLDS=") and calibrate.env_line(thresholds).endswith(",99,99")


def test_walking_labelled_as_two_still_means_occupied():
    thresholds, _, mode = calibrate.suggest({0: simulated(0), 2: simulated(2)})
    assert mode == "occupied" and thresholds[1] == calibrate.NEVER


def test_full_counts_give_rising_thresholds():
    groups = {k: simulated(k) for k in range(4)}
    thresholds, notes, mode = calibrate.suggest(groups)
    assert mode == "count" and thresholds == sorted(thresholds) and calibrate.NEVER not in thresholds
    assert calibrate.accuracy(groups, thresholds, mode) > 0.9


def test_overlap_is_reported():
    _, notes, _ = calibrate.suggest({0: [0.1, 0.2, 0.3, 0.4], 1: [0.15, 0.25, 0.35, 0.45]})
    assert notes and "overlap" in notes[0]


def test_needs_a_still_and_a_moving_period():
    with pytest.raises(ValueError):
        calibrate.suggest({1: simulated(1)})
    with pytest.raises(ValueError):
        calibrate.suggest({0: simulated(0)})


def test_readings_grouped_by_label_segments():
    rows = [(100, 0.01), (150, 0.02), (210, 0.9), (400, 0.5)]
    groups = calibrate.group_by_label(rows, [(90, 200, 0), (200, None, 1)], now=300)
    assert groups == {0: [0.01, 0.02], 1: [0.9]}  # 400 is after "now", outside the running label


@pytest.mark.parametrize("meta,promote", [
    ({"trained_on": "real CSI", "accuracy": 0.91, "threshold_accuracy": 0.85}, True),
    ({"trained_on": "real CSI", "accuracy": 0.85, "threshold_accuracy": 0.85}, False),  # a tie is not better
    ({"trained_on": "real CSI", "accuracy": 0.70, "threshold_accuracy": 0.85}, False),
    ({"trained_on": "synthetic", "accuracy": 1.0, "threshold_accuracy": 0.5}, False),  # never synthetic
    ({"trained_on": "mixed real + synthetic", "accuracy": 1.0, "threshold_accuracy": 0.5}, False),
    ({"trained_on": "real CSI"}, False),
])
def test_promotion_only_for_real_data_that_beats_the_rule(meta, promote):
    assert promote_model.decide(meta)[0] is promote
