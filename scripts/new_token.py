"""Make a new random token (32 bytes, URL-safe) for NADI.

    python scripts/new_token.py                     print one token
    python scripts/new_token.py --admin warden-1    add a named admin token to ADMIN_TOKENS in .env
    python scripts/new_token.py --viewer            set VIEWER_TOKEN in .env (read-only dashboard access)
    python scripts/new_token.py --ingest            set INGEST_TOKEN in .env (IoTDA HTTP push)

The new token is printed once so you can hand it to that person; existing tokens in .env are never printed.
Named admin tokens show in the audit log as the name ("warden-1"), so each warden or judge gets their own and one
can be removed without changing the others. Restart the server afterwards.
"""
import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
LABEL = re.compile(r"[A-Za-z0-9_-]{1,32}")


def read_env():
    return ENV.read_text(encoding="utf-8") if ENV.exists() else ""


def get(text, key):
    m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
    return m.group(1).strip() if m else ""


def put(text, key, value):
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        return re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def main():
    ap = argparse.ArgumentParser(description="Make a new random token for NADI.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--admin", metavar="NAME", help="add a named admin token to ADMIN_TOKENS in .env")
    group.add_argument("--viewer", action="store_true", help="set VIEWER_TOKEN in .env")
    group.add_argument("--ingest", action="store_true", help="set INGEST_TOKEN in .env")
    args = ap.parse_args()
    token = secrets.token_urlsafe(32)
    if not (args.admin or args.viewer or args.ingest):
        print(token)
        return
    if not ENV.exists():
        sys.exit("No .env file. Copy .env.example to .env first.")
    text = read_env()
    if args.admin:
        if not LABEL.fullmatch(args.admin):
            sys.exit("The name may use only letters, digits, - and _ (up to 32).")
        entries = [e.strip() for e in get(text, "ADMIN_TOKENS").split(",") if e.strip()]
        if any(e.partition(":")[0].strip() == args.admin for e in entries):
            sys.exit(f"ADMIN_TOKENS already has a token named {args.admin}. Remove it from .env first to replace it.")
        text = put(text, "ADMIN_TOKENS", ",".join(entries + [f"{args.admin}:{token}"]))
        what = f"admin token {args.admin} (added to ADMIN_TOKENS)"
    else:
        key = "VIEWER_TOKEN" if args.viewer else "INGEST_TOKEN"
        text = put(text, key, token)
        what = key
    ENV.write_text(text, encoding="utf-8")
    print(f"New {what}, written to .env:")
    print(token)
    print("Give it only to the person who needs it, then restart the server.")


if __name__ == "__main__":
    main()
