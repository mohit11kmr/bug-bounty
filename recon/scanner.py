#!/usr/bin/env python3
"""
scanner.py — Guide Phase 3: Safe Scanning (scope-aware, rate-limited).

Design contract (guide §9 / §14 + WS1 safety rules):
  1. Host allowlist = meesho/scope.yaml in-scope roots ONLY (plus verified assets)
  2. Rate limits from scope.yaml (rpm, concurrency) — enforced via CLI flags
  3. Destructive/active-only template categories excluded (dos, rce-destructive,
     takeover probes that write state, etc.)
  4. Output -> evidence/scans/<program>/ (timestamped), parsed into
     candidate_findings notes for triage
  5. --dry-run (default OFF, but recommended first) prints exact commands

Usage:
  python3 recon/scanner.py --program meesho --dry-run
  python3 recon/scanner.py --program meesho --ffuf-host superstoreapp.meesho.com --ffuf-wordlist /path/to/wordlist
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent          # bug-bounty/
RECON = BASE / "recon"
EVIDENCE = BASE / "evidence" / "scans"

DEFAULT_EXCLUDE_TAGS = "dos,fuzz,brute-force,crlf,injection,rce,kev"  # "safe scanning" first pass
DEFAULT_INCLUDE_TAGS = "exposure,config,misconfig,tech,cve,default-login"  # high-value, low-noise
NUCLEI_SEVERITY = "low,medium,high,critical"
NUCLEI_MAX_TIME = 900  # 15 min cap — full coverage per host at safe RPS (0 = no cap)
DEFAULT_RUN_ON = "live"  # "live" = 200/30x hosts only, "all" = har asset, "list:x,y" = explicit


def load_scope(program: str) -> dict:
    scope_file = BASE / program / "scope.yaml"
    if not scope_file.exists():
        sys.exit(f"[scanner] scope.yaml nahi mila: {scope_file}")
    return yaml.safe_load(scope_file.read_text())


def in_scope_hosts(scope: dict) -> list[str]:
    """In-scope URL-roots se unique host list (scope.yaml roots only, subdomains agar
    explicit in scope: 'wildcards' ya root-prefixed yeha program me define hote hain)."""
    hosts = []
    for r in scope.get("roots", []):
        h = str(r).replace("https://", "").replace("http://", "").rstrip("/")
        if h and h not in hosts:
            hosts.append(h)
    return sorted(hosts)


def rate_limits(scope: dict) -> tuple[int, int]:
    rl = scope.get("rate_limits", {})
    rpm = int(rl.get("rpm", 60))
    concurrency = int(rl.get("concurrency", 5))
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
    rpm, concurrency = rate_limits(scope)
    if run_on == "live":
        d = scan_dir(program)
        probe = d / f"httpx_probe_{program}.txt"
        run(["httpx", "-l", str(d / f"targets_{program}.txt"), "-silent", "-mc", "200,201,202,203,204,301,302,303,307,308",
             "-o", str(probe)], dry)
        if probe.exists() and not dry:
            live = probe.read_text().splitlines()
            print(f"[scanner] live hosts: {len(live)} {live}")
            targets = live or targets  # fallback: koi live nahi to all targets
    elif run_on.startswith("list:"):
        targets = [t for t in run_on[5:].split(",") if t in targets]
    print(f"[scanner] nuclei targets: {len(targets)}")
    d = scan_dir(program)
    stamp = date.today().isoformat()
    out_jsonl = d / f"nuclei_{program}_{stamp}.jsonl"
    # remove old same-day output to avoid appends confusion
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
        "-nc",
    ]
    for t in targets:
        # t = full URL ho sakta hai (httpx probe output se); sirf host extract karo
        if "://" in t:
            host = t.split("://", 1)[1].split("/", 1)[0]
        else:
            host = t
        host_file = d / f"host_{host.replace('.', '_').replace(':', '_')}.txt"
        host_file.write_text(host + "\n")
        cmd = base + ["-l", str(host_file), "-o", str(out_jsonl)]
        print(f"[scanner] nuclei host={host}")
        run(cmd, dry, show_stats=True)
    if not dry and out_jsonl.exists():
        n = len(out_jsonl.read_text().splitlines())
        print(f"[scanner] nuclei findings: {n} -> {out_jsonl.relative_to(BASE)}")
        return out_jsonl
    return None


def import_nuclei_findings(out_jsonl: Path, program: str) -> None:
    """Parse nuclei JSONL -> update candidate_findings (notes + confidence), no new assets."""
    db = RECON / "data" / program / "recon.db"
    con = sqlite3.connect(db)
    cur = con.cursor()
    tag_map = {
        "cve": "vuln_cve", "misconfiguration": "vuln_misconfig",
        "exposure": "vuln_exposure", "tech": "tech_probe",
        "default-login": "vuln_default_login", "vulnerability": "vuln",
    }
    inserted = 0
    for line in out_jsonl.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = rec.get("url", "")
        tag_bucket = rec.get("template-id", "").split("/")[-1].split(".")[0]
        # nuclei "info" se template title
        info = rec.get("info", {})
        title = info.get("name", tag_bucket)
        sev = info.get("severity", "info")
        cur.execute(
            "INSERT OR IGNORE INTO candidate_findings (url,host,method,tag,score,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (url, "", "GET", "vuln_nuclei", 90, "triage", date.today().isoformat(),
             date.today().isoformat()))
        cur.execute(
            "UPDATE candidate_findings SET confidence = MAX(confidence, 0.6), "
            "notes = CASE WHEN notes='' THEN ? ELSE notes || ' | ' || ? END "
            "WHERE url = ? AND tag = 'vuln_nuclei'",
            (f"nuclei: {title} ({sev})", f"nuclei: {title} ({sev})", url))
        inserted += 1
    con.commit()
    con.close()
    print(f"[scanner] candidate_findings updated: {inserted} nuclei hits")


def ffuf_check(program: str, scope: dict, host: str, wordlist: str, dry: bool) -> None:
    """Content discovery on ONE in-scope host (ffuf). Requires wordlist path."""
    rpm, concurrency = rate_limits(scope)
    d = scan_dir(program)
    stamp = date.today().isoformat()
    out = d / f"ffuf_{host.replace('.', '_')}_{stamp}.json"
    cmd = [
        "ffuf",
        "-u", f"https://{host}/FUZZ",
        "-w", wordlist,
        "-o", str(out),
        "-of", "json",
        "-mc", "200,201,202,203,204,301,302,307,308,401,403",
        "-rate", str(max(1, rpm // 4)),          # wordlist scan = higher volume, keep under rpm
        "-p", "0.1",                              # ~100ms pause -> ~10 req/sec max
        "-t", str(concurrency),
    ]
    print(f"[scanner] ffuf host={host} wordlist={Path(wordlist).name}")
    run(cmd, dry)
    if not dry and out.exists():
        print(f"[scanner] ffuf output -> {out.relative_to(BASE)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True, help="program folder name (e.g. meesho, kayak, general)")
    ap.add_argument("--dry-run", action="store_true", help="commands dikhao, chalao nahi")
    ap.add_argument("--run-on", default=DEFAULT_RUN_ON,
                    help="live|all|list:h1,h2 — nuclei targets kya ho")
    ap.add_argument("--no-nuclei", action="store_true")
    ap.add_argument("--ffuf-host")
    ap.add_argument("--ffuf-wordlist")
    args = ap.parse_args()

    scope = load_scope(args.program)
    targets = in_scope_hosts(scope)
    print(f"[scanner] program={args.program} in-scope hosts={len(targets)}")

    if not args.no_nuclei:
        out = nuclei_scan(args.program, scope, targets, args.dry_run, args.run_on)
        if out and not args.dry_run:
            import_nuclei_findings(out, args.program)

    if args.ffuf_host:
        if args.ffuf_host not in targets:
            sys.exit(f"[scanner] ffuf host out-of-scope: {args.ffuf_host}")
        ffuf_check(args.program, scope, args.ffuf_host, args.ffuf_wordlist, args.dry_run)

    if args.dry_run:
        print("[scanner] dry-run khatam — kuch run nahi hua. Live ke liye --dry-run hatao saath rate-limit verify karo.")


if __name__ == "__main__":
    main()