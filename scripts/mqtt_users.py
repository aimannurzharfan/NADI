"""Write the local Mosquitto login file (deploy/mosquitto/passwd, git-ignored) from .env.

Users:
  nadi-server                 password MQTT_SERVER_PASSWORD (the NADI server)
  each ID in MQTT_DEVICE_IDS  its own password, MQTT_PASSWORD_<ID> (nadi-recv-1 -> MQTT_PASSWORD_NADI_RECV_1);
                              username = device ID. A password read out of one board cannot log in as another.

Empty passwords are filled in .env with random ones. Passwords are never printed.
Run again after changing MQTT_DEVICE_IDS or a password, then: docker compose restart mosquitto

    python scripts/mqtt_users.py
"""
import base64
import hashlib
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
PASSWD = ROOT / "deploy" / "mosquitto" / "passwd"
SERVER_USER = "nadi-server"  # also named in deploy/mosquitto/acl
ITERATIONS = 101  # mosquitto_passwd default for PBKDF2-SHA512
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def device_password_key(device_id):
    """The .env key holding a device's broker password: nadi-recv-1 -> MQTT_PASSWORD_NADI_RECV_1."""
    return "MQTT_PASSWORD_" + re.sub(r"[^A-Z0-9]", "_", device_id.upper())


def mosquitto_hash(password, salt=None):
    """Same format mosquitto_passwd writes: $7$<iterations>$<base64 salt>$<base64 PBKDF2-SHA512>."""
    salt = salt or secrets.token_bytes(12)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, ITERATIONS)
    return f"$7${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def read_env():
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2).strip()
    return values


def set_env(key, value):
    """Set KEY=value in .env, replacing an existing line or adding one at the end."""
    text = ENV.read_text(encoding="utf-8")
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    ENV.write_text(text, encoding="utf-8")


def main(restart_hint=True):
    if not ENV.exists():
        sys.exit("No .env file. Copy .env.example to .env first.")
    env = read_env()
    devices = [d.strip() for d in env.get("MQTT_DEVICE_IDS", "").split(",") if d.strip()]
    if not devices:
        sys.exit("MQTT_DEVICE_IDS is empty in .env. List every board and the simulator, "
                 "for example: MQTT_DEVICE_IDS=nadi-sim,nadi-recv-1,nadi-climate-1")
    bad = [d for d in devices if not DEVICE_ID.fullmatch(d) or d == SERVER_USER]
    if bad:
        sys.exit(f"Device IDs may use only letters, digits, - and _ (and not {SERVER_USER}): {bad}")
    keys = [device_password_key(d) for d in devices]
    if len(set(keys)) != len(keys):
        sys.exit("Two device IDs differ only in case or - versus _, so they would share a password. Rename one.")

    for key in ["MQTT_SERVER_PASSWORD", *keys]:
        if not env.get(key):
            set_env(key, secrets.token_urlsafe(18))
            print(f"{key} was empty: a random password was written to .env.")
    env = read_env()

    lines = [f"{SERVER_USER}:{mosquitto_hash(env['MQTT_SERVER_PASSWORD'])}"]
    lines += [f"{d}:{mosquitto_hash(env[k])}" for d, k in zip(devices, keys)]
    PASSWD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {PASSWD.relative_to(ROOT)} with {SERVER_USER} and {len(devices)} device(s): {', '.join(devices)}.")
    print(f"Board passwords are in .env as {', '.join(keys)}.")
    if restart_hint:
        print("Restart the broker to load it: docker compose up -d --force-recreate mosquitto")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
