"""Occupancy model trained with MindSpore (ml/train.py) and exported as JSON weights.

The server runs the small MLP forward pass itself, so it doesn't need MindSpore installed.
No model file (or a broken one) = threshold rule from logic.py. The file is re-read when it changes,
so a new training run takes effect without restarting the server.
"""
import json
import os
from pathlib import Path

from server import logic

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ml" / "model" / "nadi_model.json"
_cache = {"path": None, "mtime": None, "model": None}


def model_path():
    p = Path(os.getenv("MODEL_PATH") or DEFAULT_PATH)
    return p if p.is_absolute() else DEFAULT_PATH.parents[2] / p  # relative = from the repo root


def load(path=None):
    path = Path(path) if path else model_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["model"]
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
        n = len(m["features"])
        assert len(m["mean"]) == n and len(m["std"]) == n and m["layers"] and m["classes"]
        assert len(m["layers"][0]["W"][0]) == n and len(m["layers"][-1]["b"]) == len(m["classes"])
    except Exception as e:
        print(f"model file {path} unusable, using threshold rule: {e}", flush=True)
        m = None
    _cache.update(path=path, mtime=mtime, model=m)
    return m


def forward(m, p):
    x = [(float(p.get(f) or 0) - mu) / (sd or 1.0) for f, mu, sd in zip(m["features"], m["mean"], m["std"])]
    last = len(m["layers"]) - 1
    for i, layer in enumerate(m["layers"]):
        x = [sum(w * v for w, v in zip(row, x)) + b for row, b in zip(layer["W"], layer["b"])]
        if i < last:
            x = [max(0.0, v) for v in x]  # ReLU
    return m["classes"][max(range(len(x)), key=x.__getitem__)]


def headcount(p, path=None):
    """(headcount, source): source is "mindspore" when the model answered, "threshold" otherwise."""
    m = load(path)
    if m is not None:
        try:
            return int(forward(m, p)), "mindspore"
        except Exception as e:
            print(f"model failed, using threshold rule: {e}", flush=True)
    return logic.headcount(p), "threshold"


def info(path=None):
    m = load(path)
    if m is None:
        return None
    return {k: m.get(k) for k in ("framework", "platform", "trained_on", "accuracy", "trained_at", "n_train")}
