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
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # bug-bounty/
RECON = BASE / "recon"
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
    import yaml
    scope_file = program_dir / "scope.yaml"
    if not scope_file.exists():
        sys.exit(f"ERROR: {scope_file} not found — pehle scope.yaml banao")
    return yaml.safe_load(scope_file.read_text())


def run(cmd: list, out: Path) -> None:
    log(f"  $ {' '.join(cmd)}  > {out.name}")
    has_output_flag = any(flag in cmd for flag in ("-o", "--o", "-output", "--output"))
    if has_output_flag:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        with open(out, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, check=False)


def make_scope_filter(scope: dict):
    """Return fn(host) -> bool. In-scope = root match AND not excluded (wildcard aware)."""
    roots = [str(r).lower() for r in scope["roots"]]
    excluded = [str(x).lower() for x in scope.get("excluded", [])]

    def wildcard_match(host: str, patterns: list) -> bool:
        host = host.lower().rstrip(".")
        for p in patterns:
            if p.startswith("*."):
                # *.example.com matches sub.example.com + example.com
                base = p[2:]
                if host == base or host.endswith("." + base):
                    return True
            elif p == host:
                return True
        return False

    def in_scope(host: str) -> bool:
        host = host.lower().rstrip(".")
        # 1) Explicit root match — hamesha in-scope (wildcard exclusions "barring" ko respect karo)
        if host in roots:
            return True
        # 2) Exclusion match — out-of-scope (wildcard included)
        if wildcard_match(host, excluded):
            return False
        # 3) Root subdomain match — in-scope
        return wildcard_match(host, roots)
    return in_scope


def collect_assets(scope: dict, raw: Path) -> list:
    """Asset[] — guide §8: host, ip, status, title, tech, source, first_seen, last_seen."""
    is_in_scope = make_scope_filter(scope)
    roots = [str(r) for r in scope["roots"]]
    subfinder_out = raw / "subfinder.txt"
    dnsx_out = raw / "dnsx.txt"
    httpx_out = raw / "httpx.jsonl"

    # 1) subdomain discovery (passive) — roots se subfinder per-domain
    if not subfinder_out.exists():
        with open(subfinder_out, "w") as f:
            for r in roots:
                subprocess.run(["subfinder", "-d", r, "-silent"],
                               stdout=f, stderr=subprocess.DEVNULL, check=False)
        log(f"  subfinder: roots={len(roots)} -> subfinder.txt")

    subs = set()
    if subfinder_out.exists():
        subs = {l.strip().lower() for l in subfinder_out.read_text().splitlines() if l.strip()}
    hosts = sorted({h for h in (subs | set(roots)) if is_in_scope(h)})
    log(f"  subdomains collected: {len(hosts)} (out-of-scope filtered)")

    # 2) DNS resolve (light)
    if not dnsx_out.exists() and hosts:
        with open(raw / "hosts.txt", "w") as f:
            f.write("\n".join(hosts))
        run(["dnsx", "-l", str(raw / "hosts.txt"), "-silent", "-o", str(dnsx_out)], dnsx_out)

    # 3) HTTP probe + tech detect
    with open(raw / "probe-in.txt", "w") as f:
        f.write("\n".join(hosts))
    run(["httpx", "-l", str(raw / "probe-in.txt"), "-silent",
         "-json", "-tech-detect", "-status-code", "-title",
         "-threads", str(RATE_LIMIT["concurrency"]), "-rate-limit", "60",
         "-o", str(httpx_out)], httpx_out)

    now = date.today().isoformat()
    assets = []
    probe_lines = httpx_out.read_text().splitlines() if httpx_out.exists() else []
    for line in probe_lines:
        try:
            h = json.loads(line)
        except json.JSONDecodeError:
            continue
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
        })
    return assets


def collect_endpoints(scope: dict, raw: Path) -> list:
    """Endpoint[] — guide §8: url, method, source, auth_hint. Out-of-scope URLs dropped."""
    is_in_scope = make_scope_filter(scope)
    gau_out = raw / "gau.txt"
    if not gau_out.exists():
        with open(raw / "gau-in.txt", "w") as f:
            f.write("\n".join(str(r) for r in scope["roots"]))
        run(["gau", "--threads", "5", "--subs", "--o", str(gau_out), *scope["roots"]], gau_out)
    else:
        log(f"  gau.txt exists ({len(gau_out.read_text().splitlines())} lines) — reuse")

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
          "first_seen": now, "last_seen": now} for u in urls),
        key=lambda e: e["url"],
    )
    return endpoints


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log(f"  wrote {path.name} ({len(data)} records)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default="meesho", help="program folder name")
    ap.add_argument("--skip-endpoints", action="store_true", help="gau skip (slow)")
    ap.add_argument("--skip-js", action="store_true", help="skip katana JS crawl & mining")
    args = ap.parse_args()

    check_tools(skip_endpoints=args.skip_endpoints)
    program_dir = BASE / args.program
    scope = load_scope(program_dir)

    data_dir = RECON / "data" / args.program
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    log(f"program={args.program} | roots={len(scope['roots'])} | excluded={len(scope['excluded'])}")
    log("=== Phase 1: Asset discovery ===")
    assets = collect_assets(scope, raw)
    write_json(data_dir / "assets.json", assets)

    if not args.skip_endpoints:
        log("=== Phase 1b: Endpoint collection (gau) ===")
        endpoints = collect_endpoints(scope, raw)
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

    meta = {
        "program": args.program,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "tools": {t: tool_version(t) for t in TOOLS},
        "rate_limits": RATE_LIMIT,
        "asset_count": len(assets),
    }
    write_json(data_dir / "run_meta.json", meta)
    log("Done.")


if __name__ == "__main__":
    main()