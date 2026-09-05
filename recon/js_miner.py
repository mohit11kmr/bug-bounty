#!/usr/bin/env python3
"""
js_miner.py — Phase 1 Advanced: Deep Client-Side JS Mining & Katana Endpoint Extractor.

Design Contract:
  1. Scope-Safe: Crawls only in-scope live assets defined in scope.yaml (roots & exclusions).
  2. Rate-Limited: Enforces concurrency & RPM from scope.yaml.
  3. Katana Crawler: Runs katana with -jc (js-crawl), -jsl (jsluice), -xhr (XHR extraction).
  4. Static JS Parser: Scans JavaScript files for API routes, cloud endpoints (S3, GCS, Firebase),
     and sensitive query parameters.
  5. SQLite & JSON Sync: Merges discovered endpoints into endpoints.json and recon.db.
  6. Selfcheck: python3 recon/js_miner.py --selfcheck

Usage:
  python3 recon/js_miner.py --program meesho --dry-run
  python3 recon/js_miner.py --program meesho
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"

# Regex patterns for static JS analysis
ROUTE_PATTERNS = [
    r"""(?:"|')((?:/[a-zA-Z0-9_.\-]+)?/(?:api|v[0-9]+|graphql|admin|internal|panel|dashboard|auth|user|order|checkout|upload|download)/[a-zA-Z0-9_.\-/?=&%]+)(?:"|')""",
    r"""(?:"|')((?:https?:)?//[a-zA-Z0-9_\-.]+(?:/[a-zA-Z0-9_.\-/?=&%]+)?)(?:"|')""",
]

SENSITIVE_SECRET_PATTERNS = [
    ("google_api_key", r"AIza[0-9A-Za-z\-_]{35}"),
    ("jwt_token", r"eyJ[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_.+/=]{10,}"),
    ("s3_bucket", r'''https?://[a-zA-Z0-9_\-\.]+\.s3(?:[\.-][a-zA-Z0-9_\-\.]*)?\.amazonaws\.com/[^\s"'<>]+'''),
    ("gcs_bucket", r"https?://storage\.googleapis\.com/[a-zA-Z0-9_\-\./]+"),
    ("firebase_url", r"https?://[a-zA-Z0-9_\-\.]+\.firebaseio\.com"),
]

SAMPLE_JS_TEST = """
var config = {
    apiUrl: "/api/v2/orders/checkout?user_id=1092&token=abc",
    internalService: "https://admin.meeshosupply.com/internal/export/data",
    gcsBucket: "https://storage.googleapis.com/meesho-supply-prod/invoices/1.pdf",
    mapsKey: "AIzaSyD-dummyGoogleApiKey123456789012345"
};
fetch("/panel/v3/new/fulfillment/items?distinct_id=xyz");
"""


def _selfcheck() -> None:
    print("[js_miner] Running self-check...")
    routes, secrets = extract_from_js_content(SAMPLE_JS_TEST, "https://supplier.meesho.com")
    
    assert any("/api/v2/orders/checkout" in r for r in routes), "Route /api/v2/orders/checkout not found"
    assert any("admin.meeshosupply.com" in r for r in routes), "Internal service route not found"
    assert any("/panel/v3/new/fulfillment/items" in r for r in routes), "Panel route not found"
    
    sec_types = {s["type"] for s in secrets}
    assert "google_api_key" in sec_types, "Google API key pattern missed"
    assert "gcs_bucket" in sec_types, "GCS bucket pattern missed"
    
    print(f"[js_miner] selfcheck OK: {len(routes)} routes and {len(secrets)} secrets extracted.")


def extract_from_js_content(text: str, base_url: str = "") -> tuple[list[str], list[dict]]:
    """Extract relative/absolute endpoints and sensitive secrets from JS code string."""
    routes = set()
    secrets = []

    for pattern in ROUTE_PATTERNS:
        for match in re.finditer(pattern, text):
            raw_path = match.group(1).strip()
            if not raw_path or raw_path.startswith("//"):
                continue
            if raw_path.startswith("http://") or raw_path.startswith("https://"):
                routes.add(raw_path)
            elif base_url and raw_path.startswith("/"):
                routes.add(urljoin(base_url, raw_path))
            elif raw_path.startswith("/"):
                routes.add(raw_path)

    for sec_type, sec_regex in SENSITIVE_SECRET_PATTERNS:
        for match in re.finditer(sec_regex, text):
            val = match.group(0)
            secrets.append({"type": sec_type, "match": val, "base_url": base_url})

    return sorted(routes), secrets


def load_scope(program: str) -> dict:
    import re
    scope_file = BASE / program / "scope.yaml"
    if not scope_file.exists():
        sys.exit(f"[js_miner] ERROR: {scope_file} nahi mila — pehle scope.yaml banao")
    raw = scope_file.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(raw)
    except Exception:
        fixed_lines = []
        for line in raw.splitlines():
            if re.match(r'^\s*-\s*[\*\?].*', line):
                prefix = line[:line.index('-') + 2]
                val = line.strip()[1:].strip().strip('"').strip("'")
                fixed_lines.append(f'{prefix}"{val}"')
            else:
                fixed_lines.append(line)
        return yaml.safe_load("\n".join(fixed_lines))


def make_scope_filter(scope: dict):
    roots = [str(r).lower() for r in scope.get("roots", [])]
    excluded = [str(x).lower() for x in scope.get("excluded", [])]

    def wildcard_match(host: str, patterns: list) -> bool:
        host = host.lower().rstrip(".")
        for p in patterns:
            if p.startswith("*."):
                base = p[2:]
                if host == base or host.endswith("." + base):
                    return True
            elif p == host:
                return True
        return False

    def in_scope(host: str) -> bool:
        host = host.lower().rstrip(".")
        if host in roots:
            return True
        if wildcard_match(host, excluded):
            return False
        return wildcard_match(host, roots)

    return in_scope


def rate_limits(scope: dict) -> tuple[int, int]:
    allowed = scope.get("allowed", {})
    rl = scope.get("rate_limits", {})
    rpm = int(allowed.get("max_requests_per_minute") or rl.get("rpm", 60))
    concurrency = int(allowed.get("max_concurrency") or rl.get("concurrency", 5))
    return rpm, concurrency


def get_live_targets(program: str, scope: dict) -> list[str]:
    data_dir = RECON / "data" / program
    assets_file = data_dir / "assets.json"
    targets = set()
    is_in_scope = make_scope_filter(scope)

    if assets_file.exists():
        try:
            assets = json.loads(assets_file.read_text())
            for a in assets:
                url = a.get("url", "")
                status = a.get("status")
                host = a.get("host", "")
                # Only crawl accessible/live hosts (200, 30x, or roots)
                if url and status in (200, 201, 301, 302, 307, 308) and is_in_scope(host):
                    targets.add(url)
        except Exception:
            pass

    if not targets:
        for r in scope.get("roots", []):
            targets.add(f"https://{r}")

    return sorted(targets)


def run_katana_crawl(targets: list[str], output_jsonl: Path, rpm: int, concurrency: int, dry_run: bool) -> list[str]:
    if not targets:
        print("[js_miner] No targets to crawl.")
        return []

    targets_file = output_jsonl.parent / "katana_targets.txt"
    targets_file.write_text("\n".join(targets) + "\n")

    cmd = [
        "katana",
        "-list", str(targets_file),
        "-jc",                  # enable js-crawl
        "-jsl",                 # enable jsluice parsing in js files
        "-xhr",                 # extract xhr request url and method
        "-depth", "2",
        "-c", str(concurrency),
        "-rate-limit", str(max(1, rpm // 2)),
        "-kf", "all",
        "-j",                   # jsonl format
        "-o", str(output_jsonl),
        "-silent"
    ]

    print(f"[js_miner] $ {' '.join(cmd)}")
    if dry_run:
        print("[js_miner] dry-run mode: katana command printed above.")
        return []

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    discovered = []
    if output_jsonl.exists():
        for line in output_jsonl.read_text().splitlines():
            try:
                rec = json.loads(line)
                url = rec.get("request", {}).get("endpoint") or rec.get("url")
                if url:
                    discovered.append(url)
            except json.JSONDecodeError:
                continue
    return discovered


def merge_into_database(program: str, new_endpoints: list[str], secrets: list[dict]) -> int:
    data_dir = RECON / "data" / program
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "recon.db"
    now = date.today().isoformat()

    # 1. Update endpoints.json
    ep_file = data_dir / "endpoints.json"
    existing = []
    seen_urls = set()
    if ep_file.exists():
        try:
            existing = json.loads(ep_file.read_text())
            for e in existing:
                seen_urls.add(e.get("url"))
        except Exception:
            existing = []

    added_count = 0
    for u in new_endpoints:
        if u not in seen_urls:
            seen_urls.add(u)
            existing.append({
                "url": u,
                "method": "GET",
                "source": ["katana", "js_crawl"],
                "auth_hint": "unknown",
                "first_seen": now,
                "last_seen": now
            })
            added_count += 1

    ep_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"[js_miner] endpoints.json updated: {added_count} naye endpoints jode gaye.")

    # 2. Update recon.db if it exists
    if db_path.exists():
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        for u in new_endpoints:
            parsed = urlparse(u)
            host = parsed.netloc.split(":")[0].lower() if parsed.netloc else "?"
            cur.execute("""INSERT OR IGNORE INTO endpoints
                (url, host, method, source, auth_hint, score, tag, first_seen, last_seen)
                VALUES (?, ?, 'GET', 'katana,js_crawl', 'unknown', 50, 'api_surface', ?, ?)""",
                (u, host, now, now))
        con.commit()
        con.close()
        print(f"[js_miner] SQLite recon.db endpoints table synced.")

    # 3. Save secrets if any
    if secrets:
        sec_file = data_dir / "js_secrets.json"
        sec_file.write_text(json.dumps(secrets, indent=2))
        print(f"[js_miner] {len(secrets)} potential secrets saved -> {sec_file.name}")

    return added_count


def mine_js_urls(js_urls: list[str], is_in_scope, max_files: int = 15) -> tuple[list[str], list[dict]]:
    """Fetch discovered JS files and statically extract embedded routes and secrets."""
    import urllib.request
    discovered_routes = set()
    all_secrets = []
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    print(f"[js_miner] Inspecting up to {min(len(js_urls), max_files)} discovered JavaScript bundles...")
    
    for u in js_urls[:max_files]:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    text = resp.read().decode("utf-8", errors="ignore")
                    parsed_routes, secrets = extract_from_js_content(text, base_url=u)
                    for r in parsed_routes:
                        try:
                            h = urlparse(r).netloc.split(":")[0].lower()
                            if not h or is_in_scope(h):
                                discovered_routes.add(r)
                        except Exception:
                            continue
                    all_secrets.extend(secrets)
        except Exception:
            continue

    print(f"[js_miner] Static JS analysis extracted: {len(discovered_routes)} routes, {len(all_secrets)} potential secrets.")
    return sorted(discovered_routes), all_secrets


def main() -> None:
    ap = argparse.ArgumentParser(description="Deep JS-Mining & Katana Endpoint Extractor")
    ap.add_argument("--program", default="meesho", help="Target program folder name")
    ap.add_argument("--dry-run", action="store_true", help="Print commands without executing network calls")
    ap.add_argument("--selfcheck", action="store_true", help="Run internal self-tests and exit")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    scope = load_scope(args.program)
    is_in_scope = make_scope_filter(scope)
    rpm, concurrency = rate_limits(scope)

    data_dir = RECON / "data" / args.program
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    katana_out = raw_dir / "katana_js.jsonl"

    targets = get_live_targets(args.program, scope)
    print(f"[js_miner] Program: {args.program} | Live crawling targets: {len(targets)}")
    for t in targets:
        print(f"  - {t}")

    discovered = run_katana_crawl(targets, katana_out, rpm, concurrency, args.dry_run)

    # Filter strictly in-scope
    in_scope_discovered = set()
    js_files = []
    for u in discovered:
        try:
            h = urlparse(u).netloc.split(":")[0].lower()
            if is_in_scope(h):
                in_scope_discovered.add(u)
                if ".js" in urlparse(u).path:
                    js_files.append(u)
        except Exception:
            continue

    secrets = []
    if not args.dry_run and js_files:
        extra_routes, secrets = mine_js_urls(js_files, is_in_scope)
        in_scope_discovered.update(extra_routes)

    if not args.dry_run:
        added = merge_into_database(args.program, sorted(in_scope_discovered), secrets)
        print(f"[js_miner] Done. Total in-scope JS endpoints discovered: {len(in_scope_discovered)} ({added} new)")


if __name__ == "__main__":
    main()
