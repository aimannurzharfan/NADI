"""Switch the server to a newly trained model, but only if it beats the threshold rule on the same test rows.

Reads ml/model/candidate/nadi_model.json (written by ml/train.py --out ml/model/candidate). If the model was trained
on real CSI data and its test accuracy is higher than the threshold rule's, it is copied to ml/model/nadi_model.json
(the old one kept as nadi_model.prev.json) and MODEL_PATH in .env is pointed at it. The server picks up the new file
on its own (server/model.py re-reads it when it changes). Otherwise nothing changes.

    python scripts/promote_model.py [--candidate ml/model/candidate]
Synthetic results are never presented as real: a model trained on synthetic or mixed data is never promoted.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.mqtt_users import read_env, set_env  # noqa: E402

LIVE = ROOT / "ml" / "model" / "nadi_model.json"
MODEL_PATH_VALUE = "ml/model/nadi_model.json"


def decide(m):
    """(promote?, reason) for a trained model's metadata."""
    if m.get("trained_on") != "real CSI":
        return False, f"trained on {m.get('trained_on')!r} data, not real CSI: not used by the server"
    acc, base = m.get("accuracy"), m.get("threshold_accuracy")
    if acc is None or base is None:
        return False, "no accuracy figures in the model file"
    if acc <= base:
        return False, f"model {acc:.3f} does not beat the threshold rule {base:.3f}: keeping the current setup"
    return True, f"model {acc:.3f} beats the threshold rule {base:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(ROOT / "ml" / "model" / "candidate"))
    args = ap.parse_args()
    path = Path(args.candidate) / "nadi_model.json"
    if not path.exists():
        sys.exit(f"{path} not found: training did not finish")
    m = json.loads(path.read_text(encoding="utf-8"))
    promote, reason = decide(m)
    print(f"trained on: {m.get('trained_on')} | {m.get('n_train')} training rows, {m.get('n_test')} test rows")
    print(f"model accuracy {m.get('accuracy')} vs threshold rule {m.get('thresholds')} {m.get('threshold_accuracy')} "
          f"on the same test rows")
    print(("SWITCHING: " if promote else "NOT SWITCHING: ") + reason)
    if not promote:
        env = read_env()
        print(f"The server keeps MODEL_PATH as it is in .env ({'set' if env.get('MODEL_PATH') else 'empty'}).")
        return 1
    if LIVE.exists():
        shutil.copy2(LIVE, LIVE.with_name("nadi_model.prev.json"))
    for f in Path(args.candidate).iterdir():
        shutil.copy2(f, LIVE.parent / f.name)
    set_env("MODEL_PATH", MODEL_PATH_VALUE)
    print(f"Copied to {LIVE.relative_to(ROOT)} (previous kept as nadi_model.prev.json); MODEL_PATH in .env now points at it.")
    print("A running server picks it up within one report; restart it only if MODEL_PATH was off before.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
