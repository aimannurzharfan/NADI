# Training the occupancy model on Huawei ModelArts

`ml/train.py` is the same script locally and on ModelArts. Locally it trains on CPU with MindSpore 2.10; on ModelArts it runs in a MindSpore training image and reads/writes OBS.

Not run on ModelArts yet (no cloud access until the coupon). Region: **CN-Hong Kong (ap-southeast-1)**.

## Local (what runs today)

MindSpore has no wheel for Python 3.13, so training uses its own Python 3.11 venv:

```powershell
uv venv -p 3.11 .venv-ml
uv pip install -p .venv-ml\Scripts\python.exe -r ml\requirements.txt

.\.venv\Scripts\python ml\synth_labels.py                                  # synthetic rows + labels (until real labels exist)
.\.venv\Scripts\python ml\prepare.py --labels ml\data\labels_synth.csv     # -> ml\data\train.csv
.\.venv-ml\Scripts\python ml\train.py                                      # -> ml\model\
```

With real data: teammates fill `ml/data/labels.csv` (`room_id,start_ts,end_ts,headcount`), then `python ml/prepare.py` (no `--labels`) and `train.py` again.

Output in `ml/model/`: `nadi_mlp.ckpt` (MindSpore checkpoint), `nadi_mlp.mindir` (MINDIR export), `nadi_model.json` (weights + scaling + metrics). The server loads `nadi_model.json` and picks up a new one without a restart.

## On ModelArts

1. **OBS bucket** (same region): create `nadi-ml` with folders `code/`, `data/`, `output/`.
2. Upload:
   - `ml/train.py` -> `obs://nadi-ml/code/train.py`
   - `ml/data/train.csv` (from `prepare.py`) -> `obs://nadi-ml/data/train.csv`
3. **ModelArts > Model Training > Training Jobs > Create Training Job**:
   - Algorithm type: **Custom algorithm**
   - Boot mode: **Preset image**, engine **MindSpore**, pick the newest CPU image offered (any MindSpore 2.x works; the script only uses `nn.Dense`, `nn.Adam`, `value_and_grad`)
   - Code directory: `obs://nadi-ml/code/`; boot file: `obs://nadi-ml/code/train.py`
   - Input: name **`data`**, OBS path `obs://nadi-ml/data/` (ModelArts mounts it as a folder and passes `--data=<folder>`; `train.py` reads `train.csv` inside it)
   - Output: name **`out`**, OBS path `obs://nadi-ml/output/` (passed as `--out=<folder>`, uploaded to OBS when the job ends)
   - Hyperparameters: `platform` = `modelarts` (shows "trained on Huawei ModelArts" on the dashboard), optionally `epochs` = `60`
   - Resource: the smallest **CPU** flavor (check for a free CPU spec in the list; the job needs well under a minute of compute)
4. Submit. The job log should end with `test accuracy: ...`, the confusion matrix and `saved model to ...`.
5. Download `obs://nadi-ml/output/nadi_model.json` and put it at `ml/model/nadi_model.json` on the server (or point `MODEL_PATH` at it).

If the console's argument names differ (older jobs use `data_url` / `train_url`), `train.py` accepts those too, and `obs://` paths given directly as arguments are copied with `moxing`, which ModelArts images include.

## Proof for the judges

- ModelArts training job page: status **Completed**, the log with the accuracy and confusion matrix.
- OBS `output/` folder with the `.ckpt`, `.mindir` and `.json`.
- Dashboard footer: `MindSpore 2.x occupancy model (trained on Huawei ModelArts, ... data)`.

## Honest numbers

On synthetic data the model scores 1.000 and the simple threshold rule 0.997, because the simulator makes headcount almost a straight line in `motion_std`. That proves the pipeline works, not the model. Only accuracy on real labelled CSI goes on the slides.
