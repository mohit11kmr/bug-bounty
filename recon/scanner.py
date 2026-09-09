#!/usr/bin/env python3
"""
scanner.py — Guide Phase 3: Safe Scanning (scope-aware, rate-limited).

Design contract (guide §9 / §14 + WS1 safety rules):
  1. Host allowlist = verified assets from assets.json (or scope.yaml in-scope roots)
  2. Rate limits from scope.yaml (rpm, concurrency) — enforced via CLI flags
  3. Destructive/active-only template categories excluded (dos, rce-destructive,
     takeover probes that write state, etc.)
  4. Output -> evidence/scans/<program>/ (timestamped), parsed into
     candidate_findings notes for triage
  5. --dry-run (default OFF, but recommended first) prints exact commands
  6. Writes validated targets to recon/data/<program>/raw/scanner-targets.txt

Usage:
  python3 recon/scanner.py --program meesho --dry-run
  python3 recon/scanner.py --program meesho --ffuf-host superstoreapp.meesho.com --ffuf-wordlist /path/to/wordlist
  python3 recon/scanner.py --selfcheck
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse
import uuid
from datetime import date, datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent          # bug-bounty/
RECON = BASE / "recon"
EVIDENCE = BASE / "evidence" / "scans"
sys.path.insert(0, str(RECON))
from scope_utils import load_scope_file, make_scope_filter  # noqa: E402

DEFAULT_EXCLUDE_TAGS = "dos,fuzz,brute-force,crlf,injection,rce,kev"  # "safe scanning" first pass
DEFAULT_INCLUDE_TAGS = os.environ.get("NUCLEI_INCLUDE_TAGS", "exposure,config,misconfig,tech,cve,default-login")  # high-value, low-noise
NUCLEI_SEVERITY = os.environ.get("NUCLEI_SEVERITY", "low,medium,high,critical")
NUCLEI_MAX_TIME = int(os.environ.get("NUCLEI_MAX_TIME", "900"))  # 15 min cap — full coverage per host at safe RPS (0 = no cap)
# Per-request timeout & max-host-error (nuclei default 30!): a genuinely large/wildcard scope
# (e.g. hundreds of hosts, some slow/WAF-blocking) can otherwise spend hours retrying dead hosts
# 30 times each before giving up — real, observed behavior, not theoretical. Configurable via env
# the same way the other NUCLEI_* knobs are, for anyone with a different tolerance.
NUCLEI_TIMEOUT = int(os.environ.get("NUCLEI_TIMEOUT", "5"))
NUCLEI_MAX_HOST_ERROR = int(os.environ.get("NUCLEI_MAX_HOST_ERROR", "3"))
DEFAULT_RUN_ON = "live"  # "live" = 200/30x hosts only, "all" = har asset, "list:x,y" = explicit


def load_scope(program: str) -> dict:
    scope_file = BASE / program / "scope.yaml"
    return load_scope_file(scope_file, required=True,
                            not_found_msg=f"[scanner] scope.yaml nahi mila: {scope_file}")


# make_scope_filter: shared single source of truth, see scope_utils.py.


def collect_scan_targets(program: str, scope: dict) -> list[str]:
    """Collect validated live targets from recon/data/<program>/assets.json.
    Falls back to non-wildcard scope roots if assets.json is unavailable or empty.
    Writes validated targets to recon/data/<program>/raw/scanner-targets.txt.
    """
    is_in_scope = make_scope_filter(scope)
    data_dir = RECON / "data" / program
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    targets = set()

    # 1. Ingest from assets.json if available
    assets_file = data_dir / "assets.json"
    if assets_file.exists():
        try:
            records = json.loads(assets_file.read_text(encoding="utf-8"))
            for r in records:
                h = r.get("host") or ""
                u = r.get("url") or ""
                if not h and u:
                    try:
                        h = urllib.parse.urlparse(u).netloc.split(":")[0]
                    except Exception:
                        h = ""
                h = h.strip().lower().rstrip(".")
                if h and "*" not in h and is_in_scope(h):
                    targets.add(h)
        except Exception as e:
            print(f"[scanner] Warning: could not parse {assets_file}: {e}", file=sys.stderr)

    # 2. Fallback to scope roots (expanding wildcards to clean base domain)
    if not targets:
        for r in scope.get("roots", []):
            h = str(r).replace("https://", "").replace("http://", "").rstrip("/")
            h = h.lstrip("*.").strip().lower().rstrip(".")
            if h and "*" not in h and is_in_scope(h):
                targets.add(h)

    validated = sorted(targets)
    target_file = raw_dir / "scanner-targets.txt"
    target_file.write_text("\n".join(validated) + ("\n" if validated else ""), encoding="utf-8")
    return validated


def in_scope_hosts(scope: dict) -> list[str]:
    """Legacy helper maintained for compatibility."""
    hosts = []
    for r in scope.get("roots", []):
        h = str(r).replace("https://", "").replace("http://", "").rstrip("/")
        h = h.lstrip("*.").strip().lower().rstrip(".")
        if h and h not in hosts:
            hosts.append(h)
    return sorted(hosts)


def rate_limits(scope: dict) -> tuple[int, int]:
    allowed = scope.get("allowed", {})
    rl = scope.get("rate_limits", {})
    rpm = int(allowed.get("max_requests_per_minute") or rl.get("rpm", 60))
    concurrency = int(allowed.get("max_concurrency") or rl.get("concurrency", 5))
    return rpm, concurrency


def scan_dir(program: str) -> Path:
    d = EVIDENCE / program
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(cmd: list[str], dry: bool, show_stats: bool = False) -> subprocess.CompletedProcess | None:
    """Run command; prints tail of output. show_stats=True -> keep last ~4 stats lines."""
    print(f"[scanner] $ {' '.join(cmd)}")
    if dry:
        return None
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in (0, 1):
        print(f"[scanner] ! exit={r.returncode}: {r.stderr[-400:]}")
    out = r.stdout.strip()
    if out:
        tail = "\n".join(out.splitlines()[-12:]) if show_stats else out[-1000:]
        print(tail[-1500:])
    return r


def nuclei_scan(program: str, scope: dict, targets: list[str], dry: bool,
                run_on: str = "live") -> Path | None:
    """Scoped nuclei run. Targets = in-scope hosts (default: verified live only).

    Per-host sequential runs (har host ko apna max-time/coverage), merged jsonl —
    batching ki wajah se max-time per-scan early-expire na ho.
    """
    if not targets:
        print(f"[scanner] ⚠ No valid in-scope targets for {program}. Skipping Nuclei scan.")
        return None

    rpm, concurrency = rate_limits(scope)
    if run_on == "live":
        d = scan_dir(program)
        tgt_file = d / f"targets_{program}.txt"
        probe_in = "\n".join(sorted(set(targets))) + "\n"
        tgt_file.write_text(probe_in)
        probe = d / f"httpx_probe_{program}.txt"
        run(["httpx", "-l", str(tgt_file), "-silent", "-mc", "200,201,202,203,204,301,302,303,307,308",
             "-o", str(probe)], dry)
        if probe.exists() and not dry:
            live = [l.strip() for l in probe.read_text().splitlines() if l.strip()]
            print(f"[scanner] live hosts: {len(live)} {live}")
            targets = live or targets  # fallback: koi live nahi to all targets
    elif run_on.startswith("list:"):
        targets = [t for t in run_on[5:].split(",") if t in targets]

    if not targets:
        print(f"[scanner] ⚠ No responding targets for Nuclei on {program}.")
        return None

    print(f"[scanner] nuclei targets: {len(targets)}")
    d = scan_dir(program)
    stamp = date.today().isoformat()
    out_jsonl = d / f"nuclei_{program}_{stamp}.jsonl"
    if out_jsonl.exists():
        out_jsonl.unlink()
    base = [
        "nuclei",
        "-jsonl",
        "-severity", NUCLEI_SEVERITY,
        "-exclude-tags", DEFAULT_EXCLUDE_TAGS,
        "-tags", DEFAULT_INCLUDE_TAGS,
        "-max-time", str(NUCLEI_MAX_TIME),
        "-rate-limit", str(max(1, rpm // 2)),   # safe: half the documented rpm
        "-c", str(concurrency),
        "-timeout", str(NUCLEI_TIMEOUT),
        "-max-host-error", str(NUCLEI_MAX_HOST_ERROR),
        "-nc",
    ]
    for idx, t in enumerate(targets, 1):
        if "://" in t:
            host = t.split("://", 1)[1].split("/", 1)[0]
        else:
            host = t
        host_safe = host.replace('.', '_').replace(':', '_')
        host_file = d / f"host_{host_safe}.txt"
        host_file.write_text(host + "\n")
        host_out = d / f"nuclei_{program}_{host_safe}_{stamp}.jsonl"
        if host_out.exists():
            host_out.unlink()
        cmd = base + ["-l", str(host_file), "-o", str(host_out)]
        print(f"[scanner] [{idx}/{len(targets)}] 🔍 Nuclei scanning host '{host}'...", flush=True)
        if dry:
            print(f"  $ {' '.join(cmd)}")
            continue

        t_start = datetime.now()
        host_hits = 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in proc.stdout:
            try:
                rec = json.loads(line)
                sev = rec.get("info", {}).get("severity", "info").upper()
                name = rec.get("info", {}).get("name", "")
                tid = rec.get("template-id", "")
                m_url = rec.get("matched-at") or rec.get("url", host)
                host_hits += 1
                print(f"  [nuclei] 🎯 [{sev}] {tid}: {name} -> {m_url}", flush=True)
            except Exception:
                pass
        proc.wait()
        dur = (datetime.now() - t_start).total_seconds()
        if host_out.exists():
            content = host_out.read_text()
            lines = [l for l in content.splitlines() if l.strip()]
            host_hits = max(host_hits, len(lines))
            if content.strip():
                with open(out_jsonl, "a") as merged:
                    merged.write(content if content.endswith("\n") else content + "\n")
            host_out.unlink(missing_ok=True)
        print(f"  [scanner] ✓ Host '{host}' finished in {dur:.1f}s ({host_hits} findings).", flush=True)

    if not dry and out_jsonl.exists():
        n = len(out_jsonl.read_text().splitlines())
        print(f"[scanner] nuclei findings: {n} -> {out_jsonl.relative_to(BASE)}")
        return out_jsonl
    return None


def import_nuclei_findings(out_jsonl: Path, program: str) -> None:
    """Parse nuclei JSONL -> update candidate_findings (notes + confidence), no new assets.
    Tag map from nuclei info.tags -> our candidate tag; score derives from severity."""
    db = RECON / "data" / program / "recon.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS candidate_findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT, host TEXT, method TEXT,
        tag TEXT, score INTEGER, status TEXT DEFAULT 'TRIAGED',
        confidence REAL DEFAULT 0.0,
        tool TEXT DEFAULT 'nuclei',
        run_id TEXT DEFAULT 'legacy',
        notes TEXT DEFAULT '',
        created_at TEXT, updated_at TEXT,
        UNIQUE(url, tag));""")
    cols = [c[1] for c in cur.execute("PRAGMA table_info(candidate_findings)").fetchall()]
    if "tool" not in cols:
        cur.execute("ALTER TABLE candidate_findings ADD COLUMN tool TEXT DEFAULT 'heuristic'")
    if "run_id" not in cols:
        cur.execute("ALTER TABLE candidate_findings ADD COLUMN run_id TEXT DEFAULT 'legacy'")
    # This scan invocation's own id — stamps every candidate_findings row this pass touches.
    scan_run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    tag_map = {
        "cve": "vuln_cve", "misconfiguration": "vuln_misconfig",
        "exposure": "vuln_exposure", "tech": "tech_probe",
        "default-login": "vuln_default_login", "vulnerability": "vuln",
    }
    sev_score = {"critical": 100, "high": 90, "medium": 70, "low": 50, "info": 40}
    inserted = 0
    for line in out_jsonl.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = rec.get("url", "")
        host = rec.get("host", "")
        info = rec.get("info", {})
        title = info.get("name", "") or ""
        sev = info.get("severity", "").lower()
        tags = (info.get("tags") or [])
        tag = next((t for k, t in tag_map.items() if k in tags), "vuln")
        score = sev_score.get(sev, 50)
        notes = f"nuclei: {title} ({sev})"
        conf = {"critical": 0.9, "high": 0.8, "medium": 0.65, "low": 0.5}.get(sev, 0.4)
        cur.execute(
            "INSERT INTO candidate_findings (url,host,method,tag,score,status,confidence,tool,run_id,created_at,updated_at,notes) "
            "VALUES (?,?,?,?,?,'TRIAGED',?,'nuclei',?,?,?,?) "
            "ON CONFLICT(url, tag) DO UPDATE SET "
            "score=MAX(score, excluded.score), confidence=MAX(confidence, excluded.confidence), "
            "tool='nuclei', run_id=excluded.run_id, "
            "notes=CASE WHEN notes='' THEN ? ELSE notes || ' | ' || ? END, updated_at=excluded.updated_at",
            (url, host, "GET", tag, score, conf, scan_run_id, date.today().isoformat(),
             date.today().isoformat(), notes, notes, notes))
        inserted += 1
    con.commit()
    con.close()
    print(f"[scanner] candidate_findings updated: {inserted} nuclei hits")


def ffuf_check(program: str, scope: dict, host: str, wordlist: str, dry: bool) -> None:
    """Content discovery on ONE in-scope host (ffuf). Requires wordlist path."""
    rpm, concurrency = rate_limits(scope)
    d = scan_dir(program)
    stamp = date.today().isoformat()
    clean_host = host.replace("http://", "").replace("https://", "").rstrip("/")
    scheme = "http" if host.startswith("http://") else "https"
    out = d / f"ffuf_{clean_host.replace('.', '_')}_{stamp}.json"
    cmd = [
        "ffuf",
        "-u", f"{scheme}://{clean_host}/FUZZ",
        "-w", wordlist,
        "-o", str(out),
        "-of", "json",
        "-mc", "200,201,202,203,204,301,302,307,308,401,403",
        "-rate", str(max(1, rpm // 4)),
        "-p", "0.1",
        "-t", str(concurrency),
    ]
    print(f"[scanner] ffuf host={clean_host} wordlist={Path(wordlist).name}")
    run(cmd, dry)
    if not dry and out.exists():
        print(f"[scanner] ffuf output -> {out.relative_to(BASE)}")


# =============================================================================
# WordPress-specific scanning (wpscan) — IF/ELIF auto-trigger, added per
# docs/FUTURE_FEATURES.md #2. Fires automatically when recon's own httpx
# -tech-detect already tagged a host as WordPress (assets.json's `technologies`
# field) — no new discovery step, just reusing data already collected. Needs a
# free WPSCAN_API_TOKEN (wpscan.com/register) for real vulnerability-database
# lookups; gracefully skips (does not crash the scan) if that's not configured.
# =============================================================================
WPSCAN_TIMEOUT = int(os.environ.get("WPSCAN_TIMEOUT", "120"))       # seconds, per host
WPSCAN_MAX_HOSTS = int(os.environ.get("WPSCAN_MAX_HOSTS", "5"))     # cap per run — avoid an unbounded multi-hour surprise


def load_wpscan_env() -> None:
    """Load WPSCAN_API_TOKEN from .env.wpscan (or .env.h1, as a shared-credentials
    fallback) if it isn't already in the environment. Mirrors notify.py's
    load_notify_env() — self-contained, so scanner.py works standalone (not just
    when launched via start-bugbounty.sh, which also sources these at startup)."""
    if os.environ.get("WPSCAN_API_TOKEN", "").strip():
        return
    for env_path in (BASE / ".env.wpscan", BASE / ".env.h1"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().replace("export ", "").strip()
            v = v.strip().strip('"').strip("'")
            if k == "WPSCAN_API_TOKEN" and v:
                os.environ[k] = v
                return


def detect_wordpress_hosts(program: str) -> list[str]:
    """The 'IF' condition: any asset whose httpx tech-detect tagged it as WordPress.
    Pure read of already-collected recon.data/<program>/assets.json — no network call."""
    assets_file = RECON / "data" / program / "assets.json"
    if not assets_file.exists():
        return []
    try:
        assets = json.loads(assets_file.read_text())
    except Exception:
        return []
    hosts = set()
    for a in assets:
        techs = a.get("technologies") or []
        if any("wordpress" in str(t).lower() for t in techs):
            host = a.get("host") or ""
            if host:
                hosts.add(host)
    return sorted(hosts)


def wpscan_check(program: str, host: str, dry: bool) -> Path | None:
    """Run wpscan (plugin/theme/timthumb vulnerability enumeration, no brute force)
    against one WordPress-tagged host. Returns the output file path, or None if
    skipped/dry-run/failed."""
    if not os.environ.get("WPSCAN_API_TOKEN", "").strip():
        print(f"[scanner] ⚠ wpscan: WPSCAN_API_TOKEN not set — skipping '{host}' "
              f"(free token: https://wpscan.com/register — set it up via the launcher's "
              f"Main Menu → [W] WPScan API Token, or manually in {BASE / '.env.wpscan'})")
        return None

    stamp = date.today().isoformat()
    host_safe = host.replace(":", "_").replace("/", "_").replace(".", "_")
    scan_dir(program)  # ensure evidence/scans/<program>/ exists
    # Relative to BASE, not absolute: the `wpscan` wrapper mounts $PWD as /wpscan
    # inside its Docker container, so an absolute host path is invisible to it —
    # we run this subprocess with cwd=BASE (below) so this path resolves inside.
    rel_out = Path("evidence") / "scans" / program / f"wpscan_{host_safe}_{stamp}.json"
    url = host if host.startswith("http") else f"https://{host}"
    cmd = [
        "wpscan", "--url", url,
        "--enumerate", "vp,vt,tt",   # vulnerable plugins/themes + timthumbs only — no brute force
        "--random-user-agent",
        "--request-timeout", "10",
        "-f", "json", "-o", str(rel_out),
    ]
    print(f"[scanner] $ {' '.join(cmd)}  (cwd={BASE})")
    if dry:
        return None
    try:
        r = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=WPSCAN_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[scanner] ! wpscan timed out on '{host}' after {WPSCAN_TIMEOUT}s")
        return None
    if r.returncode not in (0, 4, 5):
        print(f"[scanner] ! wpscan exit={r.returncode}: {r.stderr[-300:]}")
    out_path = BASE / rel_out
    return out_path if out_path.exists() else None


def import_wpscan_findings(out_json: Path, program: str) -> int:
    """Parse wpscan JSON -> candidate_findings, same provenance model as
    import_nuclei_findings (tool='wpscan', its own run_id). A plain 'scan_aborted'
    (e.g. missing API token) inserts nothing — never fabricate a finding."""
    try:
        data = json.loads(out_json.read_text())
    except Exception as e:
        print(f"[scanner] ! could not parse {out_json.name}: {e}")
        return 0

    if data.get("scan_aborted"):
        print(f"[scanner] wpscan aborted for {data.get('target_url', '?')}: {data['scan_aborted']}")
        return 0

    target_url = data.get("target_url", "")
    host = urllib.parse.urlparse(target_url).netloc or target_url

    def _walk_vulns(node, context=""):
        """wpscan nests vulnerabilities differently per enumeration mode
        (core/plugins/themes) — walk generically rather than hardcode one shape."""
        found = []
        if isinstance(node, dict):
            if isinstance(node.get("vulnerabilities"), list):
                for v in node["vulnerabilities"]:
                    found.append((context, v))
            for k, v in node.items():
                found.extend(_walk_vulns(v, context or str(k)))
        elif isinstance(node, list):
            for item in node:
                found.extend(_walk_vulns(item, context))
        return found

    vulns = _walk_vulns(data)
    if not vulns:
        print(f"[scanner] wpscan: 0 known vulnerabilities found for {host}")
        return 0

    db_path = RECON / "data" / program / "recon.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS candidate_findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT, host TEXT, method TEXT,
        tag TEXT, score INTEGER, status TEXT DEFAULT 'TRIAGED',
        confidence REAL DEFAULT 0.0,
        tool TEXT DEFAULT 'wpscan',
        run_id TEXT DEFAULT 'legacy',
        notes TEXT DEFAULT '',
        created_at TEXT, updated_at TEXT,
        UNIQUE(url, tag));""")
    cols = [c[1] for c in cur.execute("PRAGMA table_info(candidate_findings)").fetchall()]
    if "run_id" not in cols:
        cur.execute("ALTER TABLE candidate_findings ADD COLUMN run_id TEXT DEFAULT 'legacy'")
    if "tool" not in cols:
        cur.execute("ALTER TABLE candidate_findings ADD COLUMN tool TEXT DEFAULT 'heuristic'")

    scan_run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    now = date.today().isoformat()
    inserted = 0
    for context, v in vulns:
        title = v.get("title", "unknown") if isinstance(v, dict) else str(v)
        tag = f"vuln_wpscan_{context or 'core'}"[:60]
        notes = f"wpscan: {title}"
        cur.execute(
            "INSERT INTO candidate_findings (url,host,method,tag,score,status,confidence,tool,run_id,created_at,updated_at,notes) "
            "VALUES (?,?,?,?,?,'TRIAGED',?,'wpscan',?,?,?,?) "
            "ON CONFLICT(url, tag) DO UPDATE SET run_id=excluded.run_id, updated_at=excluded.updated_at",
            (target_url, host, "GET", tag, 70, 0.6, scan_run_id, now, now, notes),
        )
        inserted += 1
    con.commit()
    con.close()
    print(f"[scanner] wpscan: {inserted} known-vulnerability hit(s) for {host} -> candidate_findings")
    return inserted


def _selfcheck() -> None:
    print("[scanner] Running selfcheck...")
    mock_scope = {
        "roots": ["*.example.com", "target.org"],
        "excluded": ["excluded.example.com"],
        "rate_limits": {"rpm": 120, "concurrency": 8}
    }
    filt = make_scope_filter(mock_scope)
    assert filt("test.example.com") is True
    assert filt("example.com") is True
    assert filt("target.org") is True
    assert filt("excluded.example.com") is False
    assert filt("external.net") is False

    rpm, conc = rate_limits(mock_scope)
    assert rpm == 120
    assert conc == 8

    # Target expansion test
    hosts = in_scope_hosts(mock_scope)
    assert "example.com" in hosts
    assert "target.org" in hosts
    print("[scanner] selfcheck OK: Scope filter, rate limits and target extraction verified.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", help="program folder name (e.g. meesho, kayak, general)")
    ap.add_argument("--dry-run", action="store_true", help="commands dikhao, chalao nahi")
    ap.add_argument("--run-on", default=DEFAULT_RUN_ON,
                    help="live|all|list:h1,h2 — nuclei targets kya ho")
    ap.add_argument("--no-nuclei", action="store_true")
    ap.add_argument("--no-wpscan", action="store_true",
                     help="skip the auto-triggered wpscan pass on WordPress-tagged hosts")
    ap.add_argument("--ffuf-host")
    ap.add_argument("--ffuf-wordlist")
    ap.add_argument("--selfcheck", action="store_true", help="run internal selfcheck")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    if not args.program:
        sys.exit("[scanner] Error: --program is required (unless running --selfcheck).")

    load_wpscan_env()
    scope = load_scope(args.program)
    targets = collect_scan_targets(args.program, scope)
    print(f"[scanner] program={args.program} valid in-scope targets={len(targets)}")

    if not targets:
        print(f"[scanner] Notice: No valid in-scope targets found for {args.program}. Exiting cleanly.")
        return

    if not args.no_nuclei:
        out = nuclei_scan(args.program, scope, targets, args.dry_run, args.run_on)
        if out and not args.dry_run:
            import_nuclei_findings(out, args.program)

    if not args.no_wpscan:
        wp_hosts = detect_wordpress_hosts(args.program)
        if wp_hosts:
            capped = wp_hosts[:WPSCAN_MAX_HOSTS]
            note = "" if len(wp_hosts) == len(capped) else f" (capped from {len(wp_hosts)}, set WPSCAN_MAX_HOSTS to raise)"
            print(f"[scanner] 🔍 wpscan auto-trigger: {len(capped)} WordPress-tagged host(s){note}")
            for h in capped:
                out = wpscan_check(args.program, h, args.dry_run)
                if out and not args.dry_run:
                    import_wpscan_findings(out, args.program)

    if args.ffuf_host:
        filt = make_scope_filter(scope)
        if not filt(args.ffuf_host):
            sys.exit(f"[scanner] ffuf host out-of-scope: {args.ffuf_host}")
        ffuf_check(args.program, scope, args.ffuf_host, args.ffuf_wordlist, args.dry_run)

    if args.dry_run:
        print("[scanner] dry-run khatam — kuch run nahi hua. Live ke liye --dry-run hatao saath rate-limit verify karo.")


if __name__ == "__main__":
    main()