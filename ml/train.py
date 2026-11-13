"""Train the NADI occupancy classifier (0 / 1 / 2 / 3+ people) with MindSpore.

Input: the CSV from ml/prepare.py (room_id, ts, 5 CSI features, label).
Output (in --out):
  nadi_mlp.ckpt      MindSpore checkpoint
  nadi_mlp.mindir    MindSpore MINDIR export (for MindSpore Lite / ModelArts inference)
  nadi_model.json    weights + feature scaling + metrics; this is what server/model.py loads

Same script locally and on ModelArts (see ml/MODELARTS.md). obs:// paths are copied with moxing,
which ModelArts training images include.

    python ml/train.py
    python ml/train.py --data obs://nadi-ml/data/train.csv --out obs://nadi-ml/output --platform modelarts
"""
import argparse
import csv
import json
import os
import random
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ["motion_mean", "motion_std", "amp_var", "rssi_mean", "n_packets"]
CLASSES = [0, 1, 2, 3]  # 3 means 3 or more
THRESHOLDS = [0.35, 0.95, 1.55]  # server threshold rule defaults, used as the baseline


def fetch(path, tmp):
    """Local file, local folder (ModelArts maps OBS inputs to a folder) or obs:// path -> local CSV path."""
    if str(path).startswith("obs://"):
        import moxing as mox

        local = Path(tmp) / Path(path).name
        mox.file.copy(str(path), str(local))
        return local
    p = Path(path)
    return p / "train.csv" if p.is_dir() else p


def load_csv(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} has no rows: run ml/prepare.py first")
    return rows


def data_kind(rows):
    """ml/synth_labels.py rooms are named synth-*; anything else came from real boards."""
    synth = sum(r["room_id"].startswith("synth-") for r in rows)
    return "synthetic" if synth == len(rows) else "real CSI" if synth == 0 else "mixed real + synthetic"


def time_split(rows, test_frac):
    """Last test_frac of each room's timeline is the test set. A random split would leak, because
    neighbouring reports 20 s apart are almost identical."""
    by_room = {}
    for r in rows:
        by_room.setdefault(r["room_id"], []).append(r)
    train, test = [], []
    for room_rows in by_room.values():
        room_rows.sort(key=lambda r: int(r["ts"]))
        cut = int(len(room_rows) * (1 - test_frac))
        train += room_rows[:cut]
        test += room_rows[cut:]
    return train, test


def session_split(rows, test_frac):
    """Whole labelling sessions go to the test set, never single rows: for each headcount, its latest sessions
    (about test_frac of them, at least one when there are two or more). Rows from one session are near copies of
    each other, so testing on rows from a session the model trained on would overstate the accuracy."""
    sessions = {}
    for r in rows:
        sessions.setdefault((int(r["label"]), r["session"]), []).append(r)
    by_class = {}
    for (label, session), session_rows in sessions.items():
        by_class.setdefault(label, []).append((min(int(r["ts"]) for r in session_rows), session, session_rows))
    train, test, notes = [], [], []
    n_train = n_test = 0
    for label in sorted(by_class):
        ordered = sorted(by_class[label])
        k = max(1, round(len(ordered) * test_frac)) if len(ordered) >= 2 else 0
        if k == 0:
            notes.append(f"headcount {'3+' if label == 3 else label} has only 1 session: kept for training, not tested")
        for _, _, session_rows in ordered[:len(ordered) - k]:
            train += session_rows
        for _, _, session_rows in ordered[len(ordered) - k:]:
            test += session_rows
        n_train += len(ordered) - k
        n_test += k
    return train, test, f"by labelling session: {n_train} sessions to train, {n_test} held out to test", notes


def arrays(rows):
    x = np.array([[float(r[f]) for f in FEATURES] for r in rows], dtype=np.float32)
    y = np.array([int(r["label"]) for r in rows], dtype=np.int32)
    return x, y


def confusion(y_true, y_pred):
    m = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    for t, p in zip(y_true, y_pred):
        m[t, p] += 1
    return m


def print_confusion(m):
    names = ["0", "1", "2", "3+"]
    print("confusion matrix (rows = true, cols = predicted)")
    print("       " + "".join(f"{n:>6}" for n in names))
    for name, row in zip(names, m):
        print(f"  {name:>3}  " + "".join(f"{v:>6}" for v in row))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", "--data_url", default=str(ROOT / "ml" / "data" / "train.csv"))
    ap.add_argument("--out", "--train_url", default=str(ROOT / "ml" / "model"))
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--test_frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--platform", choices=["local", "modelarts"], default="local")
    ap.add_argument("--trained_on", default="", help='data description stored with the model, e.g. "synthetic"')
    ap.add_argument("--thresholds", default=os.getenv("HEADCOUNT_THRESHOLDS") or ",".join(map(str, THRESHOLDS)),
                    help="threshold rule to compare against, as in HEADCOUNT_THRESHOLDS (default: the server's)")
    args, _ = ap.parse_known_args()  # ModelArts may pass extra arguments

    import mindspore as ms
    from mindspore import Tensor, nn

    ms.set_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    ms.set_context(mode=ms.PYNATIVE_MODE)

    tmp = tempfile.mkdtemp()
    rows = load_csv(fetch(args.data, tmp))
    if "session" in rows[0]:
        train_rows, test_rows, how, notes = session_split(rows, args.test_frac)
    else:  # a train.csv made before sessions were recorded
        train_rows, test_rows = time_split(rows, args.test_frac)
        how, notes = f"by time block: the last {args.test_frac:.0%} of each room's timeline is the test set", []
    print(f"Train/test split {how} (not random rows).")
    for note in notes:
        print(f"note: {note}")
    if not test_rows:
        raise SystemExit("No test sessions: record at least 2 sessions per headcount (see docs/DATA_COLLECTION.md).")
    x_tr, y_tr = arrays(train_rows)
    x_te, y_te = arrays(test_rows)
    mean, std = x_tr.mean(axis=0), x_tr.std(axis=0) + 1e-6
    print(f"MindSpore {ms.__version__} | {len(train_rows)} train, {len(test_rows)} test rows | "
          f"train per class 0/1/2/3+: {np.bincount(y_tr, minlength=4).tolist()}")

    class Net(nn.Cell):
        def __init__(self, n_in, n_hidden, n_out):
            super().__init__()
            self.fc1 = nn.Dense(n_in, n_hidden)
            self.relu = nn.ReLU()
            self.fc2 = nn.Dense(n_hidden, n_out)

        def construct(self, x):
            return self.fc2(self.relu(self.fc1(x)))

    net = Net(len(FEATURES), args.hidden, len(CLASSES))
    loss_fn = nn.CrossEntropyLoss()
    opt = nn.Adam(net.trainable_params(), learning_rate=args.lr)
    grad_fn = ms.value_and_grad(lambda x, y: loss_fn(net(x), y), None, opt.parameters)

    xs = (x_tr - mean) / std
    batch = 64
    for epoch in range(1, args.epochs + 1):
        order = np.random.permutation(len(xs))
        total = 0.0
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            loss, grads = grad_fn(Tensor(xs[idx]), Tensor(y_tr[idx]))
            opt(grads)
            total += float(loss.asnumpy()) * len(idx)
        if epoch == 1 or epoch % 10 == 0:
            print(f"epoch {epoch:>3}  loss {total / len(xs):.4f}")

    logits = net(Tensor((x_te - mean) / std)).asnumpy()
    pred = logits.argmax(axis=1)
    acc = float((pred == y_te).mean())
    thresholds = [float(v) for v in args.thresholds.split(",")]
    base_pred = (x_te[:, FEATURES.index("motion_std")][:, None] > np.array(thresholds)).sum(axis=1)
    base_acc = float((base_pred == y_te).mean())
    cm = confusion(y_te, pred)
    print(f"\ntrained on: {data_kind(rows)}")
    print(f"test accuracy: {acc:.3f}  (threshold rule {args.thresholds} on the same rows: {base_acc:.3f})")
    print("model:")
    print_confusion(cm)
    print("threshold rule:")
    print_confusion(confusion(y_te, base_pred))

    out_local = Path(tmp) / "out" if str(args.out).startswith("obs://") else Path(args.out)
    out_local.mkdir(parents=True, exist_ok=True)
    ms.save_checkpoint(net, str(out_local / "nadi_mlp.ckpt"))
    try:  # MINDIR rejects spaces in paths, so export from inside the output folder
        cwd = os.getcwd()
        os.chdir(out_local)
        try:
            ms.export(net, Tensor(np.zeros((1, len(FEATURES)), np.float32)), file_name="nadi_mlp", file_format="MINDIR")
        finally:
            os.chdir(cwd)
    except Exception as e:  # MINDIR is a bonus; the JSON is what the server needs
        print(f"MINDIR export skipped: {e}")
    model = {
        "framework": f"MindSpore {ms.__version__}",
        "platform": args.platform,
        "trained_on": args.trained_on or data_kind(rows),
        "trained_at": int(time.time()),
        "n_train": len(train_rows),
        "accuracy": round(acc, 4),
        "threshold_accuracy": round(base_acc, 4),
        "thresholds": thresholds,
        "n_test": len(test_rows),
        "confusion": cm.tolist(),
        "features": FEATURES,
        "mean": mean.tolist(),
        "std": std.tolist(),
        "classes": CLASSES,
        "layers": [
            {"W": net.fc1.weight.asnumpy().tolist(), "b": net.fc1.bias.asnumpy().tolist()},
            {"W": net.fc2.weight.asnumpy().tolist(), "b": net.fc2.bias.asnumpy().tolist()},
        ],
    }
    (out_local / "nadi_model.json").write_text(json.dumps(model), encoding="utf-8")
    if str(args.out).startswith("obs://"):
        import moxing as mox

        mox.file.copy_parallel(str(out_local), str(args.out))
    print(f"saved model to {args.out}")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    os.environ.setdefault("GLOG_v", "3")  # quieter MindSpore logs
    main()
