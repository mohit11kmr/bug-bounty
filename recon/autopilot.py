#!/usr/bin/env python3
"""
autopilot.py — Fully autonomous "flip it ON and walk away" hunting loop.

Manual today: pick a program yourself -> setup -> trigger a scan -> repeat.
Autopilot: turn it ON once, and it keeps going by itself —

  1. Auto-detects this PC's capability (CPU cores + RAM) and picks safe
     concurrency/rate-limit settings for it (no manual tuning).
  2. Auto-discovers a fresh, not-yet-set-up bounty program (h1_client.py,
     sorted newest-first — same "less crowded" logic as the TUI's option 4).
  3. Auto-creates its target folder + scope (h1_client.py --setup).
  4. Auto-runs the full zero-touch hunt pipeline on it
     (start-bugbounty.sh --auto <handle> --fresh).
  5. On completion, auto-picks the next fresh program and repeats.

Respects the account-server's scan-gate (trial/daily-quota) automatically —
that's enforced inside recon_pipeline.py regardless of who calls it. If a run
gets blocked (trial expired / quota hit), autopilot checks why via the
account API and STOPS with a clear message rather than looping forever on a
failure it can't fix itself.

Usage:
  python3 recon/autopilot.py                    # run forever
  python3 recon/autopilot.py --max-targets 3     # stop after 3 targets
  python3 recon/autopilot.py --delay 60          # seconds between targets (default 30)
Stop anytime: Ctrl+C (or kill the process if run in the background).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"
sys.path.insert(0, str(RECON))

import account_client  # noqa: E402


def detect_capability() -> tuple[str, int, int | None, dict]:
    """CPU count + RAM -> a safe scan-intensity tier. No external deps —
    /proc/meminfo is Linux-only; falls back to a conservative tier elsewhere."""
    cpu = os.cpu_count() or 2
    ram_mb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    ram_mb = int(line.split()[1]) // 1024
                    break
    except (FileNotFoundError, OSError):
        pass

    if cpu >= 8 and (ram_mb or 0) >= 8192:
        tier = "high"
    elif cpu >= 4 and (ram_mb or 0) >= 4096:
        tier = "medium"
    else:
        tier = "low"

    tier_settings = {
        "high":   {"NUCLEI_MAX_HOST_ERROR": "5", "NUCLEI_TIMEOUT": "8"},
        "medium": {"NUCLEI_MAX_HOST_ERROR": "3", "NUCLEI_TIMEOUT": "5"},
        "low":    {"NUCLEI_MAX_HOST_ERROR": "2", "NUCLEI_TIMEOUT": "4"},
    }
    return tier, cpu, ram_mb, tier_settings[tier]


def find_next_fresh_program() -> str | None:
    """Fetch newest bounty programs from H1 (same as TUI option 4) and return
    the first one that doesn't already have a local target folder."""
    result = subprocess.run(
        [sys.executable, str(RECON / "h1_client.py"), "--list", "--bounty-only", "--sort-recency", "--json"],
        cwd=str(BASE), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[autopilot] h1_client.py --list failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    try:
        programs = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("[autopilot] could not parse program list.", file=sys.stderr)
        return None

    for prog in programs:
        handle = prog.get("handle")
        if not handle:
            continue
        folder = BASE / handle
        if not (folder / "scope.yaml").exists():
            return handle
    return None


def run_one_target(handle: str, env_overrides: dict) -> int:
    print(f"[autopilot] === Setting up target: {handle} ===")
    setup = subprocess.run(
        [sys.executable, str(RECON / "h1_client.py"), "--setup", handle, "--folder", handle],
        cwd=str(BASE),
    )
    if setup.returncode != 0:
        print(f"[autopilot] setup failed for '{handle}' (exit {setup.returncode}) — skipping.")
        return setup.returncode

    print(f"[autopilot] === Running zero-touch hunt on: {handle} ===")
    env = os.environ.copy()
    env.update(env_overrides)
    hunt = subprocess.run(
        ["bash", str(BASE / "start-bugbounty.sh"), "--auto", handle, "--fresh"],
        cwd=str(BASE), env=env,
    )
    return hunt.returncode


def account_gate_is_blocking() -> str | None:
    """Returns a human-readable reason if the account-gate is why runs are
    failing, or None if the account looks fine (failure was something else)."""
    ok, data = account_client.get_status()
    if not ok:
        return f"Account status check failed: {data.get('error', 'unknown')}"
    if data.get("trial_days_remaining") == 0 and data.get("tier") == "free":
        return "Free trial khatam ho gaya. Subscribe karo autopilot jaari rakhne ke liye."
    if data.get("remaining") == 0:
        return f"Aaj ka daily-scan-limit ({data.get('daily_limit')}) khatam ho gaya."
    return None


def run_autopilot(max_targets: int | None, delay_between: int) -> None:
    tier, cpu, ram_mb, env_overrides = detect_capability()
    ram_str = f"{ram_mb}MB" if ram_mb is not None else "unknown"
    print(f"[autopilot] PC capability detected: {tier} ({cpu} cores, {ram_str} RAM)")
    print(f"[autopilot] Auto-tuned settings: {env_overrides}")

    count = 0
    consecutive_failures = 0
    while True:
        if max_targets is not None and count >= max_targets:
            print(f"[autopilot] Reached --max-targets={max_targets}. Stopping.")
            return

        handle = find_next_fresh_program()
        if not handle:
            print("[autopilot] Koi naya fresh program nahi mila. 1 ghante baad dobara try karunga.")
            time.sleep(3600)
            continue

        rc = run_one_target(handle, env_overrides)
        if rc != 0:
            reason = account_gate_is_blocking()
            if reason:
                print(f"[autopilot] STOPPED: {reason}")
                return
            consecutive_failures += 1
            print(f"[autopilot] '{handle}' hunt exited with code {rc} (not account-related). "
                  f"consecutive_failures={consecutive_failures}")
            if consecutive_failures >= 3:
                print("[autopilot] 3 lagataar failures — kuch aur wajah se ruk raha hai (network/tools?). "
                      "Diagnostics check karo (Main Menu -> [D]). Stopping to avoid wasted loops.")
                return
        else:
            consecutive_failures = 0

        count += 1
        print(f"[autopilot] Target #{count} ('{handle}') complete. {delay_between}s baad agla target...")
        time.sleep(delay_between)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-targets", type=int, default=None, help="stop after N targets (default: run forever)")
    ap.add_argument("--delay", type=int, default=30, help="seconds to wait between targets (default: 30)")
    args = ap.parse_args()
    try:
        run_autopilot(max_targets=args.max_targets, delay_between=args.delay)
    except KeyboardInterrupt:
        print("\n[autopilot] Stopped by user (Ctrl+C).")


if __name__ == "__main__":
    main()
