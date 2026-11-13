# Retrain the occupancy model on the real labels and switch the server to it only if it beats the threshold rule.
#   powershell -ExecutionPolicy Bypass -File scripts\retrain.ps1
# 1. ml/prepare.py   ml/data/labels.csv (from the /label page or the team sheet) + MySQL readings -> ml/data/train.csv
# 2. ml/train.py     MindSpore in .venv-ml -> ml/model/candidate/, prints accuracy and both confusion matrices.
#                   Test set = whole labelling sessions held out (not random rows), see docs/DATA_COLLECTION.md
# 3. scripts/promote_model.py   copies it to ml/model/nadi_model.json only if it is real data and beats the rule
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$pyml = Join-Path $root ".venv-ml\Scripts\python.exe"
$labels = Join-Path $root "ml\data\labels.csv"

if (-not (Test-Path $labels)) { Write-Output "No ml\data\labels.csv yet. Label with the /label page first."; exit 1 }
if (-not (Test-Path $pyml)) { Write-Output "No .venv-ml (MindSpore). See ml\MODELARTS.md for the set-up."; exit 1 }

# The threshold rule the server uses now, from .env (value only passed on, never printed)
$thresholds = (Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*HEADCOUNT_THRESHOLDS\s*=' } |
    Select-Object -First 1) -replace '^\s*HEADCOUNT_THRESHOLDS\s*=\s*', ''
if (-not $thresholds) { $thresholds = "0.35,0.95,1.55" }

Write-Output "== 1/3 prepare: real labels + readings"
& $py ml\prepare.py --labels $labels --out ml\data\train.csv
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "`n== 2/3 train (MindSpore). Test set: whole labelling sessions held out, not random rows."
$candidate = Join-Path $root "ml\model\candidate"
if (Test-Path $candidate) { Remove-Item -Recurse -Force $candidate }
& $pyml ml\train.py --data ml\data\train.csv --out $candidate --thresholds $thresholds
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "`n== 3/3 compare and switch"
& $py scripts\promote_model.py --candidate $candidate
exit 0
