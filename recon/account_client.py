#!/usr/bin/env python3
"""
Account Client — talks to recon/account_server.py for login + the
per-scan subscription-tier gate. Pure Python standard library (no pip deps),
mirrors recon/h1_client.py's credential-file pattern.

Credentials/session token live in <workspace>/.env.account (chmod 600,
gitignored — see .gitignore's **/.env.* pattern). This file is deliberately
separate from .env.h1: .env.h1 is the user's OWN HackerOne API credentials
(what lets the tool scan programs they're already authorized on); .env.account
is this product's own login (what the subscription/scan-quota gate checks).

check_scan_allowed() is called once per real pipeline run (see
recon_pipeline.py's main()) — it is the actual enforcement point, not just a
TUI-level suggestion, so it applies even if a scan is triggered directly via
`python3 recon/recon_pipeline.py` rather than through start-bugbounty.sh.

Fails CLOSED by default if the account server is unreachable (blocks the scan)
— an unreachable server must never become a free bypass (e.g. by firewalling
outbound traffic to it). The only way to allow scans while offline is to
explicitly set ACCOUNT_OFFLINE_DEV_MODE=1, which is meant for solo local
development only and must never be set on anything resembling a real,
deployed gate for paying strangers.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ENV_FILE = BASE / ".env.account"
SERVER_URL = os.environ.get("ACCOUNT_SERVER_URL", "http://127.0.0.1:8899").rstrip("/")


def _read_env_file() -> dict:
    creds = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")
    return creds


def get_token() -> str | None:
    token = os.environ.get("ACCOUNT_TOKEN", "").strip()
    if token:
        return token
    return _read_env_file().get("ACCOUNT_TOKEN") or None


def _save_token(email: str, token: str, tier: str) -> None:
    ENV_FILE.write_text(
        "# Bug-bounty tool account login (separate from .env.h1's HackerOne API creds).\n"
        "# Never committed (see .gitignore: **/.env.*).\n"
        f"export ACCOUNT_EMAIL=\"{email}\"\n"
        f"export ACCOUNT_TOKEN=\"{token}\"\n"
        f"# tier at time of login (server is the source of truth, this is just informational): {tier}\n",
        encoding="utf-8",
    )
    os.chmod(ENV_FILE, 0o600)


def _request(method: str, path: str, body: dict | None = None, token: str | None = None):
    url = f"{SERVER_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def register(email: str, password: str) -> tuple[bool, str]:
    status, data = _request("POST", "/register", {"email": email, "password": password})
    if status == 201:
        _save_token(email, data["token"], data["tier"])
        return True, f"Account bana ({data['tier']} tier). Login ho gaye."
    return False, data.get("error", f"HTTP {status}")


def login(email: str, password: str) -> tuple[bool, str]:
    status, data = _request("POST", "/login", {"email": email, "password": password})
    if status == 200:
        _save_token(email, data["token"], data["tier"])
        return True, f"Login successful ({data['tier']} tier)."
    return False, data.get("error", f"HTTP {status}")


def get_status() -> tuple[bool, dict]:
    token = get_token()
    if not token:
        return False, {"error": "koi account login nahi mila — pehle register/login karo"}
    status, data = _request("GET", "/me", token=token)
    return status == 200, data


def check_scan_allowed() -> tuple[bool, str]:
    """Returns (allowed, message). Fails CLOSED if server unreachable/erroring —
    see module docstring for the ACCOUNT_OFFLINE_DEV_MODE escape hatch."""
    offline_dev_mode = os.environ.get("ACCOUNT_OFFLINE_DEV_MODE", "").strip() == "1"
    token = get_token()
    if not token:
        return False, "Account login zaroori hai scan chalane ke liye (Main Menu -> Account)."
    status, data = _request("POST", "/check-and-record-scan", token=token)
    if status == 0:
        if offline_dev_mode:
            return True, f"⚠ Account server unreachable ({data.get('error')}) — ACCOUNT_OFFLINE_DEV_MODE=1 hai, allowing scan."
        return False, f"Account server unreachable ({data.get('error')}). Scan blocked (fail-closed — set ACCOUNT_OFFLINE_DEV_MODE=1 for solo local dev only)."
    if status == 401:
        return False, "Session expired ya invalid — dobara login karo."
    if status != 200:
        if offline_dev_mode:
            return True, f"⚠ Account server error (HTTP {status}) — ACCOUNT_OFFLINE_DEV_MODE=1 hai, allowing scan."
        return False, f"Account server error (HTTP {status}). Scan blocked (fail-closed)."
    if not data.get("allowed"):
        return False, data.get("reason", "Daily scan limit reached.")
    remaining = data.get("remaining")
    tail = "" if remaining is None else f" ({remaining} scans left today)"
    return True, f"✓ Scan allowed{tail}."


def admin_set_tier(email: str, tier: str, admin_secret: str) -> tuple[bool, str]:
    """Manual tier upgrade — run this yourself after receiving payment directly
    (UPI/bank transfer/etc.) until real billing (Stripe/Paddle) is wired up."""
    # admin endpoint authenticates via X-Admin-Secret, not Bearer token —
    # build the request manually instead of using _request()'s token-based auth.
    req = urllib.request.Request(
        f"{SERVER_URL}/admin/set-tier",
        data=json.dumps({"email": email, "tier": tier}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Admin-Secret": admin_secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, f"✓ {data['email']} ab '{data['tier']}' tier par hai."
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8"))
            return False, data.get("error", f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def admin_reset_password(email: str, new_password: str, admin_secret: str) -> tuple[bool, str]:
    """Admin-assisted password reset — no email/SMTP infra yet, so run this
    yourself when a customer tells you (outside the app) that they're locked out."""
    req = urllib.request.Request(
        f"{SERVER_URL}/admin/reset-password",
        data=json.dumps({"email": email, "new_password": new_password}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Admin-Secret": admin_secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, f"✓ {data['email']} ka password reset ho gaya. Unhe naya password bata do."
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8"))
            return False, data.get("error", f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--status-line", action="store_true",
                     help="one-line status for embedding in the TUI header")
    ap.add_argument("--check-scan", action="store_true")
    ap.add_argument("--admin-set-tier", action="store_true",
                     help="upgrade a customer's tier after receiving payment manually")
    ap.add_argument("--admin-reset-password", action="store_true",
                     help="reset a customer's password when they're locked out (no email infra yet)")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--new-password")
    ap.add_argument("--tier", choices=["free", "paid", "unlimited"])
    ap.add_argument("--admin-secret", help="or set ACCOUNT_ADMIN_SECRET env var")
    args = ap.parse_args()

    if args.admin_reset_password:
        email = args.email or input("Customer email: ").strip()
        new_password = args.new_password or input("New temp password: ").strip()
        secret = args.admin_secret or os.environ.get("ACCOUNT_ADMIN_SECRET", "")
        if not secret:
            secret = input("Admin secret: ").strip()
        ok, msg = admin_reset_password(email, new_password, secret)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.admin_set_tier:
        email = args.email or input("Customer email: ").strip()
        tier = args.tier or input("New tier [free/paid/unlimited]: ").strip()
        secret = args.admin_secret or os.environ.get("ACCOUNT_ADMIN_SECRET", "")
        if not secret:
            secret = input("Admin secret: ").strip()
        ok, msg = admin_set_tier(email, tier, secret)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.register or args.login:
        email = args.email or input("Email: ").strip()
        password = args.password or input("Password: ").strip()
        ok, msg = register(email, password) if args.register else login(email, password)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.status:
        ok, data = get_status()
        print(json.dumps(data, indent=2) if ok else data.get("error", "error"))
        sys.exit(0 if ok else 1)
    elif args.status_line:
        if not get_token():
            print("NOT_LOGGED_IN")
            sys.exit(1)
        ok, data = get_status()
        if not ok:
            print(f"ERROR|{data.get('error', 'unknown')}")
            sys.exit(1)
        remaining = data.get("remaining")
        rem_str = "unlimited" if remaining is None else str(remaining)
        trial_days = data.get("trial_days_remaining")
        trial_str = f"|trial:{trial_days}d left" if trial_days is not None else ""
        print(f"{data['email']}|{data['tier']}|{rem_str}{trial_str}")
        sys.exit(0)
    elif args.check_scan:
        ok, msg = check_scan_allowed()
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    _cli()
