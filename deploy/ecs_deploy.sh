#!/usr/bin/env bash
# Runs on the ECS host, called by the CodeArts Deploy job (deploy/CODEARTS.md step 5).
# Unpacks a build into a new release folder, installs dependencies, switches /opt/nadi/current
# to it and restarts the service. Keeps the last 5 releases for rollback.
#
#   sudo bash ecs_deploy.sh /tmp/nadi/nadi.tar.gz
set -euo pipefail

APP=/opt/nadi
PKG=${1:-/tmp/nadi/nadi.tar.gz}

# Take back the app folder first: older versions of this script made it nadi-owned, and nadi could
# have planted symlinks there (e.g. .env -> /etc/shadow) for the chown/chmod below to follow.
mkdir -p "$APP"
chown root:root "$APP"
chmod 755 "$APP"
for p in "$APP/.env" "$APP/releases" "$APP/venv"; do
  if [ -L "$p" ]; then echo "Refusing to deploy: $p is a symlink. Inspect it and remove it by hand." >&2; exit 1; fi
done
# current must be our symlink (or absent); a real folder there would swallow the new link
if [ -e "$APP/current" ] && [ ! -L "$APP/current" ]; then echo "Refusing to deploy: $APP/current is not a symlink." >&2; exit 1; fi

# .env holds the huawei-mode settings and secrets; it lives on the server only, never in git
if [ ! -f "$APP/.env" ]; then
  echo "Missing $APP/.env: copy .env.example there, set NADI_MODE=huawei and fill in the cloud values." >&2
  exit 1
fi

id nadi >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin nadi
# Code and venv are root-owned and not writable by the service user: pip runs from the venv as root
# on every deploy, so nadi must never be able to change anything there. nadi only reads .env.
# All of this happens BEFORE the new release is created, so nothing nadi planted earlier gets used.
# -h: change symlinks themselves, never what they point to. chmod -R skips symlinks.
mkdir -p "$APP/releases"
chown -hR root:root "$APP/releases"
chmod -R go-w "$APP/releases"
[ -d "$APP/venv" ] && chown -hR root:root "$APP/venv" && chmod -R go-w "$APP/venv"
chown -h root:nadi "$APP/.env"
chmod 640 "$APP/.env"

# New release folder: unpredictable name, created atomically by root (mktemp fails if the path exists)
REL=$(mktemp -d "$APP/releases/$(date +%Y%m%d%H%M%S).XXXXXX")
chmod 755 "$REL"
if [ -L "$REL" ] || [ "$(stat -c %u "$REL")" != 0 ]; then echo "Refusing: $REL is not a root-owned folder" >&2; exit 1; fi
tar --no-same-owner -xzf "$PKG" -C "$REL"
chmod -R go-w "$REL"
ln -sfn "$APP/.env" "$REL/.env"

python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q -r "$REL/requirements.txt"
chmod -R go-w "$APP/venv"

ln -sfn "$REL" "$APP/current"

# Unit file comes from the release just extracted above (root-owned), not from a nadi-writable path
cp "$REL/deploy/nadi.service" /etc/systemd/system/nadi.service
systemctl daemon-reload
systemctl enable nadi
systemctl restart nadi

# Health check: the deploy job fails if the server doesn't come up
for _ in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8000/api/info; then echo; echo "NADI deployed: $REL"; break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/api/info >/dev/null

# Keep the 5 newest releases
ls -1dt "$APP"/releases/* | tail -n +6 | xargs -r rm -rf
