# Contributing

## Set up

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
.\.venv\Scripts\python scripts\mqtt_users.py
docker compose up -d --wait
```

Model training needs a separate Python 3.11 environment for MindSpore (see [ml/MODELARTS.md](ml/MODELARTS.md)). Firmware builds run in Docker (see [firmware/README.md](firmware/README.md)).

## Run the tests

```powershell
.\.venv\Scripts\python -m pytest                    # server
cd web; npm install; npm test; cd ..                 # web console (after a change in web/src: npm run build)
.\.venv\Scripts\python -m pytest tests_e2e           # end to end in Microsoft Edge, needs the Docker services
```

The server tests need no Redis, MySQL, broker or cloud: every test gets its own in-memory Redis (fakeredis), so a test can never touch the real Valkey. Stress tests against the running stack are in `scripts/stress/` ([docs/TESTING.md](docs/TESTING.md)). Stop anything left over with `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1`.

## Secret scan before every commit

Turn on the pre-commit hook once per clone. It runs gitleaks on the staged changes and refuses a commit that adds a key, token or password:

```powershell
git config core.hooksPath scripts/hooks
```

It needs gitleaks 8.30.1 on the PATH: download `gitleaks_8.30.1_windows_x64.zip` from the gitleaks releases on GitHub, check its SHA-256 against the release's checksums file (`d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e`), and put `gitleaks.exe` in a folder on the PATH. `.gitleaks.toml` allows only the made-up test tokens that contain `0123456789`.

## Continuous checks

`.github/workflows/ci.yml` runs on every push and pull request, with no secrets: pytest, the console unit tests, `pip-audit`, `npm audit` (fails on high or critical) and gitleaks over the whole history. After changing `requirements.txt` or `web/package.json`, run `.\.venv\Scripts\python scripts\sbom.py` to refresh `docs/sbom/`.

## Rules

- **Never commit secrets.** Keys, passwords, device secrets and tokens go in `.env`, which git ignores. Add any new setting to `.env.example` with an empty or example value.
- **Only counts leave the room.** Never store MAC addresses, names, images or raw packets. See [PRIVACY.md](PRIVACY.md).
- **Wording lives in one place.** Every phrase a user sees is in `dashboard/strings.json`, in English and Malay. After changing it, run `.\.venv\Scripts\python scripts\glossary.py`; the tests fail if a key is missing or the glossary is out of date.
- **House style for text:** formal and plain, British spelling ("colour", "metres"), "air conditioning" not "aircon", no em dashes. Malay is standard Malay (bahasa baku).
- **Simple beats clever.** No new frameworks without a good reason.

## Commit messages

- First line: what the change does, in the imperative, sentence case, no full stop, about 70 characters at most. For example: `Drop history rows MySQL refuses instead of retrying them forever`.
- Then a blank line and, if needed, a few lines or bullets on why.
- One logical change per commit. Run the tests before committing.

## Reporting problems

Bugs: open an issue. Security problems: see [SECURITY.md](SECURITY.md) and report them privately.
