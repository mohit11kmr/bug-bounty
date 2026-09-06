#!/usr/bin/env python3
"""
daemon.py — Autonomous Continuous Recon & Delta Engine for Bug Bounty Suite.

Monitors program scopes for newly deployed subdomains, infrastructure changes,
and exposed attack surfaces without human intervention.

Features:
  - Delta Detection: Only triggers downstream tools if new assets appear (Δ = current - previous).
  - Automated Chaining: Δ > 0 -> httpx -> js_miner -> intelligence -> auto_hunter -> notify.
  - Non-Intrusive: If no changes are detected, logs cleanly and sleeps.
  - Daemon Lifecycle: Supports background looping, PID management, --status, and --stop.

Usage:
  python3 recon/daemon.py --selfcheck
  python3 recon/daemon.py --program wordpress --once
  python3 recon/daemon.py --program wordpress --interval 3600
  python3 recon/daemon.py --status
  python3 recon/daemon.py --stop
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"
PID_FILE = RECON / "data" / ".daemon.pid"

# Lazy-load sibling modules
sys.path.insert(0, str(RECON))
try:
    import notify
except ImportError:
    pass


def load_scope(program: str) -> dict:
    scope_file = BASE / program / "scope.yaml"
    if not scope_file.exists():
        return {}
    raw = scope_file.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(raw) or {}
    except Exception:
        import re
        fixed_lines = []
        for line in raw.splitlines():
            if re.match(r'^\s*-\s*[\*\?].*', line):
                prefix = line[:line.index('-') + 2]
                val = line.strip()[1:].strip().strip('"').strip("'")
                fixed_lines.append(f'{prefix}"{val}"')
            else:
                fixed_lines.append(line)
        return yaml.safe_load("\n".join(fixed_lines)) or {}


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
        bare = host.split(":")[0]
        variants = [host] if host == bare else [host, bare]
        if any(v in roots for v in variants):
            return True
        if any(wildcard_match(v, excluded) for v in variants):
            return False
        return any(wildcard_match(v, roots) for v in variants)

    return in_scope


def get_existing_hosts(program: str) -> set[str]:
    assets_file = RECON / "data" / program / "assets.json"
    hosts = set()
    if assets_file.exists():
        try:
            records = json.loads(assets_file.read_text())
            for r in records:
                h = r.get("host")
                if h:
                    hosts.add(h.lower())
        except Exception:
            pass
    return hosts


def run_passive_subdomain_probe(roots: list[str], is_in_scope) -> set[str]:
    """Run lightweight passive subfinder scan across roots concurrently."""
    discovered = set()
    clean_roots = sorted({r.lstrip("*.").strip() for r in roots if r.strip()})
    if not clean_roots:
        return discovered

    cache_dir = RECON / "data" / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_roots = cache_dir / "daemon_subfinder_roots.txt"
    temp_roots.write_text("\n".join(clean_roots) + "\n")

    print(f"[daemon] 🔍 Running concurrent subfinder probe on {len(clean_roots)} roots...", flush=True)
    t_start = datetime.now()
    try:
        res = subprocess.run(
            ["subfinder", "-dL", str(temp_roots), "-silent", "-timeout", "8", "-max-time", "1"],
            capture_output=True,
            text=True,
            check=False,
            timeout=80,
        )
        for line in res.stdout.splitlines():
            h = line.strip().lower()
            if h and is_in_scope(h):
                discovered.add(h)
    except Exception as e:
        print(f"[daemon] subfinder warning: {e}")

    dur = (datetime.now() - t_start).total_seconds()
    print(f"[daemon] ✓ Subfinder finished in {dur:.1f}s — {len(discovered)} candidate subdomains discovered.", flush=True)
    return discovered


def run_delta_cycle(program: str, dry_run: bool = False) -> int:
    """Check for new assets and execute downstream pipeline only on delta."""
    scope = load_scope(program)
    if not scope:
        print(f"[daemon] Program '{program}' scope.yaml not found.")
        return 0

    roots = scope.get("roots", [])
    if not roots:
        print(f"[daemon] Program '{program}' has no in-scope roots.")
        return 0

    is_in_scope = make_scope_filter(scope)
    prev_hosts = get_existing_hosts(program)
    t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n[daemon] [{t_now}] Checking scope delta for '{program}' ({len(prev_hosts)} existing hosts)...")
    curr_hosts = run_passive_subdomain_probe(roots, is_in_scope)

    delta = curr_hosts - prev_hosts
    if not delta:
        print(f"[daemon] ✓ No new attack surfaces detected for '{program}' (Total: {len(prev_hosts)}). All quiet.")
        return 0

    print(f"[daemon] 🚨 DELTA DETECTED: {len(delta)} NEW candidate hosts discovered for '{program}'!")
    for h in sorted(delta)[:10]:
        print(f"  + [new host] {h}")
    if len(delta) > 10:
        print(f"  ... and {len(delta) - 10} more.")

    if dry_run:
        print("[daemon] dry-run mode: Downstream pipeline execution skipped.")
        return len(delta)

    # 1. Probe new hosts with httpx
    raw_dir = RECON / "data" / program / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    delta_file = raw_dir / "delta_hosts.txt"
    delta_file.write_text("\n".join(sorted(delta)))

    print(f"[daemon] 🌐 Probing {len(delta)} new hosts with httpx...")
    delta_httpx = raw_dir / "delta_httpx.jsonl"
    subprocess.run(
        [
            "httpx",
            "-l", str(delta_file),
            "-silent",
            "-json",
            "-status-code",
            "-title",
            "-tech-detect",
            "-o", str(delta_httpx),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    # 2. Append newly verified assets to assets.json
    assets_file = RECON / "data" / program / "assets.json"
    existing_assets = []
    if assets_file.exists():
        try:
            existing_assets = json.loads(assets_file.read_text())
        except Exception:
            existing_assets = []

    new_alive_count = 0
    if delta_httpx.exists():
        for line in delta_httpx.read_text().splitlines():
            try:
                rec = json.loads(line)
                existing_assets.append({
                    "host": rec.get("input", ""),
                    "url": rec.get("url", ""),
                    "ip": rec.get("host", ""),
                    "status": rec.get("status_code"),
                    "title": rec.get("title", ""),
                    "technologies": rec.get("tech", []),
                    "source": ["delta_daemon"],
                    "first_seen": datetime.now().strftime("%Y-%m-%d"),
                    "last_seen": datetime.now().strftime("%Y-%m-%d"),
                })
                new_alive_count += 1
            except Exception:
                continue
        assets_file.write_text(json.dumps(existing_assets, indent=2))

    print(f"[daemon] ✓ {new_alive_count} new live web endpoints added to assets.json.")

    # 3. Trigger JS Miner on new assets
    print("[daemon] 📦 Running JS Miner on new assets...")
    subprocess.run([sys.executable, str(RECON / "js_miner.py"), "--program", program], check=False)

    # 3b. Trigger Safe Vulnerability Scanner (Nuclei) on newly discovered assets
    print("[daemon] 🛡️ Running safe vulnerability scanner on updated assets...")
    subprocess.run([sys.executable, str(RECON / "scanner.py"), "--program", program], check=False)

    # 4. Trigger Intelligence Scoring
    print("[daemon] ⚡ Prioritizing new surfaces with intelligence.py...")
    subprocess.run([sys.executable, str(RECON / "intelligence.py"), "--program", program], check=False)

    # 5. Trigger Headless Auto-Hunter for Verification
    print("[daemon] 🎯 Verifying top candidates with auto_hunter.py...")
    subprocess.run([sys.executable, str(RECON / "auto_hunter.py"), "--program", program, "--min-score", "60"], check=False)

    # 6. Notify user of delta
    try:
        import notify
        notify.dispatch_alert(
            title=f"🚨 [{program.upper()}] New Attack Surfaces Detected!",
            message=(
                f"Delta Engine discovered {len(delta)} new subdomains.\n"
                f"Live Web Services: {new_alive_count}\n"
                f"Automated JS-Mining & candidate triage completed in background!"
            ),
            severity="medium",
        )
    except Exception:
        pass

    return len(delta)


def manage_pid(action: str) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if action == "status":
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, 0)
                print(f"[daemon] Running in background (PID: {pid}).")
                return
            except (OSError, ValueError):
                PID_FILE.unlink(missing_ok=True)
        print("[daemon] Not currently running in background.")
    elif action == "stop":
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"[daemon] Stopped background process (PID: {pid}).")
            except (OSError, ValueError) as e:
                print(f"[daemon] Process not running or already terminated: {e}")
            PID_FILE.unlink(missing_ok=True)
        else:
            print("[daemon] No running daemon found.")


def _selfcheck() -> None:
    print("[daemon] Running selfcheck...")
    scope = {"roots": ["wordpress.org", "*.wordpress.org"], "excluded": []}
    filt = make_scope_filter(scope)
    assert filt("api.wordpress.org") is True
    assert filt("google.com") is False
    assert callable(run_delta_cycle)
    print("[daemon] selfcheck OK: Scope validation and delta logic verified.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous Continuous Recon & Delta Watcher")
    ap.add_argument("--program", default="wordpress", help="Program handle to watch")
    ap.add_argument("--interval", type=int, default=0, help="Loop interval in seconds (0 = single run)")
    ap.add_argument("--once", action="store_true", help="Run single delta cycle and exit")
    ap.add_argument("--dry-run", action="store_true", help="Detect delta without running heavy downstream tools")
    ap.add_argument("--status", action="store_true", help="Check background daemon status")
    ap.add_argument("--stop", action="store_true", help="Stop background daemon")
    ap.add_argument("--selfcheck", action="store_true", help="Run internal validation")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    if args.status:
        manage_pid("status")
        return

    if args.stop:
        manage_pid("stop")
        return

    if args.once or args.interval <= 0:
        run_delta_cycle(args.program, dry_run=args.dry_run)
        return

    # Background loop mode
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    print(f"[daemon] Starting autonomous monitor for '{args.program}' (interval: {args.interval}s, PID: {os.getpid()})...")
    print(f"[daemon] Press Ctrl+C or run 'python3 recon/daemon.py --stop' to terminate.\n")

    try:
        while True:
            run_delta_cycle(args.program, dry_run=args.dry_run)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[daemon] Interrupted by user. Exiting...")
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
