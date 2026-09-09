#!/usr/bin/env python3
"""
Account & Subscription Server — MVP, pure Python standard library (no pip deps).

Provides the login/subscription-tier gate for the bug-bounty tool: a user
registers/logs in once (their own account, separate from their HackerOne
credentials), and every real scan checks in here before it runs so a
per-day scan quota can be enforced per tier.

This is intentionally minimal:
- SQLite for storage (users + daily usage counters).
- PBKDF2-HMAC-SHA256 password hashing (stdlib hashlib, no bcrypt dependency).
- Plain stdlib http.server for the HTTP API (no Flask/FastAPI dependency).
- Tier upgrades are manual (POST /admin/set-tier) until real billing
  (Stripe/Paddle) is wired up — see docs/FUTURE_FEATURES.md item 4.

Run: python3 recon/account_server.py [--host 127.0.0.1] [--port 8899]
"""

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("ACCOUNT_DB_PATH", str(BASE / "account_data.db")))
ADMIN_SECRET = os.environ.get("ACCOUNT_ADMIN_SECRET", "")

TIER_DAILY_LIMITS = {
    "free": int(os.environ.get("ACCOUNT_FREE_DAILY_LIMIT", "3")),
    "paid": int(os.environ.get("ACCOUNT_PAID_DAILY_LIMIT", "50")),
    "unlimited": None,  # operator/admin tier — no cap, used for mohit's own existing programs
}

PBKDF2_ITERATIONS = 100_000
TOKEN_MAX_AGE_SECONDS = int(os.environ.get("ACCOUNT_TOKEN_MAX_AGE_SECONDS", str(30 * 24 * 3600)))  # 30 days
TRIAL_DAYS = int(os.environ.get("ACCOUNT_TRIAL_DAYS", "4"))
TRIAL_SECONDS = TRIAL_DAYS * 24 * 3600

# ---- Brute-force protection on /login and /register (per-IP, in-memory) ----
# ThreadingHTTPServer spawns a thread per request, so this dict needs a lock.
MAX_AUTH_ATTEMPTS = int(os.environ.get("ACCOUNT_MAX_AUTH_ATTEMPTS", "5"))
AUTH_LOCKOUT_SECONDS = int(os.environ.get("ACCOUNT_AUTH_LOCKOUT_SECONDS", "300"))
_auth_attempts_lock = threading.Lock()
_auth_attempts: dict[str, list[float]] = {}


def _record_failed_attempt(ip: str) -> None:
    with _auth_attempts_lock:
        now = time.time()
        attempts = [t for t in _auth_attempts.get(ip, []) if now - t < AUTH_LOCKOUT_SECONDS]
        attempts.append(now)
        _auth_attempts[ip] = attempts


def _is_locked_out(ip: str) -> bool:
    with _auth_attempts_lock:
        now = time.time()
        attempts = [t for t in _auth_attempts.get(ip, []) if now - t < AUTH_LOCKOUT_SECONDS]
        _auth_attempts[ip] = attempts
        return len(attempts) >= MAX_AUTH_ATTEMPTS


def _clear_attempts(ip: str) -> None:
    with _auth_attempts_lock:
        _auth_attempts.pop(ip, None)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            token TEXT UNIQUE,
            token_created_at REAL,
            tier TEXT NOT NULL DEFAULT 'free',
            trial_started_at REAL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS usage (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            scan_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )"""
    )
    _migrate_users_columns(conn)
    conn.commit()
    return conn


def _migrate_users_columns(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS never adds columns to an already-existing
    table — a DB created before trial_started_at was added would otherwise
    crash every query that references it. Add the column, then backfill any
    row that predates it with "starting now" rather than leaving it NULL
    (NULL would be read as "trial check doesn't apply" — a permanent
    free-trial-expiry bypass for every pre-existing account, not intended)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "trial_started_at" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN trial_started_at REAL")
        conn.execute("UPDATE users SET trial_started_at = ? WHERE trial_started_at IS NULL", (time.time(),))


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    computed, _ = hash_password(password, salt)
    return secrets.compare_digest(computed, password_hash)


def today() -> str:
    return date.today().isoformat()


class AccountHandler(BaseHTTPRequestHandler):
    server_version = "BugBountyAccountServer/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _bearer_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):].strip()
        return None

    def _user_by_token(self, conn: sqlite3.Connection):
        token = self._bearer_token()
        if not token:
            return None
        row = conn.execute(
            "SELECT id, email, tier, token_created_at, trial_started_at FROM users WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        user_id, email, tier, token_created_at, trial_started_at = row
        if token_created_at is not None and (time.time() - token_created_at) > TOKEN_MAX_AGE_SECONDS:
            return None  # expired — treat exactly like an invalid token
        return (user_id, email, tier, trial_started_at)

    def log_message(self, fmt, *args):  # quieter default logging
        sys.stderr.write("[account_server] " + (fmt % args) + "\n")

    def do_POST(self):
        conn = get_db()
        try:
            if self.path == "/register":
                self._handle_register(conn)
            elif self.path == "/login":
                self._handle_login(conn)
            elif self.path == "/check-and-record-scan":
                self._handle_check_and_record_scan(conn)
            elif self.path == "/admin/set-tier":
                self._handle_admin_set_tier(conn)
            elif self.path == "/admin/reset-password":
                self._handle_admin_reset_password(conn)
            else:
                self._send_json(404, {"error": "not found"})
        finally:
            conn.close()

    def do_GET(self):
        conn = get_db()
        try:
            if self.path == "/me":
                self._handle_me(conn)
            elif self.path == "/health":
                self._send_json(200, {"status": "ok"})
            else:
                self._send_json(404, {"error": "not found"})
        finally:
            conn.close()

    def _handle_register(self, conn):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        if not email or not password or len(password) < 8:
            self._send_json(400, {"error": "email aur kam-se-kam 8-character password zaroori hai"})
            return
        ip = self.client_address[0]
        if _is_locked_out(ip):
            self._send_json(429, {"error": f"Bahut zyada attempts. {AUTH_LOCKOUT_SECONDS // 60} minute baad try karo."})
            return
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            _record_failed_attempt(ip)
            self._send_json(409, {"error": "is email se account pehle se hai — login use karo"})
            return
        pw_hash, salt = hash_password(password)
        token = secrets.token_hex(32)
        now = time.time()
        conn.execute(
            "INSERT INTO users (email, password_hash, salt, token, token_created_at, tier, trial_started_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (email, pw_hash, salt, token, now, "free", now, today()),
        )
        conn.commit()
        _clear_attempts(ip)
        self._send_json(201, {"token": token, "tier": "free", "trial_days": TRIAL_DAYS})

    def _handle_login(self, conn):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        ip = self.client_address[0]
        if _is_locked_out(ip):
            self._send_json(429, {"error": f"Bahut zyada attempts. {AUTH_LOCKOUT_SECONDS // 60} minute baad try karo."})
            return
        row = conn.execute(
            "SELECT id, password_hash, salt, tier FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row or not verify_password(password, row[1], row[2]):
            _record_failed_attempt(ip)
            self._send_json(401, {"error": "email ya password galat hai"})
            return
        token = secrets.token_hex(32)
        conn.execute("UPDATE users SET token = ?, token_created_at = ? WHERE id = ?", (token, time.time(), row[0]))
        conn.commit()
        _clear_attempts(ip)
        self._send_json(200, {"token": token, "tier": row[3]})

    def _handle_me(self, conn):
        user = self._user_by_token(conn)
        if not user:
            self._send_json(401, {"error": "invalid ya missing token"})
            return
        user_id, email, tier, trial_started_at = user
        row = conn.execute(
            "SELECT scan_count FROM usage WHERE user_id = ? AND date = ?", (user_id, today())
        ).fetchone()
        scans_today = row[0] if row else 0
        limit = TIER_DAILY_LIMITS.get(tier, TIER_DAILY_LIMITS["free"])
        trial_days_remaining = None
        if tier == "free" and trial_started_at is not None:
            remaining_seconds = TRIAL_SECONDS - (time.time() - trial_started_at)
            trial_days_remaining = max(0, int(remaining_seconds // 86400) + (1 if remaining_seconds % 86400 > 0 else 0))
        self._send_json(200, {
            "email": email,
            "tier": tier,
            "scans_today": scans_today,
            "daily_limit": limit,
            "remaining": None if limit is None else max(0, limit - scans_today),
            "trial_days_remaining": trial_days_remaining,
        })

    def _handle_check_and_record_scan(self, conn):
        user = self._user_by_token(conn)
        if not user:
            self._send_json(401, {"error": "invalid ya missing token"})
            return
        user_id, email, tier, trial_started_at = user

        if tier == "free" and trial_started_at is not None and (time.time() - trial_started_at) > TRIAL_SECONDS:
            self._send_json(200, {
                "allowed": False,
                "reason": f"{TRIAL_DAYS}-din ka free trial khatam ho gaya. Jaari rakhne ke liye subscribe karo.",
                "trial_expired": True,
            })
            return

        limit = TIER_DAILY_LIMITS.get(tier, TIER_DAILY_LIMITS["free"])
        d = today()
        row = conn.execute(
            "SELECT scan_count FROM usage WHERE user_id = ? AND date = ?", (user_id, d)
        ).fetchone()
        scans_today = row[0] if row else 0

        if limit is not None and scans_today >= limit:
            self._send_json(200, {
                "allowed": False,
                "reason": f"Daily scan limit ({limit}) reached for tier '{tier}'. Upgrade for more.",
                "scans_today": scans_today,
                "daily_limit": limit,
            })
            return

        if row:
            conn.execute(
                "UPDATE usage SET scan_count = scan_count + 1 WHERE user_id = ? AND date = ?",
                (user_id, d),
            )
        else:
            conn.execute(
                "INSERT INTO usage (user_id, date, scan_count) VALUES (?, ?, 1)", (user_id, d)
            )
        conn.commit()
        self._send_json(200, {
            "allowed": True,
            "scans_today": scans_today + 1,
            "daily_limit": limit,
            "remaining": None if limit is None else max(0, limit - (scans_today + 1)),
        })

    def _handle_admin_set_tier(self, conn):
        ip = self.client_address[0]
        if _is_locked_out(ip):
            self._send_json(429, {"error": f"Bahut zyada attempts. {AUTH_LOCKOUT_SECONDS // 60} minute baad try karo."})
            return
        supplied = self.headers.get("X-Admin-Secret", "")
        if not ADMIN_SECRET or not secrets.compare_digest(supplied, ADMIN_SECRET):
            _record_failed_attempt(ip)
            self._send_json(403, {"error": "invalid admin secret"})
            return
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        tier = body.get("tier") or ""
        if tier not in TIER_DAILY_LIMITS:
            self._send_json(400, {"error": f"tier must be one of {list(TIER_DAILY_LIMITS)}"})
            return
        cur = conn.execute("UPDATE users SET tier = ? WHERE email = ?", (tier, email))
        conn.commit()
        if cur.rowcount == 0:
            self._send_json(404, {"error": "user not found"})
            return
        self._send_json(200, {"ok": True, "email": email, "tier": tier})

    def _handle_admin_reset_password(self, conn):
        # Admin-assisted reset (no email/SMTP infra yet) — a customer emails/messages
        # the operator "forgot my password", operator runs this with a new temp
        # password, tells the customer to log in and (ideally) change it again.
        ip = self.client_address[0]
        if _is_locked_out(ip):
            self._send_json(429, {"error": f"Bahut zyada attempts. {AUTH_LOCKOUT_SECONDS // 60} minute baad try karo."})
            return
        supplied = self.headers.get("X-Admin-Secret", "")
        if not ADMIN_SECRET or not secrets.compare_digest(supplied, ADMIN_SECRET):
            _record_failed_attempt(ip)
            self._send_json(403, {"error": "invalid admin secret"})
            return
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        new_password = body.get("new_password") or ""
        if len(new_password) < 8:
            self._send_json(400, {"error": "new_password kam-se-kam 8 characters ka hona chahiye"})
            return
        pw_hash, salt = hash_password(new_password)
        # Also invalidate any existing session token — a leaked/forgotten-password
        # account shouldn't keep a still-valid old token floating around.
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, token = NULL, token_created_at = NULL WHERE email = ?",
            (pw_hash, salt, email),
        )
        conn.commit()
        if cur.rowcount == 0:
            self._send_json(404, {"error": "user not found"})
            return
        self._send_json(200, {"ok": True, "email": email})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("ACCOUNT_SERVER_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("ACCOUNT_SERVER_PORT", "8899")))
    args = ap.parse_args()

    get_db().close()  # ensure tables exist before serving
    httpd = ThreadingHTTPServer((args.host, args.port), AccountHandler)
    print(f"[account_server] listening on http://{args.host}:{args.port}  (db={DB_PATH})")
    if not ADMIN_SECRET:
        print("[account_server] WARNING: ACCOUNT_ADMIN_SECRET not set — /admin/set-tier is disabled.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
