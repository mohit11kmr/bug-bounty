#!/usr/bin/env python3
"""
recon_pipeline.py — Guide Phase 1+2: recon → normalized JSON
Scope-safe: SIRF scope.yaml ke roots/exclusions ke andar. Passive + light probing only.

Output (per program, recon/data/<program>/):
  raw/          — tool raw output (subfinder, dnsx, httpx, gau)
  assets.json   — normalized Asset[] (guide §8 data model)
  endpoints.json— normalized Endpoint[]
  run_meta.json — run metadata (tools, versions, timestamps)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any

BASE = Path(__file__).resolve().parent.parent  # bug-bounty/
RECON = BASE / "recon"
sys.path.insert(0, str(RECON))
from scope_utils import load_scope_file, make_scope_filter  # noqa: E402

RATE_LIMIT = {"concurrency": 5, "delay": "800ms"}  # WAF-safe default, scope.yaml override

TOOLS = ["subfinder", "dnsx", "httpx", "gau"]


def tool_version(t: str) -> str:
    """Best-effort version scrape: stderr/stdout, flag fallback. Faisla nahi rukega."""
    for flag in ("-version", "--version", "-v"):
        try:
            r = subprocess.run([t, flag], capture_output=True, text=True, timeout=5)
            out = (r.stdout + r.stderr).strip()
            for line in out.splitlines():
                if "unknown" in line.lower() or "flag" in line.lower():
                    continue
                if re.search(r"\d+\.\d+", line):
                    return line.strip()[:60]
        except (subprocess.SubprocessError, OSError):
            continue
    return ""


def log(msg: str) -> None:
    print(f"[recon] {msg}", flush=True)


def check_tools(skip_endpoints: bool = False) -> None:
    import shutil
    missing = []
    required = [t for t in TOOLS if not (skip_endpoints and t == "gau")]
    for t in required:
        if shutil.which(t) is None:
            missing.append(t)
    if missing:
        sys.exit(f"ERROR: missing tools: {', '.join(missing)}")


def load_scope(program_dir: Path) -> dict:
    scope_file = program_dir / "scope.yaml"
    return load_scope_file(
        scope_file, required=True,
        not_found_msg=f"ERROR: {scope_file} not found — pehle scope.yaml banao",
    )


def run(cmd: list, out: Path) -> None:
    log(f"  $ {' '.join(cmd)}  > {out.name}")
    has_output_flag = any(flag in cmd for flag in ("-o", "--o", "-output", "--output"))
    if has_output_flag:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        with open(out, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, check=False)


# load_scope_file/make_scope_filter: shared single source of truth, see scope_utils.py.


def validate_jsonl_output(path: Path) -> Tuple[str, List[dict]]:
    """
    Validates a JSONL output file.
    Returns (status, valid_records) where status is:
      - 'MISSING': file does not exist
      - 'EMPTY': file exists but is 0 bytes or has 0 valid records
      - 'PARTIAL': file contains some valid and some malformed lines
      - 'VALID': all non-empty lines are valid JSON records
    """
    if not path.exists():
        return "MISSING", []
    if path.stat().st_size == 0:
        return "EMPTY", []

    valid = []
    malformed = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and (rec.get("url") or rec.get("input")):
                    valid.append(rec)
                else:
                    malformed += 1
            except Exception:
                malformed += 1

    if not valid:
        return "EMPTY", []
    if malformed > 0:
        return "PARTIAL", valid
    return "VALID", valid


def validate_assets_list(assets: list) -> Tuple[str, List[dict]]:
    """Validates the in-memory Asset[] list before disk persistence."""
    if not isinstance(assets, list):
        return "MALFORMED", []
    if len(assets) == 0:
        return "EMPTY", []
    valid = [a for a in assets if isinstance(a, dict) and a.get("host")]
    if len(valid) == len(assets):
        return "VALID", valid
    return "PARTIAL", valid


def collect_assets(scope: dict, raw: Path, fresh: bool = False, run_id: str = "legacy") -> list:
    """Asset[] — guide §8: host, ip, status, title, tech, source, first_seen, last_seen."""
    is_in_scope = make_scope_filter(scope)
    roots = [str(r) for r in (scope.get("roots") or [])]
    subfinder_out = raw / "subfinder.txt"
    dnsx_out = raw / "dnsx.txt"
    httpx_out = raw / "httpx.jsonl"

    if fresh:
        log("  ⚡ [FRESH] Purging cached discovery files. Forcing re-enumeration.")
        subfinder_out.unlink(missing_ok=True)
        dnsx_out.unlink(missing_ok=True)
        httpx_out.unlink(missing_ok=True)

    # 1) subdomain discovery (passive) — roots se subfinder per-domain
    if not subfinder_out.exists() or subfinder_out.stat().st_size == 0:
        log(f"⚡ [1/3] Starting passive subdomain enumeration across {len(roots)} root targets...")
        all_subs = set()
        for idx, r in enumerate(roots, 1):
            clean_root = r.lstrip("*.").strip().split(":")[0]
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", clean_root) or clean_root.lower() == "localhost":
                continue
            print(f"  [recon] [{idx}/{len(roots)}] 🔍 Running subfinder on '{clean_root}'...", end="", flush=True)
            t_start = datetime.now()
            res = subprocess.run(["subfinder", "-d", clean_root, "-silent", "-timeout", "10"],
                                 capture_output=True, text=True, check=False)
            found = [line.strip().lower() for line in res.stdout.splitlines() if line.strip()]
            all_subs.update(found)
            dur = (datetime.now() - t_start).total_seconds()
            print(f" found {len(found)} subdomains ({dur:.1f}s)", flush=True)
        with open(subfinder_out, "w") as f:
            f.write("\n".join(sorted(all_subs)) + "\n")
        log(f"  ✓ Total passive subdomains discovered: {len(all_subs)}")
    else:
        log(f"  [CACHE REUSE] subfinder.txt already exists ({len(subfinder_out.read_text().splitlines())} lines) — reusing historical discovery. (Pass --fresh to re-enumerate)")

    subs = set()
    if subfinder_out.exists():
        subs = {l.strip().lower() for l in subfinder_out.read_text().splitlines() if l.strip()}
    clean_roots = {str(r).lstrip("*.").strip().lower() for r in roots}
    hosts = sorted({h for h in (subs | clean_roots) if is_in_scope(h)})
    log(f"  ✓ Subdomains filtered for scope: {len(hosts)} valid candidate hosts")

    # 2) DNS resolve (light)
    if not dnsx_out.exists() and hosts:
        log(f"🌐 [2/3] Resolving DNS for {len(hosts)} candidate hosts with dnsx...")
        with open(raw / "hosts.txt", "w") as f:
            f.write("\n".join(hosts))
        run(["dnsx", "-l", str(raw / "hosts.txt"), "-silent", "-o", str(dnsx_out)], dnsx_out)
        res_count = len(dnsx_out.read_text().splitlines()) if dnsx_out.exists() else 0
        log(f"  ✓ DNS resolved: {res_count}/{len(hosts)} hosts responding")
    elif dnsx_out.exists():
        log(f"  [CACHE REUSE] dnsx.txt already exists ({len(dnsx_out.read_text().splitlines())} lines) — reusing historical resolution. (Pass --fresh to re-enumerate)")

    # 3) HTTP probe + tech detect
    resolved_hosts = []
    if dnsx_out.exists():
        dns_lines = [l.strip().lower() for l in dnsx_out.read_text().splitlines() if l.strip()]
        resolved_hosts = sorted({h for h in dns_lines if is_in_scope(h)})

    probe_hosts = resolved_hosts if resolved_hosts else hosts
    probe_in = raw / "probe-in.txt"
    with open(probe_in, "w") as f:
        f.write("\n".join(probe_hosts))
    log(f"⚡ [3/3] Probing HTTP services, status & tech across {len(probe_hosts)} hosts with httpx...")
    
    # SINGLE PRODUCER ARCHITECTURE:
    # httpx outputs strictly to stdout; Python process alone writes the atomic temporary file.
    cmd = ["httpx", "-l", str(probe_in), "-silent",
           "-json", "-tech-detect", "-status-code", "-title",
           "-threads", str(RATE_LIMIT["concurrency"]), "-rate-limit", "60"]
    
    httpx_tmp = raw / f"httpx.{os.getpid()}.tmp"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    live_count = 0
    with open(httpx_tmp, "w", encoding="utf-8") as out_f:
        for line in proc.stdout:
            out_f.write(line)
            out_f.flush()
            try:
                rec = json.loads(line)
                url = rec.get("url", "")
                status = rec.get("status_code", "")
                title = rec.get("title", "")
                title_str = f" [{title[:30]}...]" if title else ""
                tech = ", ".join(rec.get("tech", [])[:3])
                tech_str = f" ({tech})" if tech else ""
                live_count += 1
                if live_count <= 25 or live_count % 10 == 0:
                    print(f"  [alive] ✓ {url} [{status}]{tech_str}{title_str}", flush=True)
            except Exception:
                pass
    _, stderr_data = proc.communicate()
    
    # Atomic validation & commit
    v_status, valid_records = validate_jsonl_output(httpx_tmp)
    if v_status in ("VALID", "PARTIAL") and valid_records:
        os.replace(httpx_tmp, httpx_out)
        log(f"  ✓ HTTP probing complete: {len(valid_records)} live web endpoints detected (Contract: {v_status})")
    elif v_status == "EMPTY":
        httpx_tmp.unlink(missing_ok=True)
        log(f"  ⚠ HTTP probing returned 0 responsive endpoints across {len(probe_hosts)} candidate hosts (Contract: EMPTY).")
    else:
        httpx_tmp.unlink(missing_ok=True)
        log(f"  ✖ HTTP probing output was malformed (Contract: {v_status}). Stderr: {stderr_data.strip()[:120]}")

    # If httpx_out exists from atomic commit or valid previous run, parse records
    if not valid_records and httpx_out.exists():
        _, valid_records = validate_jsonl_output(httpx_out)

    now = date.today().isoformat()
    assets = []
    for h in valid_records:
        assets.append({
            "host": h.get("input", ""),
            "url": h.get("url", ""),
            "ip": h.get("a", [""])[0] if h.get("a") else "",
            "status": h.get("status_code"),
            "title": h.get("title", ""),
            "technologies": h.get("tech", []),
            "webserver": h.get("webserver", ""),
            "source": ["subfinder", "httpx"],
            "first_seen": now,
            "last_seen": now,
            "run_id": run_id,
        })
    return assets


def collect_endpoints(scope: dict, raw: Path, fresh: bool = False, run_id: str = "legacy") -> list:
    """Endpoint[] — guide §8: url, method, source, auth_hint. Out-of-scope URLs dropped."""
    is_in_scope = make_scope_filter(scope)
    gau_out = raw / "gau.txt"
    if fresh:
        log("  ⚡ [FRESH] Purging cached gau.txt. Forcing archive re-harvesting.")
        gau_out.unlink(missing_ok=True)

    if not gau_out.exists() or gau_out.stat().st_size == 0:
        roots_clean = [str(r).lstrip("*.").strip() for r in (scope.get("roots") or [])]
        log(f"📜 Querying Wayback Machine, AlienVault & URLScan across {len(roots_clean)} roots...")
        all_urls = set()
        for idx, r in enumerate(roots_clean, 1):
            clean_r = r.split(":")[0]
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", clean_r) or clean_r.lower() == "localhost":
                continue
            print(f"  [archive] [{idx}/{len(roots_clean)}] 🌐 Harvesting archive URLs for '{r}'...", end="", flush=True)
            t_start = datetime.now()
            res = subprocess.run(["gau", "--threads", "5", "--subs", r],
                                 capture_output=True, text=True, check=False)
            found = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith("http")]
            in_scope_found = [u for u in found if is_in_scope(u.split("/", 3)[2].split(":")[0].lower())]
            all_urls.update(in_scope_found)
            dur = (datetime.now() - t_start).total_seconds()
            print(f" found {len(in_scope_found)} in-scope URLs ({dur:.1f}s)", flush=True)
        with open(gau_out, "w") as f:
            f.write("\n".join(sorted(all_urls)) + "\n")
        log(f"  ✓ Archive harvesting complete: {len(all_urls)} unique in-scope URLs collected")
    else:
        log(f"  [CACHE REUSE] gau.txt exists ({len(gau_out.read_text().splitlines())} lines) — reusing historical archive discovery. (Pass --fresh to re-harvest)")

    urls = set()
    if gau_out.exists():
        for l in gau_out.read_text().splitlines():
            l = l.strip()
            if not l.startswith("http"):
                continue
            host = l.split("/", 3)[2].split(":")[0].lower()
            if is_in_scope(host):
                urls.add(l)

    now = date.today().isoformat()
    endpoints = sorted(
        ({"url": u, "method": "GET", "source": ["gau"], "auth_hint": "unknown",
          "first_seen": now, "last_seen": now, "run_id": run_id} for u in urls),
        key=lambda e: e["url"],
    )
    return endpoints


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log(f"  wrote {path.name} ({len(data)} records)")


def _selfcheck() -> None:
    print("[recon_pipeline] Running selfcheck...")
    scope = {
        "roots": ["example.com", "*.target.com"],
        "excluded": ["excluded.target.com"]
    }
    is_in_scope = make_scope_filter(scope)
    assert is_in_scope("example.com") is True
    assert is_in_scope("api.target.com") is True
    assert is_in_scope("excluded.target.com") is False
    assert is_in_scope("out-of-scope.com") is False

    # Contract test: validate_jsonl_output
    tmp_dir = BASE / "recon" / "data" / ".cache" / f"test_check_{os.getpid()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        f_missing = tmp_dir / "nonexistent.jsonl"
        st, recs = validate_jsonl_output(f_missing)
        assert st == "MISSING" and len(recs) == 0, "MISSING check failed"

        f_empty = tmp_dir / "empty.jsonl"
        f_empty.write_text("")
        st, recs = validate_jsonl_output(f_empty)
        assert st == "EMPTY" and len(recs) == 0, "EMPTY check failed"

        f_valid = tmp_dir / "valid.jsonl"
        f_valid.write_text('{"url": "https://example.com", "status_code": 200}\n')
        st, recs = validate_jsonl_output(f_valid)
        assert st == "VALID" and len(recs) == 1, "VALID check failed"

        f_partial = tmp_dir / "partial.jsonl"
        f_partial.write_text('{"url": "https://example.com"}\ncorrupted_line\n')
        st, recs = validate_jsonl_output(f_partial)
        assert st == "PARTIAL" and len(recs) == 1, "PARTIAL check failed"

        # Contract test: validate_assets_list
        assert validate_assets_list([]) == ("EMPTY", [])
        assert validate_assets_list([{"host": "example.com"}])[0] == "VALID"
        assert validate_assets_list([{"no_host": 1}])[0] == "PARTIAL"
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("[recon_pipeline] selfcheck OK: Scope filter and data contracts verified.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default="meesho", help="program folder name")
    ap.add_argument("--skip-endpoints", action="store_true", help="gau skip (slow)")
    ap.add_argument("--skip-js", action="store_true", help="skip katana JS crawl & mining")
    ap.add_argument("--fresh", "--force", dest="fresh", action="store_true",
                    help="force fresh enumeration, bypassing and refreshing cached raw files (subfinder, dnsx, httpx, gau)")
    ap.add_argument("--selfcheck", action="store_true", help="run internal selfcheck")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    check_tools(skip_endpoints=args.skip_endpoints)
    program_dir = BASE / args.program
    scope = load_scope(program_dir)

    data_dir = RECON / "data" / args.program
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    # Generated up front so every artifact this run produces (assets.json/endpoints.json
    # records, run_meta.json) shares one id — the basis for stale-artifact detection.
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    roots = scope.get("roots") or []
    excluded = scope.get("excluded") or []
    log(f"program={args.program} | roots={len(roots)} | excluded={len(excluded)} | fresh={args.fresh} | run_id={run_id}")
    log("=== Phase 1: Asset discovery ===")
    assets = collect_assets(scope, raw, fresh=args.fresh, run_id=run_id)
    a_status, valid_assets = validate_assets_list(assets)
    if a_status == "EMPTY":
        log("  ⚠ 0 active web assets found. assets.json written as [] (Contract: EMPTY).")
    else:
        log(f"  ✓ {len(assets)} active assets validated. assets.json written (Contract: {a_status}).")
    write_json(data_dir / "assets.json", assets)

    endpoints = []
    if not args.skip_endpoints:
        log("=== Phase 1b: Endpoint collection (gau) ===")
        endpoints = collect_endpoints(scope, raw, fresh=args.fresh, run_id=run_id)
        write_json(data_dir / "endpoints.json", endpoints)

    if not args.skip_js:
        log("=== Phase 1b.2: Client-side JS Mining (Katana) ===")
        js_script = RECON / "js_miner.py"
        r = subprocess.run([sys.executable, str(js_script), "--program", args.program],
                           cwd=str(BASE), check=False)

    if (data_dir / "endpoints.json").exists():
        log("=== Phase 1c: Application model ===")
        app_script = RECON / "application_model.py"
        r = subprocess.run([sys.executable, str(app_script), "--program", args.program],
                           cwd=str(BASE), capture_output=True, text=True)
        if r.returncode != 0:
            log(f"  application_model.py warning: {r.stderr.strip()}")
        else:
            log("  application_model.json generated successfully")

    run_at = datetime.now().isoformat(timespec="seconds")
    meta = {
        "run_id": run_id,
        "program": args.program,
        "fresh_mode": args.fresh,
        "run_at": run_at,
        "tools": {t: tool_version(t) for t in TOOLS},
        "rate_limits": RATE_LIMIT,
        "asset_count": len(assets),
        "endpoint_count": len(endpoints),
        "status": "VALID" if len(assets) > 0 else "NO_LIVE_ASSETS",
    }
    write_json(data_dir / "run_meta.json", meta)
    log(f"Done. Run ID: {run_id}")


if __name__ == "__main__":
    main()