#!/usr/bin/env python3
"""
HackerOne Direct API Client & Target Workspace Provisioner.
Pure Python standard library (no external pip dependencies).

Functions:
- Test HackerOne API authentication
- List accessible programs & filter existing workspace targets
- Fetch program details & structured scope
- Auto-scaffold target workspace (<target>/scope.yaml, SCOPE.md, NOTES.md, opencode.json)
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_auth_headers():
    username = os.environ.get("H1_USERNAME", "").strip()
    api_token = os.environ.get("H1_API_TOKEN", "").strip()

    # Fallback to local .env.h1 if not set in environment
    if not username or not api_token:
        env_file = BASE_DIR / ".env.h1"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("export H1_USERNAME=") or line.startswith("H1_USERNAME="):
                    username = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("export H1_API_TOKEN=") or line.startswith("H1_API_TOKEN="):
                    api_token = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not username or not api_token:
        return None
    cred = f"{username}:{api_token}".encode("utf-8")
    encoded = base64.b64encode(cred).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "User-Agent": "BugBounty-Automation/2.0"
    }

def h1_request(endpoint, params=None):
    headers = get_auth_headers()
    if not headers:
        raise ValueError("H1_USERNAME ya H1_API_TOKEN environment variables set nahi hain.")
    
    url = f"https://api.hackerone.com/v1/hackers{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return e.code, {"error": str(e), "body": body}
    except Exception as e:
        return 0, {"error": str(e)}

def test_auth():
    status, data = h1_request("/programs", {"page[size]": "1"})
    if status == 200:
        return True, "Authentication successful (HTTP 200)"
    return False, f"Auth failed with HTTP {status}: {data.get('error', 'unknown error')}"

def list_existing_targets():
    targets = set()
    for item in BASE_DIR.iterdir():
        if item.is_dir() and (item / "scope.yaml").is_file():
            targets.add(item.name.lower())
    return targets

def list_programs(page_size=50, filter_existing=True, bounty_only=False, verbose=False):
    existing = list_existing_targets() if filter_existing else set()
    candidates = []
    
    if verbose:
        print("  [1/4] 🌐 Connecting to HackerOne API (api.hackerone.com)...", file=sys.stderr)
        
    status, data = h1_request("/programs", {"page[size]": str(page_size)})
    if status != 200:
        print(f"  [!] Error fetching programs: HTTP {status} - {data.get('error')}", file=sys.stderr)
        return candidates

    programs = data.get("data", [])
    if verbose:
        filter_label = "Cash Bounty ($$$ Paid Only)" if bounty_only else "All Programs (Cash + VDP)"
        print(f"  [2/4] 🔍 Querying active programs (Found {len(programs)} programs on H1)...", file=sys.stderr)
        print(f"  [3/4] 💰 Filtering programs: [{filter_label}]...", file=sys.stderr)

    for p in programs:
        attrs = p.get("attributes", {})
        handle = attrs.get("handle", "")
        name = attrs.get("name", "")
        state = attrs.get("state", "")
        bounty = attrs.get("offers_bounties", False)
        
        if not handle:
            continue
            
        if bounty_only and not bounty:
            continue
            
        norm_handle = handle.lower().replace("-", "_")
        if filter_existing and (handle.lower() in existing or norm_handle in existing):
            continue
            
        candidates.append({
            "id": p.get("id"),
            "handle": handle,
            "name": name,
            "state": state,
            "offers_bounties": bounty
        })
        
    if verbose:
        print(f"  [4/4] 🛡 Workspace check: Filtered existing targets. {len(candidates)} candidates ready.", file=sys.stderr)
        
    return candidates

def get_program_details(handle):
    status, data = h1_request(f"/programs/{handle}")
    if status != 200:
        return None
    return data

def get_structured_scopes(handle):
    scopes = []
    page = 1
    while True:
        status, data = h1_request(f"/programs/{handle}/structured_scopes", {"page[number]": str(page), "page[size]": "100"})
        if status != 200:
            break
        items = data.get("data", [])
        if not items:
            break
        scopes.extend(items)
        links = data.get("links", {})
        if not links.get("next") or page >= 5:
            break
        page += 1
    return scopes

def setup_target(handle, folder_name=None, force=False):
    if not folder_name:
        folder_name = handle.lower().replace("-", "_")
        
    target_dir = BASE_DIR / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[h1_client] Target folder: {target_dir}")
    
    prog_meta = get_program_details(handle)
    attrs = prog_meta.get("attributes", {}) if prog_meta else {}
    prog_name = attrs.get("name", handle.capitalize())
    policy = attrs.get("policy", "")
    
    scopes = get_structured_scopes(handle)
    print(f"[h1_client] Retrieved {len(scopes)} structured scope items from HackerOne.")
    
    roots = []
    excluded = []
    assets = []
    
    for s in scopes:
        s_id = s.get("id")
        s_attrs = s.get("attributes", {})
        identifier = s_attrs.get("asset_identifier", "").strip()
        asset_type = s_attrs.get("asset_type", "").lower()
        eligible = s_attrs.get("eligible_for_bounty", False)
        max_sev = s_attrs.get("max_severity", "none").lower()
        instruction = s_attrs.get("instruction", "")
        
        if not identifier:
            continue
            
        asset_record = {
            "identifier": identifier,
            "type": asset_type,
            "max_severity": max_sev,
            "scope_id": s_id,
            "eligible_for_bounty": eligible
        }
        assets.append(asset_record)
        
        clean_target = identifier
        if clean_target.startswith("https://"):
            clean_target = clean_target[8:]
        elif clean_target.startswith("http://"):
            clean_target = clean_target[7:]
        # Filter third party app store links from web reconnaissance roots
        is_third_party = any(clean_target.lower().startswith(ign) for ign in [
            "play.google.com", "apps.apple.com", "itunes.apple.com", "github.com"
        ])
        host_target = clean_target.split("/")[0] if "/" in clean_target else clean_target
        
        if asset_type in ("url", "domain", "wildcard", "api", "cidr") and not is_third_party:
            if eligible and max_sev != "none":
                if host_target not in roots:
                    roots.append(host_target)
            else:
                if host_target not in excluded:
                    excluded.append(host_target)
        elif not eligible or max_sev == "none":
            if not is_third_party and host_target not in excluded:
                excluded.append(host_target)

    # 1. Create scope.yaml
    scope_yaml_path = target_dir / "scope.yaml"
    if not scope_yaml_path.exists() or force:
        yaml_lines = [
            f"# {prog_name} — Engagement Contract (machine-readable)",
            f"# Source of truth: {folder_name}/SCOPE.md + HackerOne program scope",
            f"# Last synced from HackerOne API: 2026-09-05",
            "",
            "program:",
            f'  handle: "{handle}"',
            f'  name: "{prog_name}"',
            f"  confirmed: {str(bool(prog_meta)).lower()}",
            "",
            "roots:"
        ]
        if roots:
            for r in roots:
                yaml_lines.append(f"  - {r}")
        else:
            yaml_lines.append("  # [Action Required] Add target roots here:")
            yaml_lines.append(f"  # - {handle}.com")
            
        yaml_lines.extend([
            "",
            "excluded:"
        ])
        if excluded:
            for ex in excluded:
                yaml_lines.append(f'  - "{ex}"')
        else:
            yaml_lines.append("  []")
            
        yaml_lines.extend([
            "",
            "assets:"
        ])
        for a in assets:
            yaml_lines.append(f'  - identifier: "{a["identifier"]}"')
            yaml_lines.append(f'    type: "{a["type"]}"')
            yaml_lines.append(f'    max_severity: "{a["max_severity"]}"')
            yaml_lines.append(f'    scope_id: "{a["scope_id"]}"')
            yaml_lines.append(f'    eligible_for_bounty: {str(a["eligible_for_bounty"]).lower()}')
            
        yaml_lines.extend([
            "",
            "allowed:",
            "  methods: [GET, HEAD, OPTIONS, POST]",
            "  max_requests_per_minute: 60",
            "  max_concurrency: 5",
            "  destructive_actions: false",
            '  sqlmap: "--batch --risk 1"              # non-destructive only'
        ])
        scope_yaml_path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        print(f"[h1_client] Created {scope_yaml_path}")

    # 2. Create SCOPE.md
    scope_md_path = target_dir / "SCOPE.md"
    if not scope_md_path.exists() or force:
        md_lines = [
            f"# {prog_name} — SCOPE",
            "",
            f"> Program handle: `{handle}`",
            "> Synchronized directly via HackerOne API.",
            "> Har hunting session se pehle scope verify karein. Sirf in-scope targets par testing karein.",
            "",
            "## Program Info",
            f"- **Handle:** `{handle}`",
            f"- **Name:** {prog_name}",
            f"- **Bounty Eligible:** {attrs.get('offers_bounties', False)}",
            "",
            "## In-Scope Assets (Eligible for Bounty)"
        ]
        if roots:
            md_lines.append("| Asset Identifier | Type | Scope ID | Max Severity |")
            md_lines.append("|---|---|---|---|")
            for a in assets:
                if a["eligible_for_bounty"] and a["max_severity"] != "none":
                    md_lines.append(f"| `{a['identifier']}` | {a['type']} | {a['scope_id']} | {a['max_severity']} |")
        else:
            md_lines.append("*(Check scope.yaml and populate verified roots)*")
            
        md_lines.extend([
            "",
            "## Excluded / Out-of-Scope",
            "*(Strictly do NOT touch any of these)*"
        ])
        if excluded:
            for ex in excluded:
                md_lines.append(f"- `{ex}`")
        else:
            md_lines.append("- None listed explicitly.")
            
        if policy:
            md_lines.extend([
                "",
                "## Program Policy Excerpt",
                policy[:2000] + ("..." if len(policy) > 2000 else "")
            ])
            
        scope_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"[h1_client] Created {scope_md_path}")

    # 3. Create NOTES.md
    notes_md_path = target_dir / "NOTES.md"
    if not notes_md_path.exists():
        notes_content = f"""# {prog_name} — Hunt Progress & Notes

## Active Session
- Target: `{handle}`
- Initialized: 2026-09-05

## Recon & Surface Notes
- In-Scope Roots: {len(roots)}
- Excluded Assets: {len(excluded)}

## Triage Queue & Hypotheses
- [ ] Subdomain enumeration & live probing
- [ ] Deep JS & route extraction
- [ ] Auth & access control verification
"""
        notes_md_path.write_text(notes_content, encoding="utf-8")
        print(f"[h1_client] Created {notes_md_path}")

    # 4. Create opencode.json
    opencode_path = target_dir / "opencode.json"
    if not opencode_path.exists():
        parent_oc = BASE_DIR / "meesho" / "opencode.json"
        if parent_oc.exists():
            opencode_path.write_text(parent_oc.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[h1_client] Created {opencode_path}")

    return {
        "folder": folder_name,
        "name": prog_name,
        "roots_count": len(roots),
        "excluded_count": len(excluded),
        "assets_count": len(assets)
    }

def generate_hunt_prompt(target_dir):
    target_path = BASE_DIR / target_dir if not isinstance(target_dir, Path) else target_dir
    scope_yaml_file = target_path / "scope.yaml"
    if not scope_yaml_file.exists():
        return f"Error: {scope_yaml_file} nahi mila."

    try:
        import yaml
        with open(scope_yaml_file, "r") as f:
            scope_data = yaml.safe_load(f)
    except Exception:
        scope_data = {"roots": [], "excluded": [], "program": {"handle": target_path.name, "name": target_path.name}}

    prog = scope_data.get("program", {}) if isinstance(scope_data, dict) else {}
    handle = prog.get("handle", target_path.name)
    name = prog.get("name", handle.capitalize())
    roots = scope_data.get("roots", []) if isinstance(scope_data, dict) else []
    excluded = scope_data.get("excluded", []) if isinstance(scope_data, dict) else []
    allowed = scope_data.get("allowed", {}) if isinstance(scope_data, dict) else {}
    rpm = allowed.get("max_requests_per_minute", 60)
    concurrency = allowed.get("max_concurrency", 5)

    cand_file = BASE_DIR / "recon" / "data" / target_path.name / "candidate_report.md"
    top_candidates = []
    if cand_file.exists():
        lines = cand_file.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith("- ["):
                top_candidates.append(line)
            if len(top_candidates) >= 6:
                break

    candidates_block = "\n".join(top_candidates) if top_candidates else "- Run recon/intelligence.py first to rank candidates."
    roots_block = "\n".join(f"  - {r}" for r in roots) if roots else "  - (Check scope.yaml)"
    excluded_block = "\n".join(f"  - {ex}" for ex in excluded) if excluded else "  - None listed"

    prompt = f"""# MISSION: Autonomous Bug Bounty Hunting — Target: {name} ({handle})

You are operating in the dedicated authorized HackerOne workspace for program `{handle}`.
Your objective is to find valid, high-impact security vulnerabilities and prepare actionable non-destructive Proof-of-Concepts (PoCs).

## 1. SCOPE & LEGAL BOUNDARIES (Hard Rules)
- IN-SCOPE TARGETS:
{roots_block}

- EXCLUDED / OUT-OF-SCOPE (Strictly forbidden — Do NOT touch):
{excluded_block}

- SAFE OPERATING LIMITS:
  - Max rate limit: {rpm} requests/min | Concurrency: {concurrency}
  - Destructive actions: STRICTLY PROHIBITED
  - sqlmap: non-destructive only (`--batch --risk 1`)
  - No DoS, no credential brute forcing, no customer data corruption.

## 2. HIGH-PRIORITY ATTACK SURFACE & RECON CANDIDATES
{candidates_block}

## 3. YOUR EXECUTION PROTOCOL
1. **Analyze Candidates**: Examine prioritized endpoints above (auth flows, admin panels, sensitive APIs).
2. **Formulate Hypotheses**:
   - Access Control: Test for IDOR / BOLA on IDs, user_ids, invoice parameters.
   - Authentication Flaws: Test token validation, OAuth redirect params, SSO callback flaws.
   - Information Disclosure: Test API endpoints for secret leakage or internal cloud bucket exposures.
   - SSRF / Open Redirect: Test URL parameters handling redirections.
3. **Execute Non-Destructive Verification**:
   - Use `curl -s -i` or Burp Suite to reproduce.
   - Record exact HTTP request & response headers.
4. **Prepare Report Artifact**:
   - Save PoC evidence to `evidence/findings/{handle}/`.
   - Match with HackerOne scope_id from `scope.yaml` for triage submission.

Proceed with systematic hunting now. Focus on quality, business impact, and rigorous verification!"""

    out_file = target_path / "AUTONOMOUS_HUNT_PROMPT.md"
    out_file.write_text(prompt, encoding="utf-8")
    return prompt

def main():
    parser = argparse.ArgumentParser(description="HackerOne API Client & Target Workspace Manager")
    parser.add_argument("--test-auth", action="store_true", help="Test H1 credentials")
    parser.add_argument("--list", action="store_true", help="List accessible H1 programs (excluding existing targets)")
    parser.add_argument("--bounty-only", action="store_true", help="Filter for cash bounty paid programs only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print live progress steps")
    parser.add_argument("--all", action="store_true", help="Include existing targets in listing")
    parser.add_argument("--setup", type=str, metavar="HANDLE", help="Auto-scaffold a target from HackerOne")
    parser.add_argument("--prompt", type=str, metavar="TARGET", help="Generate pre-filled autonomous hunt prompt for target")
    parser.add_argument("--folder", type=str, metavar="DIR", help="Custom folder name for target")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing scope files")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    
    args = parser.parse_args()
    
    if args.test_auth:
        ok, msg = test_auth()
        print(f"[h1_client] Auth test: {'SUCCESS' if ok else 'FAILED'} - {msg}")
        sys.exit(0 if ok else 1)
        
    if args.prompt:
        p = generate_hunt_prompt(args.prompt)
        print(p)
        return

    if args.list:
        programs = list_programs(page_size=50, filter_existing=not args.all, bounty_only=args.bounty_only, verbose=args.verbose)
        if args.json:
            print(json.dumps(programs, indent=2))
        else:
            if not programs:
                print("[h1_client] Koi naya candidate program nahi mila.")
            else:
                print(f"[h1_client] {len(programs)} available programs on HackerOne:")
                for i, p in enumerate(programs, 1):
                    bounty_tag = "💰 BOUNTY" if p.get("offers_bounties") else "ℹ VDP"
                    print(f"  {i:2d}) {p['handle']:<20} | {p['name']} ({bounty_tag})")
        return

    if args.setup:
        res = setup_target(args.setup, args.folder, force=args.force)
        print(f"[h1_client] Target '{res['folder']}' successfully configured:")
        print(f"  Roots: {res['roots_count']} | Excluded: {res['excluded_count']} | Assets: {res['assets_count']}")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
