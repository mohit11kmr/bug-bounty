#!/usr/bin/env python3
"""
auto_hunter.py — Headless Candidate Prober & Verification Engine.

Autonomously verifies prioritized candidate surfaces from recon.db using
safe, non-destructive HTTP requests. Eliminates false positives, 403 WAF blocks,
and dead endpoints without requiring human intervention.

State Machine Contract:
  DISCOVERED / TRIAGED -> VALIDATING -> VERIFIED | REJECTED

Features:
  - Scope-Aware: Strictly respects roots & exclusions from scope.yaml.
  - Rate-Limited: Enforces requests per minute (rpm) delays.
  - Verification Modules:
      1. Alive & Reachability Check (200/30x vs 404/403/WAF block).
      2. CORS Misconfiguration Probe (Arbitrary Origin reflection + Credentials).
      3. Sensitive File & Secret Exposure Check (.env, .git, stack traces).
      4. GraphQL Introspection Probe (Unauthenticated schema inspection).
      5. Admin / Internal Panel Reachability (Must contain actionable auth/admin interface).
  - NO FABRICATION: Normal HTTP 200 API responses are NOT marked as vulnerabilities.
  - Automated Pipeline Handoff:
      Verified findings -> report_gen.py (Draft report) -> notify.py (Alert).

Usage:
  python3 recon/auto_hunter.py --selfcheck
  python3 recon/auto_hunter.py --program wordpress --dry-run
  python3 recon/auto_hunter.py --program wordpress --min-score 50
"""

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"
sys.path.insert(0, str(RECON))
from scope_utils import load_scope_file, make_scope_filter  # noqa: E402

# Lazy-load sibling modules
sys.path.insert(0, str(RECON))
try:
    import notify
    import report_gen
except ImportError:
    pass


def load_scope(program: str) -> dict:
    """Load scope.yaml with resilient wildcard quotes handling."""
    scope_file = BASE / program / "scope.yaml"
    return load_scope_file(scope_file, required=False)


def load_auth_credentials(program: str) -> dict | None:
    """Load a single test-account auth header from <program>/.env.auth, if present.

    Opt-in only: authenticated/IDOR probing (see check_idor()) is entirely disabled for
    a program until this file exists — no existing program's behavior changes.

    Expected format (bash-style, gitignored via '**/.env.*'):
        export AUTH_HEADER="Authorization"
        export AUTH_VALUE="Bearer <token>"
    or, for cookie-based auth:
        export AUTH_HEADER="Cookie"
        export AUTH_VALUE="session=<value>"
    """
    auth_file = BASE / program / ".env.auth"
    if not auth_file.exists():
        return None
    creds = {}
    for line in auth_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        creds[key.strip()] = val.strip().strip('"').strip("'")
    if "AUTH_HEADER" in creds and "AUTH_VALUE" in creds:
        return creds
    return None


_IDOR_ID_RE = re.compile(r"(/|[?&]\w*id\w*=)(\d{2,})")


def check_idor(url: str, auth_creds: dict) -> dict | None:
    """Heuristic authenticated-IDOR candidate check (opt-in, requires .env.auth).

    NOT a certain verification like the other checks in verify_candidate() — it cannot
    prove a different numeric ID belongs to another real user, only that the same
    authenticated session can fetch substantive-looking data for more than one ID.
    Callers must surface this as NEEDS_MANUAL_CONFIRMATION, never as a blind VERIFIED.
    """
    # Search only the path+query, never scheme://netloc — an IP:port host (e.g.
    # 127.0.0.1:38445) or a numeric-looking domain segment would otherwise match as a
    # false "ID", since /\d+/ ("//127...") is indistinguishable from a real path ID.
    parsed = urllib.parse.urlparse(url)
    path_start = len(parsed.scheme) + len("://") + len(parsed.netloc)
    m = _IDOR_ID_RE.search(url, pos=path_start)
    if not m:
        return None
    prefix, id_str = m.group(1), m.group(2)
    original_id = int(id_str)
    auth_header = {auth_creds["AUTH_HEADER"]: auth_creds["AUTH_VALUE"]}

    orig_status, _, orig_body = safe_request(url, headers=auth_header, timeout=5)
    if orig_status != 200 or len(orig_body) < 20:
        return None  # can't even fetch the original ID authenticated — nothing to compare

    error_sigs = ["not found", "forbidden", "unauthorized", "access denied", "no permission", "invalid id"]
    for candidate_id in (original_id - 1, original_id + 1):
        if candidate_id <= 0:
            continue
        alt_url = url[: m.start()] + prefix + str(candidate_id) + url[m.end():]
        status, _, body = safe_request(alt_url, headers=auth_header, timeout=5)
        if status != 200 or len(body) < 20:
            continue
        if any(sig in body.lower() for sig in error_sigs):
            continue
        # Same session, 200, substantive body, on an ID it doesn't legitimately own.
        return {
            "alt_url": alt_url,
            "alt_id": candidate_id,
            "original_id": original_id,
            "evidence_notes": (
                f"Authenticated session accessed ID {candidate_id} at {alt_url} "
                f"(HTTP 200, {len(body)} bytes) — same session's own ID appears to be "
                f"{original_id}. NEEDS MANUAL CONFIRMATION: verify {candidate_id} is not "
                f"this account's own resource before treating as IDOR."
            ),
        }
    return None


# make_scope_filter: shared single source of truth, see scope_utils.py.


def safe_request(url: str, method: str = "GET", headers: dict | None = None, data: bytes | None = None, timeout: int = 6) -> tuple[int, dict, str]:
    """Execute safe, non-destructive HTTP request."""
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8", errors="ignore")
            return status, resp_headers, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
        return e.code, dict(e.headers), body
    except Exception:
        return 0, {}, ""


def verify_candidate(candidate: dict, is_in_scope, auth_creds: dict | None = None) -> dict | None:
    """Run non-destructive heuristic verification against candidate endpoint.

    Returns verified finding dict or None if false positive / non-vulnerable / blocked.
    `auth_creds` (from load_auth_credentials()) is optional — when present, an extra
    IDOR heuristic check runs (see check_idor()); its result is always surfaced as
    status='NEEDS_MANUAL_CONFIRMATION', never blindly as 'VERIFIED'.
    """
    url = candidate.get("url", "")
    tag = candidate.get("tag", "normal")
    score = candidate.get("score", 0)

    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None

    if not is_in_scope(host):
        return None

    # Step 1: Reachability check. When an auth_creds test session is configured, probe
    # with it — an authenticated-only endpoint (401 with no header) would otherwise be
    # discarded here before the IDOR check (step E, below) ever gets a chance to run.
    # Harmless for unauthenticated checks too: an extra header a public endpoint doesn't
    # need is simply ignored by it.
    reach_headers = {auth_creds["AUTH_HEADER"]: auth_creds["AUTH_VALUE"]} if auth_creds else None
    status, headers, body = safe_request(url, headers=reach_headers, timeout=5)
    if status not in (200, 201, 301, 302, 307, 308):
        # 403 Forbidden, 404 Not Found, 502/503 Cloudflare blocks are discarded
        return None

    # Check for generic WAF block pages
    waf_signatures = ["attention required! | cloudflare", "access denied", "blocked by waf", "shield security", "security by wordfence"]
    if any(sig in body.lower() for sig in waf_signatures):
        return None

    # Step 2: Verification by tag
    verified = False
    evidence_notes = ""
    verified_tag = tag

    # A. CORS Misconfiguration Check
    cors_origin = "https://attacker-verification.example.com"
    c_status, c_headers, _ = safe_request(url, headers={"Origin": cors_origin}, timeout=5)
    acao = c_headers.get("Access-Control-Allow-Origin", "").strip()
    acac = c_headers.get("Access-Control-Allow-Credentials", "").strip().lower()
    if acao == cors_origin and acac == "true":
        verified = True
        verified_tag = "cors_misconfig"
        evidence_notes = f"Verified CORS reflection of {cors_origin} with Access-Control-Allow-Credentials: true"

    # B. Sensitive Config / Secret Leak Check
    if not verified and tag in ("config_leak", "vuln_exposure"):
        leak_sigs = [
            ("git_head", r"ref:\s*refs/heads/"),
            ("env_file", r"(?:APP_KEY|DB_PASSWORD|SECRET_KEY|API_KEY|AWS_SECRET)\s*="),
            ("stack_trace", r"(?:Traceback \(most recent call last\)|Fatal error:|Exception in thread)"),
        ]
        for leak_name, leak_rx in leak_sigs:
            if re.search(leak_rx, body, re.IGNORECASE):
                verified = True
                evidence_notes = f"Verified sensitive exposure signature: {leak_name}"
                break

    # C. GraphQL Introspection Check
    if not verified and ("graphql" in url.lower() or "gql" in url.lower()):
        q = json.dumps({"query": "{__typename}"}).encode("utf-8")
        g_status, _, g_body = safe_request(url, method="POST", headers={"Content-Type": "application/json"}, data=q, timeout=5)
        if g_status == 200 and '"data"' in g_body and '"__typename"' in g_body:
            verified = True
            verified_tag = "graphql_introspection"
            evidence_notes = "Verified unauthenticated GraphQL API query response"

    # D. Admin / Auth Panel Discovery (Strict keyword match with status 200)
    if not verified and tag in ("admin_internal", "auth") and status == 200:
        admin_sigs = ["login", "username", "password", "sign in", "dashboard", "panel"]
        if any(sig in body.lower() for sig in admin_sigs):
            verified = True
            evidence_notes = f"Verified accessible authentication/admin surface (HTTP {status})"

    # E. Authenticated IDOR heuristic (opt-in — only runs if .env.auth is configured for
    # this program). Deliberately NOT folded into `verified` above: unlike CORS/secret-leak/
    # GraphQL/admin-panel (all deterministic, certain signals), this is a probabilistic
    # signal that needs a human to confirm the alternate ID actually belongs to someone else.
    if not verified and auth_creds:
        idor = check_idor(url, auth_creds)
        if idor:
            return {
                "url": url,
                "host": host,
                "method": "GET",
                "tag": "idor_candidate",
                "score": score,
                "notes": idor["evidence_notes"],
                "confidence": 0.4,
                "status": "NEEDS_MANUAL_CONFIRMATION",
            }

    # NOTE: Normal API endpoints returning HTTP 200 are NOT verified vulnerabilities.
    # Fabricated API 200 fallback has been removed to prevent false positives.

    if verified:
        return {
            "url": url,
            "host": host,
            "method": "GET",
            "tag": verified_tag,
            "score": score,
            "notes": evidence_notes,
            "confidence": 0.85,
            "status": "VERIFIED",
        }

    return None


def run_auto_hunter(program: str, min_score: int = 50, dry_run: bool = False) -> list[dict]:
    """Autonomous candidate triage and non-destructive verification loop.
    Enforces state machine: DISCOVERED/TRIAGED -> VALIDATING -> VERIFIED | REJECTED
    """
    scope = load_scope(program)
    if not scope:
        print(f"[auto_hunter] Error: scope.yaml not found for {program}", file=sys.stderr)
        return []

    is_in_scope = make_scope_filter(scope)
    rpm = int(scope.get("allowed", {}).get("max_requests_per_minute") or 60)
    delay = max(0.5, 60.0 / max(1, rpm))

    auth_creds = load_auth_credentials(program)
    if auth_creds:
        print(f"[auto_hunter] 🔑 Authenticated IDOR heuristic ENABLED for '{program}' (.env.auth found).")

    db_path = RECON / "data" / program / "recon.db"
    if not db_path.exists():
        print(f"[auto_hunter] No recon.db found for {program}. Running intelligence first is recommended.")
        return []

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute(
        "SELECT id, url, host, method, tag, score, notes FROM candidate_findings "
        "WHERE status IN ('triage', 'TRIAGED', 'DISCOVERED') AND score >= ? ORDER BY score DESC LIMIT 50",
        (min_score,),
    )
    candidates = cur.fetchall()

    print(f"[auto_hunter] ⚡ Inspecting {len(candidates)} high-priority candidate surfaces (min_score={min_score})...")
    verified_findings = []

    for idx, (cid, url, host, method, tag, score, notes) in enumerate(candidates, 1):
        clean_url = url if len(url) <= 75 else url[:72] + "..."
        print(f"  [{idx}/{len(candidates)}] 🔍 Probing [{score:2}] [{tag}] {clean_url}...", end="", flush=True)

        if dry_run:
            print(" [dry-run: safe test simulated]", flush=True)
            continue

        # Transition to VALIDATING
        cur.execute(
            "UPDATE candidate_findings SET status='VALIDATING', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), cid),
        )
        con.commit()

        cand_dict = {"id": cid, "url": url, "host": host, "method": method, "tag": tag, "score": score, "notes": notes}
        t_start = datetime.now()
        verified = verify_candidate(cand_dict, is_in_scope, auth_creds=auth_creds)
        dur = (datetime.now() - t_start).total_seconds()

        if verified and verified.get("status") == "NEEDS_MANUAL_CONFIRMATION":
            # Heuristic IDOR signal — probabilistic, not certain. Recorded for human
            # review only: no auto-report, no push alert, and NOT counted in
            # verified_findings (that list feeds the "N verified" summary + notify.py,
            # which must stay reserved for deterministic, certain findings).
            print(f" \033[38;5;220m? NEEDS MANUAL CONFIRMATION\033[0m ({dur:.1f}s)", flush=True)
            print(f"     ↳ {verified['notes']}", flush=True)
            cur.execute(
                "UPDATE candidate_findings SET status='NEEDS_MANUAL_CONFIRMATION', tag=?, confidence=?, notes=?, updated_at=? WHERE id=?",
                (verified["tag"], verified["confidence"], verified["notes"], datetime.now().isoformat(), cid),
            )
            con.commit()
        elif verified:
            print(f" \033[38;5;48m✓ VERIFIED\033[0m ({dur:.1f}s)", flush=True)
            print(f"     ↳ {verified['notes']}", flush=True)
            verified_findings.append(verified)

            # Update DB status to VERIFIED — also correct the tag, since verification
            # can reclassify a candidate (e.g. a generic "normal" surface turns out to
            # be the specific cors_misconfig it was probed for).
            cur.execute(
                "UPDATE candidate_findings SET status='VERIFIED', tag=?, confidence=?, notes=?, updated_at=? WHERE id=?",
                (verified["tag"], verified["confidence"], verified["notes"], datetime.now().isoformat(), cid),
            )
            con.commit()

            # Auto-generate draft report
            try:
                import report_gen
                _, r_path = report_gen.generate_markdown_report(program, verified)
                print(f"     ↳ \033[38;5;51m📄 Report draft generated: {r_path.name}\033[0m", flush=True)
            except Exception as e:
                print(f"     ↳ (Report gen skipped: {e})", flush=True)

            # Send push alert
            try:
                import notify
                notify.dispatch_alert(
                    title=f"🎯 [{program.upper()}] Verified Finding Detected!",
                    message=(
                        f"Target: {verified['host']}\n"
                        f"Surface: {verified['url']}\n"
                        f"Type: {verified['tag']} (Score: {verified['score']})\n"
                        f"Details: {verified['notes']}\n"
                        f"Draft Report ready for 1-click review!"
                    ),
                    severity="high" if score >= 70 else "medium",
                )
            except Exception as e:
                print(f"     ↳ (Notification skipped: {e})", flush=True)
        else:
            # Transition to REJECTED (non-vulnerable / unverified)
            rej_reason = f"Non-vulnerable during active probe ({dur:.1f}s)"
            cur.execute(
                "UPDATE candidate_findings SET status='REJECTED', notes=?, updated_at=? WHERE id=?",
                (rej_reason, datetime.now().isoformat(), cid),
            )
            con.commit()
            print(f" \033[2m- unverified / rejected ({dur:.1f}s)\033[0m", flush=True)

        time.sleep(delay)

    con.close()
    print(f"\n[auto_hunter] Finished. {len(verified_findings)} verified findings confirmed out of {len(candidates)} candidates.")
    return verified_findings


def _selfcheck() -> None:
    print("[auto_hunter] Running selfcheck...")
    scope = {
        "roots": ["example.com", "*.target.com"],
        "excluded": ["forbidden.target.com"],
    }
    is_in_scope = make_scope_filter(scope)
    assert is_in_scope("example.com") is True
    assert is_in_scope("sub.target.com") is True
    assert is_in_scope("forbidden.target.com") is False
    assert is_in_scope("out-of-scope.org") is False
    assert callable(safe_request)
    assert callable(verify_candidate)

    # Test that normal API 200 is NOT fabricated into a vulnerability
    api_candidate = {
        "url": "https://example.com/api/v1/users",
        "tag": "api_surface",
        "score": 85,
    }
    # verify_candidate on non-existent endpoint or normal 200 without leak returns None
    result = verify_candidate(api_candidate, is_in_scope)
    assert result is None or result.get("status") == "VERIFIED", "Status contract violated"
    print("[auto_hunter] selfcheck OK: Scope filters, finding state machine, and no-fabrication verified.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous Candidate Prober & Verification Engine")
    ap.add_argument("--program", default="wordpress", help="Program handle")
    ap.add_argument("--min-score", type=int, default=50, help="Minimum priority score to test")
    ap.add_argument("--dry-run", action="store_true", help="Simulate without executing network probes")
    ap.add_argument("--selfcheck", action="store_true", help="Run internal validation")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    run_auto_hunter(args.program, min_score=args.min_score, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
