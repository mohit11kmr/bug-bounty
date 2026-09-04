# Bug Bounty AI Automation — Deep Audit

**Audit Date:** 2026-09-04
**Auditor:** Multi-agent audit pipeline (system auditor, security tool auditor, MCP specialist, OpenCode specialist, 2× workspace analysts, 2× external researchers, synthesis)
**Targets Audited:**
- Machine: `Linux Mint 22.3 (Zena)` — local workstation
- Workspace 1: `/home/mohit/Desktop/projects/bug-bounty/`
- Workspace 2: `/home/mohit/Desktop/projects/bug-bountyhunt by ai with saas/`

> **Method note:** This is an evidence-based audit. Every claim was verified by direct inspection, live execution, or documented source. No destructive changes were made. No secrets are reproduced in this file — secrets are reported as `PRESENT — VALUE REDACTED`.

---

## 1. Executive Summary

**Health Score (0-10):**

| Component | Score |
|-----------|-------|
| OS / Runtime Health | 8/10 |
| Security Tooling | 7.5/10 |
| MCP Infrastructure | 8/10 |
| OpenCode Configuration | 7/10 |
| Workspace 1 (Hunting) | 4/10 operational, 2/10 state-management |
| Workspace 2 (SaaS) | 3/10 (security 2/10, production-readiness 2/10) |
| **Overall Platform** | **4.5/10** |

**Bottom line:** The machine is a competent bug-bounty workstation — 20+ core tool binaries exist and work, all 8 MCP servers connect, and OpenCode is well configured around a `hackerone-analyst` agent. But the **operational backbone is broken**: evidence is written to `/tmp` and has been wiped, **zero reports have ever been submitted** (verified against the live H1 API), Workspace 1 has **no git/state/DB/scheduler**, and Workspace 2's SaaS has a **missing findings pipeline** (scan output never becomes `Finding` rows), **no scope enforcement** (arbitrary-target scanning = SSRF/abuse), and **dangerous defaults** including a live H1 PAT on disk and an image that bakes local `.env` into it.

Highest-leverage first moves: (1) submit or close the Kiwi MEDIUM draft, (2) rotate the exposed H1 token, (3) git-init Workspace 1, (4) fix evidence persistence (out of `/tmp`), (5) enforce scope checks + findings pipeline in the SaaS before any public exposure.

---

## 2. Current Machine Environment

| Field | Value | Evidence |
|-------|-------|----------|
| Distribution | Linux Mint 22.3 "Zena" | `/etc/os-release` `PRETTY_NAME="Linux Mint 22.3"` |
| Based on | Ubuntu/Debian (`ID_LIKE="ubuntu debian"`) | `/etc/os-release` |
| Kernel | `6.8.0-139-generic` | `uname -r` |
| Architecture | `x86_64` | `uname -m` |
| Shell | `/bin/bash` | `$SHELL` |
| Desktop Environment | XFCE (`XDG_CURRENT_DESKTOP=XFCE`) | env |
| Session | X11 (`DISPLAY=:0.0`) | env |
| CPU | Intel Core i5-5300U @ 2.30GHz (2C/4T) | `lscpu` |
| RAM | 7.6 GiB total, ~5.6 available | `free -h` |
| Disk | 137 GiB root, 23 GiB free | `df -h` |

### Runtimes & Toolchains

| Runtime | Version | Status |
|---------|---------|--------|
| Python | 3.12.3 | ✅ |
| pip | 24.0 (dist-packages) | ✅ |
| Node.js | v22.23.2 | ✅ |
| npm | 10.9.8 | ✅ |
| pnpm | 9.15.9 | ✅ |
| bun | 1.3.14 | ✅ |
| Go | 1.22.2 | ✅ |
| Java (OpenJDK) | 21.0.12 | ✅ |
| PHP | 8.3.6 | ✅ |
| Composer | 2.7.1 | ✅ |
| Rust/Cargo | — | ❌ NOT INSTALLED |
| Ruby/gem | — | ❌ NOT INSTALLED |
| yarn | — | ❌ NOT INSTALLED |

### System Tools

| Tool | Version | Status |
|------|---------|--------|
| Git | 2.43.0 | ✅ |
| OpenSSH | 9.6p1/OpenSSL 3.0.13 | ✅ |
| systemd | 255 (255.4-1ubuntu8.17) | ✅ |
| apt | present at `/usr/local/bin/apt` | ✅ |
| flatpak | present | ✅ |
| snap | — | ❌ NOT INSTALLED |
| Docker CLI | 29.1.3 | ⚠️ CLI only — **daemon NOT running** |
| Docker Compose | 2.40.3 | ⚠️ needs daemon |
| cron | service **active (running)**, enabled | ✅ — used only for nifty daemon, no bug-bounty jobs |
| tmux | — | ❌ NOT INSTALLED |
| virtualbox | — | ❌ NOT INSTALLED |

---

## 3. Installed Tools

Complete inventory table (health verified by executing `--version`/`-h`/`command -v`, and where safe, harmless live checks).

### Recon & Asset Discovery

| Tool | Installed | Version | Path | Executes | Health | Notes |
|------|-----------|---------|------|----------|--------|-------|
| subfinder | ✅ | v2.16.0 | /usr/local/bin/subfinder | ✅ | 🟢 | live test OK |
| assetfinder | ✅ | (go) | /usr/local/bin/assetfinder | ✅ | 🟢 | |
| amass | ❌ | — | — | — | 🔴 MISSING | |
| findomain | ❌ | — | — | — | 🔴 MISSING | |
| chaos | ❌ | — | — | — | 🔴 MISSING | |
| dnsx | ✅ | (pd) | /usr/local/bin/dnsx | ✅ | 🟢 | |
| shuffledns | ❌ | — | — | — | 🔴 MISSING | |
| puredns | ❌ | — | — | — | 🔴 MISSING | |
| massdns | ❌ | — | — | — | 🔴 MISSING | |
| cloudflared | ✅ | — | /usr/local/bin/cloudflared | ✅ | 🟢 | useful for WARP-enabled exfil/hunting |

### HTTP / Web / Crawling

| Tool | Installed | Version | Path | Executes | Health | Notes |
|------|-----------|---------|------|----------|--------|-------|
| httpx | ✅ | latest | /usr/local/bin/httpx | ✅ | 🟢 | live test `example.com → 200` |
| httprobe | ❌ | — | — | — | 🔴 MISSING | |
| katana | ✅ | latest | /usr/local/bin/katana | ✅ | 🟢 | |
| gau | ✅ | latest | /usr/local/bin/gau | ✅ | 🟢 | |
| waybackurls | ✅ | latest | /usr/local/bin/waybackurls | ✅ | 🟢 | |
| hakrawler | ❌ | — | — | — | 🔴 MISSING | |
| feroxbuster | ❌ | — | — | — | 🔴 MISSING | |
| ffuf | ✅ | (go) | /usr/bin/ffuf | ✅ | 🟢 | `-version` flag unsupported → health by execution |
| dirsearch | ❌ | — | — | — | 🔴 MISSING | |
| gobuster | ✅ | — | /usr/bin/gobuster | ✅ | 🟢 | |
| burpsuite | ✅ | Community (wrapper) | /usr/local/bin/burpsuite | ✅ | 🟢 | installed, GUI tool |

### Vulnerability Research / Scanning

| Tool | Installed | Version | Path | Executes | Health | Notes |
|------|-----------|---------|------|----------|--------|-------|
| nuclei | ✅ | v3.11.1 | /usr/local/bin/nuclei | ✅ | 🟢 | 13,619 templates loaded; live scan OK |
| nuclei-templates | ✅ | v10.4.8 | ~/nuclei-templates | ✅ | 🟢 | updates current |
| dalfox | ✅ | v3.2.2 | /usr/local/bin/dalfox | ✅ | 🟢 | |
| sqlmap | ✅ | latest | /usr/bin/sqlmap | ✅ | 🟢 | |
| nikto | ✅ | — | /usr/bin/nikto | ✅ | 🟢 | |
| testssl | ❌ | — | — | — | 🔴 MISSING | |
| semgrep | ❌ | — | — | — | 🔴 MISSING | |
| trivy | ❌ | — | — | — | 🔴 MISSING | |
| grype | ❌ | — | — | — | 🔴 MISSING | |
| wpscan | ✅ | (docker wrapper) | /usr/local/bin/wpscan | ✅ | 🟡 | wrapper halts if Docker daemon down |
| zaproxy | ❌ | — | — | — | 🔴 MISSING | referenced in TOOLS.md (docker baseline) |

### Network

| Tool | Installed | Version | Path | Executes | Health | Notes |
|------|-----------|---------|------|----------|--------|-------|
| nmap | ✅ | 7.94SVN | /usr/bin/nmap | ✅ | 🟢 | |
| naabu | ✅ | (pd) | /usr/local/bin/naabu | ✅ | 🟢 | |
| masscan | ❌ | — | — | — | 🔴 MISSING | |

### Mobile / MITM / App

| Tool | Installed | Version | Path | Executes | Health |
|------|-----------|---------|------|----------|--------|
| adb | ✅ | — | /usr/bin/adb | ✅ | 🟢 |
| mitmdump | ✅ | — | ~/.local/bin/mitmdump | ✅ | 🟢 |
| jadx | ✅ | — | /usr/local/bin/jadx | ✅ | 🟢 |
| apktool | ✅ | — | /usr/bin/apktool | ✅ | 🟢 |

### Automation / Agent CLIs

| Tool | Installed | Version | Path | Health |
|------|-----------|---------|------|--------|
| opencode | ✅ | 1.18.28 | ~/.opencode/bin/opencode | 🟢 |
| claude (Claude Code) | ✅ | 2.1.260 | ~/.local/bin/claude | 🟢 |
| bb-hunt (skill wrapper) | ✅ | — | ~/.local/bin/bb-hunt | 🟢 |
| meesho-hunt (alias) | ✅ | — | ~/.local/bin/meesho-hunt | 🟢 |

### Wordlists / Data

| Location | Content | Health |
|----------|---------|--------|
| `/usr/share/wordlists/bb/` | api-endpoints, big, common, raft-large, raft-medium-directories, raft-small-directories | 🟢 |
| `/usr/share/seclists/` | directory exists | ⚪ UNKNOWN — empty listing returned; verify before relying on it |
| `~/nuclei-templates/` | 13,619 YAML templates | 🟢 |

---

## 4. Tool Health Report

### 🟢 HEALTHY (verified live)

subfinder, httpx, nuclei (with templates), ffuf, naabu, dnsx, waybackurls, gau, katana, sqlmap, nmap, nikto, gobuster, assetfinder, dalfox, jadx, apktool, adb, mitmdump, burpsuite, opencode, claude CLI, `bb-hunt`, wpscan (when Docker up).

### 🟡 PARTIAL

| Tool | Problem | Evidence | Impact | Fix |
|------|---------|----------|--------|-----|
| **wpscan** | Depends on Docker daemon | wrapper script runs docker image; `docker ps` fails | unusable while daemon down | start Docker daemon |
| **Docker ecosystem** | CLI + compose installed, daemon down | `docker ps` → cannot connect to `/var/run/docker.sock` | Workspace 2 Postgres + ZAP baseline can't run | `sudo systemctl enable --now docker` |
| **Claude Code config MCP** | `~/.claude.json` defines hackerone+github MCP | MCP keys present | usable but duplicates opencode config | decide single source of truth |
| **backend venv (WS2)** | `pytest` shebang points to pre-move path `/home/mohit/bug-bountyhunt/...` | `scripts/setup.sh` venv activation breaks | tests/venv unreproducible in place | recreate venv at new path |

### 🔴 BROKEN

| Tool | Problem | Evidence | Root Cause | Impact | Fix |
|------|---------|----------|-----------|--------|-----|
| **Docker daemon** | not running | `docker ps` fails | likely never enabled / stopped after boot | compose stack dead | `systemctl enable --now docker` (automatic) |
| **WS2 findings pipeline** | no code creates `Finding` rows | `grep "Finding(" backend` only hits models.py:76; no `POST /api/findings`; `parse_log()` not wired | product gap — dashboard/reports have no data source | implement scan-output→findings parser (manual, prioritize) |
| **WS2 scope enforcement** | `program.scope` stored but never read in `start_scan()` | `api/scans/routes.py` validates only `ARG_RE` regex | design gap | enforce scope match before launch (manual, critical) |
| **bb-hunt wordlist supply-chain** | `sudo` curl download of unpinned wordlist on missing | `bb-hunt.sh` lines 42-46 | risky pattern | pin/download to user dir, checksum (manual) |
| **BountyGrimoire path** | SKILL.md references `/home/mohit/bountyhunt/BountyGrimoire/` | dir empty/missing | dead reference | remove/rewire reference |
| **Me�shoo blocker stale** | APK exists in `.playwright-mcp/` but NEXT_STEPS says blocked | 38MB `Meesho-...apks` file present | handoff never updated | update NEXT_STEPS (automatic) |
| **H1 token plaintext incident** | priceline report documents token pasted in chat | documented in report; rotation unconfirmed | secret hygiene | **rotate token** (manual, security) |
| **WS2 live H1 PAT on disk** | `/.env` contains live-looking H1 token | file inspected (values redacted) | secret hygiene | move to env-only, rotate (manual, security) |
| **WS2 docker image bakes `.env`** | `backend/Dockerfile` `COPY . .` with no `.dockerignore` | Dockerfile line | dev JWT secret in image | add `.dockerignore` (manual) |

---

## 5. Broken Tools & Root Causes

1. **Docker daemon down** — client installed; `systemd` unit not running. Root cause: never enabled at boot. Impact: WS2 Postgres/compose, ZAP baseline, wpscan wrapper all dead.
2. **WS2 findings pipeline absent** — architectural gap between runner NDJSON output and DB. Because of it, FindingsPanel/report endpoints have no data ever.
3. **WS2 scope bypass** — `start_scan()` accepts any host matching `[A-Za-z0-9._:/-]{1,255}` after free signup. Root cause: MVP shortcut. Impact: SSRF + billing abuse + liability.
4. **Evidence ephemerality in WS1** — everything written to `/tmp/opencode`, `/tmp/mitm_captures`. Kiwi + Priceline artifacts deleted. Root cause: no evidence contract.
5. **Secrets sprawl** — live-looking H1 PAT in WS2 `.env`, plaintext incident in WS1, JWT default `change-me-in-production`.
6. **No git in WS1** — findings/scope/creds unrecoverable and unversioned.

---

## 6. Missing Tools

| Tool | Why Missing Matters | Install Priority |
|------|--------------------|------------------|
| **amass** | deeper DNS enumeration for complex scopes | P2 |
| **anew** | dedupe pipeline output (tiny, high value) | P1 |
| **masscan** | fast full-port scans | P3 |
| **feroxbuster** | faster alternative to gobuster/ffuf dir scans | P2 |
| **wfuzz** | flexible web fuzzing | P3 |
| **testssl** | TLS hygiene checks | P3 |
| **semgrep** | static analysis of target source repos | P2 |
| **trivy / grype** | container/OS vuln scanning for WS2 images | P2 (WS2) |
| **whatweb / wappalyzer** | tech fingerprinting | P2 |
| **paramspider / arjun / linkfinder / secretfinder** | parameter/JS mining | P2 |
| **httprobe / hakrawler / dirsearch** | redundant with existing tools | P3 — skip |
| **pdtm** (ProjectDiscovery tool manager) | single-command tool/template updates | P1 |
| **sqlite-vec** | embedding search inside SQLite (memory layer) | P2 |

---

## 7. MCP Audit

### MCP Servers Configured (opencode global: `~/.config/opencode/opencode.json`)

| MCP Server | Type | Command | Env Required | Installed | Connects | Functional | Purpose |
|------------|------|---------|--------------|-----------|----------|------------|---------|
| github | local | `npx @modelcontextprotocol/server-github` | GITHUB_TOKEN ✅ | ✅ | ✅ | ✅ | repo/meta/PR ops |
| memory | local | `npx @modelcontextprotocol/server-memory` | — | ✅ | ✅ | ✅ | knowledge graph |
| sqlite-nifty | local | `uvx mcp-server-sqlite --db-path .../research.db` | — | ✅ | ✅ | ✅ | trading research DB |
| filesystem-nifty | local | `npx @modelcontextprotocol/server-filesystem /home/mohit/Desktop/nifty-research` | — | ✅ | ✅ | ✅ | scoped file access (nifty only!) |
| fetch | local | `uvx mcp-server-fetch` | — | ✅ | ✅ | ✅ | web fetch |
| playwright | local | `npx @playwright/mcp --browser chrome` | — | ✅ | ✅ | ✅ | browser automation |
| chrome-devtools | local | `npx chrome-devtools-mcp` | — | ✅ | ✅ | ✅ | DOM/network control |
| hackerone | local | `npx hackerone-mcp@latest` | H1_USERNAME ✅ H1_API_TOKEN ✅ | ✅ | ✅ | ✅ | H1 programs/reports/hacktivity/submission |

**Claude-side (`~/.claude.json`):** MCP servers: `hackerone`, `github` — both also configured in opencode (duplication, single source-of-truth decision needed).

### MCP Gaps / Issues

- ⚠️ Filesystem MCP is scoped to `nifty-research` only — NOT the bug-bounty workspaces. Read/write of WS1/WS2 via MCP is not exposed to agents.
- ⚠️ No Workspace/project-scoped MCP for bug-bounty (e.g., state-DB access, evidence dir).
- ⚠️ 2 browser MCPs (playwright + chrome-devtools) — redundant but each has strengths; keep both.
- ✅ All 8 connect and are functional in current session (verified by tool availability + live calls: `hackerone_list_my_reports` → `[]`, `get_program_scope` worked).
- ⛔ Any MCP `submit` tool must NOT be auto-called (safety invariant, enforced by prompt in WS2 and by design in WS1).

---

## 8. OpenCode Audit

| Item | Status | Detail |
|------|--------|--------|
| Installed | ✅ | v1.18.28 at `~/.opencode/bin/opencode` |
| Global config | ✅ | `~/.config/opencode/opencode.json` — model `openrouter/openrouter/free`, `max_steps: 99999`, permission `"*": "allow"` |
| Project config WS1 | ✅ | `bug-bounty/opencode.json` — default agent `hackerone-analyst`, instructions `AGENTS.md` + `HUNTING_GUIDE.md`, skills paths, H1 MCP |
| Project config WS2 | ✅ | `bug-bountyhunt.../opencode.json` — minimal (134 bytes) |
| meesho/ subconfig | ⚠️ | omits MCP/skills declarations — relies on merge |
| Agents (global) | ✅ | 12: hackerone-analyst (default for WS1), claude-reviewer, security-auditor, researcher, developer, architect, qa, release-reviewer, performance-reviewer, nifty-analyst, quant-researcher, risk-officer |
| Skills (global) | ✅ | 15 incl. bug-bounty (SKILL.md, TOOLS.md, LESSONS.md, scripts/bb-hunt.sh) |
| Hooks | ❌ | none configured |
| Permissions | ⚠️ | `"*": "allow"` at global + workspace — **no read-only default, no ask-gates** |
| max_steps | ⚠️ | 99999 — unbounded autonomous loops possible |
| Providers | ✅ | OpenRouter free (OPENROUTER_API_KEY SET); claude CLI available separately |
| Missing env | ⚠️ | `ANTHROPIC_API_KEY` ❌, `OPENAI_API_KEY` ❌, `HF_TOKEN` ❌ (WS2 generator needs them) |

### OpenCode Current Architecture

```
User (xfce4-terminal / .desktop launcher)
   ↓
OpenCode v1.18.28
   ├─ model: openrouter/free (cheap, default)
   ├─ permission: "*": "allow"   ←  ⚠️ no gates
   ├─ agents: hackerone-analyst (default) / claude-reviewer / …
   ├─ skills: bug-bounty (SKILL/TOOLS/LESSONS + bb-hunt.sh)
   ├─ MCP: github, memory, sqlite-nifty, filesystem-nifty, fetch, playwright, chrome-devtools, hackerone
   └─ workspace: /home/mohit/Desktop/projects/bug-bounty
       ├─ instructions: AGENTS.md + HUNTING_GUIDE.md
       └─ outputs: markdown reports + /tmp artifacts  ←  ⚠️ ephemeral
```

### What Is Missing from OpenCode

1. Per-agent permission scoping (hunter agents should be read-only for bash unless gated)
2. Hooks (e.g., post-tool log evidence, secret redaction)
3. A project-scoped state/evidence MCP (filesystem access to `bug-bounty/evidence`, a state DB)
4. Model routing between agents (cheap for recon, strong for validation)
5. Env keys for Anthropic/OpenAI/HF
6. Compaction/tail config is set; but evidence of actual compaction hygiene unknown.

---

## 9. Workspace 1 Analysis (`bug-bounty/`)

Purpose: dedicated authorized HackerOne hunting workspace, opencode-driven.

### Architecture Map

| Stage | Status | Implementation |
|-------|--------|----------------|
| Input | ✅ | opencode default agent + instructions; desktop launcher |
| Target Management | 🟡 PARTIAL | only `meesho/` follows folder+SCOPE standard; Kiwi/Kayak orphaned at root |
| Recon | ✅ | `bb-hunt.sh --probe` (subfinder→httpx), symlinked at ~/.local/bin |
| Enumeration | 🟡 | `bb-hunt.sh --fuzz` (ffuf, WAF-skip logic), TOOLS.md routing |
| HTTP Discovery | ✅ | httpx + chrome-devtools MCP |
| Scanning | ✅ | `bb-hunt.sh --nuclei` (13,619 templates, rate-limit 5), dalfox, nikto, sqlmap, wpscan |
| Vulnerability Detection | 🟡 | nuclei auto + MANUAL (kiwi cache-leak was manual) |
| Validation | 🟡 | manual curl; claude-reviewer agent exists but **never run** (no evidence) |
| Evidence | 🔴 MISSING | `/tmp` only — **artifacts wiped**, nothing persistent |
| Reporting | 🟡 | 3 hand-written markdown drafts, no template tooling |
| Submission | 🟡 | H1 MCP works (**0 reports ever submitted**, verified: `hackerone_list_my_reports → []`) |

### Automation Inventory

- `start-bugbounty.sh` + `.desktop` — launcher ✅
- `bb-hunt.sh` — recon pipeline ✅ (live verified)
- H1 MCP — scope/hacktivity/submit ✅ (live verified)
- `meesho/EMULATOR_ROOT.md` + mitmdump — root emulator pipeline 🟡
- Cron — ❌ no bug-bounty jobs (only nifty daemon)
- NO scheduler, NO notifications, NO dedup, NO state/DB.

### Scorecard

| Dimension | Score |
|-----------|-------|
| Automation | 5/10 |
| Reliability | 3/10 |
| Reproducibility | 3/10 |
| Observability | 2/10 |
| Security | 3/10 |
| Organization of State | 2/10 |

---

## 10. Workspace 2 Analysis (`bug-bountyhunt by ai with saas/`)

Two products in one repo: **BountyGrimoire** (local AI hunt tool) + **SecScanAI** (hosted SaaS wrapping the same engine).

| Layer | Tech | Status |
|-------|------|--------|
| Backend | FastAPI 0.115, SQLAlchemy 2.0, Alembic | ✅ runnable, **37 tests pass (verified)** |
| DB | PostgreSQL 16 (compose) / SQLite (tests) | ⚠️ needs Docker; local venv pytest broken |
| Auth | JWT (HS256, 7-day) + bcrypt | ✅ implemented, ⚠️ default secrets |
| Billing | Stripe Checkout + webhooks | ⚠️ 501 until keys set |
| Scanner | subprocess claude/opencode, 17 hunters | ✅ exists; ⚠️ findings never persisted; `bypassPermissions` |
| Frontend | Next.js 15.1.4, React 19 | ⚠️ built, Playwright found regex bug (fix uncommitted) |
| Deploy | Docker compose | 🔴 daemon down; no TLS/registry/CI |

### Critical Findings (evidence-based)

1. **B1 — Findings pipeline does not exist.** No code parses scan NDJSON into `Finding` rows; no create endpoint. UI findings/reports operate on rows that can never be created. **Product core gap** — README claim unimplemented.
2. **B2 — Arbitrary-target scanning (SSRF/abuse).** `start_scan()` checks only `ARG_RE`; `program.scope` never consulted; free signup; no rate limit; LLM runs with `bypassPermissions`. Any user can scan `169.254.169.254` or third-party hosts at the API host's network + billing.
3. **B3 — Scope guardrail not available to SaaS subprocess.** `runner.launch()` cwd=`backend/scanner/` — no `CLAUDE.md` there (it lives at repo root). The consent/scope rules rely on prompts only.
4. **B4 — In-memory `_PROCS`.** Restart → scans stuck `"running"` forever. No watchdog/timeouts.
5. **B5 — Dangerous secrets.** Default JWT `change-me-in-production`; compose `dev-only-secret...`; live H1 PAT in root `.env` (gitignored but on disk); backend Dockerfile `COPY . .` bakes `.env` in image.
6. **B6 — No observability** beyond uvicorn access logs.
7. **B7 — Stale claims.** "Browser verification pending" is stale — Playwright logs exist and found the `pattern="[-A-Za-z0-9_]+"` regex bug; the fix sits uncommitted in git diff.
8. **B8 — Local-tool evidence (real Mozilla hunts in sessions/) does NOT flow through SaaS.** 17/17 hunter run, findings marked CONFIRMED/NON_QUALIFYING — but the API has never produced a finding end-to-end.

### Scorecard

| Dimension | Score |
|-----------|-------|
| SaaS completeness | 4/10 |
| Scanner maturity | 4/10 |
| Security | 2/10 |
| Test coverage | 5/10 |
| Production-readiness | 2/10 |
| Observability | 1/10 |

---

## 11. Workspace Comparison

| Capability | WS1 (hunting) | WS2 (SaaS) | Better | Recommendation |
|------------|--------------|------------|--------|----------------|
| Recon (bb-hunt) | ✅ live | 🔴 partial (prompt) | WS1 | port WS1's `bb-hunt.sh` into WS2 engine |
| Scope map | ✅ SCOPE.md/AGENTS | ❌ | WS1 | reuse pattern |
| 17 hunter agents | ❌ | ✅ | WS2 | keep as engine |
| Independent validator | ⚠️ prompt/agent never used | ⚠️ prompt-only (hunt.md Step 7) | WS2 | elevate to code |
| Findings DB | ❌ | ⚠️ model exists, pipeline missing | WS2 (fix B1) | fix B1 first |
| Evidence persistence | ❌ /tmp | ❌ | neither | build evidence contract |
| Report generation | ✅ 3 drafts manual | ✅ template endpoint | WS2 | template + WS1 human context |
| Submission | ❌ 0 submitted | ⛔ never auto | — | human gate, simplify path |
| Auth/JWT | n/a | ✅ | WS2 | — |
| SaaS/UI | ❌ | ✅ | WS2 | — |
| State/queue | ❌ | ⚠️ in-memory | neither | add saga/queue |
| Testing | ❌ | ✅ 37 tests | WS2 | extend coverage |
| Security posture | 3/10 | 2/10 | WS1 | fix both |

**Merge verdict:** **Selective merge — one platform, two modes.** The 17-hunter engine + SaaS shell of WS2 should become the *forward system*; WS1's hardened recon pipeline (`bb-hunt`), scope discipline (AGENTS.md/SCOPE.md pattern), honest-report style, and the Kiwi/Kayak/Priceline/Meesho program knowledge should become its content and tools. Do NOT bolt WS2's buggy scanner onto WS1's folders; instead, WHICH-ONE architecture:

- **Mode A — Local CLI (WS1 evolution):** opencode + `hackerone-analyst` agent + `bb-hunt` + H1 MCP + evidence dir + git. Used daily by you.
- **Mode B — SaaS (WS2 evolution):** SecScanAI for productization. Used after B1/B2/B4/B5 fixed.

Both share: 17-hunter skill library, scope maps, evidence contract, findings schema.

---

## 12. Existing Automation

| Automation | Works | Trigger | Notes |
|------------|-------|---------|-------|
| opencode agent bootstrap | ✅ | session | default agent + instructions |
| H1 MCP scope/hacktivity | ✅ | agent | live verified |
| bb-hunt recon chain | ✅ | manual/agent | single command subfinder→httpx→ffuf→nuclei |
| Desktop launcher | ✅ | click | xfce4-terminal + opencode |
| WS2 17-hunter run (local tool) | ✅ (real Mozilla hunts) | CLI command | sessions/JSON evidence exists |
| WS2 scanner subprocess | 🟡 | API | output never persisted (B1) |
| Priceline MITM pipeline | 🟡 | manual | artifacts wiped |
| cron bug-bounty jobs | ❌ | — | none exist |

## 13. Missing Automation

1. Scheduled/diff-based recon (cron/systemd timer + state.json)
2. Evidence persistence contract (per-finding dir)
3. Notification on new assets/findings (ntfy/Telegram)
4. Findings DB + submission state tracking
5. Dedup against own prior findings + hacktivity
6. Automated PoC re-validation (sandboxed)
7. Report bundler (template + attachments)
8. Watchdog/orphan reaping for scans
9. Token/cost accounting for agent runs
10. Model routing (cheap→strong cascade)

---

## 14. Multi-Agent Architecture

**Research-backed principle:** "The most expensive multi-agent system is one that doesn't need to be multi-agent" (Anthropic engineering). 17 parallel hunters are justified because each drills one vuln class — but each must be independently resumable and cheap.

```
                    ┌──────────────────┐
                    │   Orchestrator   │  frontier model, owns plan/state
                    └────────┬─────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
 Recon Agent            Web Agent            Vuln Agent ×N (17 skill types)
 (assets/DNS)           (URLs/JS/API)        (idor, ssrf, sqli, xss, …)
       │                     │                     │
       └─────────────────────┼─────────────────────┘
                             ▼
                    Validation Agent    (evidence-gated: ≥0.85 + PoC)
                             │
                             ▼
                      Dedup Agent
                             │
                             ▼
                  Evidence Agent (persist artifacts)
                             │
                             ▼
                   Report Agent (template draft)
                             │
                             ▼
                   HUMAN REVIEW GATE (submission)
```

### Agent Evaluation (do we need it?)

| Agent | Purpose | Verdict |
|-------|---------|---------|
| Orchestrator | decompose, route, checkpoint | ✅ REQUIRED |
| Recon (assets/DNS) | subfinder/amass/dnsx | ✅ merges with WS1 bb-hunt |
| Web (URLs/JS/API) | katana/gau/JS mining | ✅ |
| 17 Vuln Hunters | one class each | ✅ (WS2 library) |
| Validation | re-run PoC, response-diff, scope check | ✅ (elevate prompt→code) |
| Dedup | own findings + hacktivity | ✅ cheap, real value |
| Evidence | persist artifacts | ✅ new |
| Report | template+attachments | ✅ |
| Monitoring | rate-limit/ban detection, watchdog | ✅ cheap |
| Learning | lessons/memory | ⚠️ later phase |
| Research Agent | web/OSINT via fetch | ⚠️ optional — use Research skill inline |

---

## 15. Agent Responsibilities (detailed)

Each hunter spec (from WS2 library): input = trimmed program context (scope, rules, UA, proxy) + target; output = structured finding JSON (target, vuln_class, endpoint, evidence, confidence, scope_check, qualifying). Tools = its own skill namespace; MCP deps = none directly (tools are shell). Model = cheap tier (Haiku-class / openrouter-free). Memory = short-term context + DB checkpoint. Failure modes = rate-limit hit (STOP+backoff), timeout (retry queue), parse fail (schema re-run). Auto-run = yes within authorized scope; **human approval = ALWAYS for submission.**

---

## 16. MCP Architecture

| Layer | Servers | Reasoning |
|-------|---------|-----------|
| Core | hackerone, github, fetch | needed by most agents |
| Specialized | playwright, chrome-devtools | browser/DOM agents only |
| Research | fetch, memory(knowledge graph) | documentation/OSINT |
| Project | **NEW: bug-bounty-state** (SQLite + evidence dir) | program/finding/scan state for both modes |
| Dangerous | H1 **submit** tools, bash with `"*" allow` | must stay human-gated; WS2 already prompt-bans it |

---

## 17. Model Strategy

Per research (FrugalGPT cascade, Anthropic multi-agent, pricing):

| Task Class | Model Tier | Rationale |
|------------|-----------|-----------|
| Recon parse, classification, summarization | Cheap (Haiku-class / openrouter free) | indistinguishable on grunt work |
| Hunters (17×) | Cheap-Medium | each does bounded task; escalate on low confidence |
| Validation/exploit judgment | Strong (Sonnet/Opus-class) | quality gate matters most |
| Orchestrator planning + final report | Strongest | 80% of variance explained by tokens; budget here |
| Fallback chain | any available | on 429/5xx/timeout, retry with backoff |

**Warnings:** CLI subagent model routing in Claude Code was historically unreliable (GitHub issue #43869, fixed only in v2.1.146+ for some paths) — **route models at parent level** (one process = one model) and verify from transcripts. Validate JSON schema on every response regardless of provider.

---

## 18. Data Architecture

Entities: Program, Scope (asset/domain), Asset/Subdomain, IP, Port, Service, URL, Endpoint, Parameter, Technology, Finding, Vulnerability, Evidence, Scan, Job, AgentRun, Report, ResearchNote.

**Recommendation:** SQLite (single file, FTS5) for solo/local; PostgreSQL in WS2 when multi-tenant. Findings/Jobs/Evidence tables in both modes share the same schema so the local and SaaS modes interchange data.

- Use **SQLite + sqlite-vec** for semantic memory (per research: vector DB unnecessary below ~1M vectors; FTS5 BM25 covers text search). Skip standalone vector DB.
- Queue: RQ/Arq class, job=saga state machine persisted in own DB; Redis optional (only if replay/audit log needed). Kafka = overkill. Always write run state to our own store (never Celery result backend in Redis).

## 19. Memory Architecture

| Layer | Mechanism |
|-------|-----------|
| Short-term | context window; orchestrator persists plan BEFORE big tool dumps (truncation survival) |
| Workflow state | Job/AgentRun rows: `status, step_index, retry_counter, context, history, deadline` (saga pattern) |
| Long-term | SQLite: findings, bans/rate-limits/dismissals with embedding column (`sqlite-vec`), FTS5; namespaced by program/target |
| Vector search | only if/when corpus grows; not now (research: unnecessary below ~1M vectors) |

## 20. Queue / Worker Architecture

- **Job lifecycle:** created → queued → running → validating → reviewed → submitted → done | failed → retry (backoff 30s→60s→120s→240s, cap 1h aligned to H1 15-min rate reset) → DLQ → human review.
- **Saga pattern** (persisted state machine) beats heavy orchestrators for 17 agents on one box.
- **Crash-resumable:** checkpoint per agent; resume from step index; reaper for stuck jobs (RQ SIGKILL leaves `started` jobs — cleanup required).
- **Concurrency cap:** research says cap probing agents (recommended ≤4 concurrent on one WAF-sensitive target; WS2 currently fires 17 in parallel — flag for safety review).

## 21. Security Architecture

Risks identified (evidence in §5/§10): arbitrary command execution (`"*": "allow"`, `bypassPermissions`), prompt injection from untrusted web content, SSRF via arbitrary-target scans, secret leakage (plaintext PAT, baked `.env`), localStorage JWT, no sandboxing, unverified wordlist download with sudo.

**Defenses (research-backed):**
- Filesystem isolation + network isolation: bubblewrap (like Anthropic Claude Code sandboxing) or Docker per agent; allowlisted egress proxy (logged) — credentials NEVER inside sandbox.
- `--network=none` for PoC/exploitation containers; scope-check before every target injection (hard rule: instantiate containers with post-scope-check target only).
- Validate model tool args as arg lists, never `shell=True`/string shell.
- Secrets: env-only, `.dockerignore`, no secrets in images, rotate exposed tokens.
- Permission model: read-only default, `ask`/`deny` per tool class; remove `"*": "allow"` for autonomous runs; keep human gates on submission.
- Untrusted content (web pages/repos being analyzed) is adversarial input — parse in isolated no-tool/no-egress sandbox (OWASP LLM01 — no model-level fix; isolation is the control).

## 22. Observability

**Exists:** default uvicorn access logs only. WS1: markdown prose. **Missing:** logs, metrics, traces, cost.

**Design:** OTel GenAI semantic conventions (`gen_ai.request.model`, `gen_ai.usage.input_tokens/output_tokens`); per-run token/cost attribution; six production metrics (token usage/run, tool success rate, LLM latency p50-p99, loop iterations, context utilization, E2E latency); **north-star quality metric = false-positive submission rate** (target: near 0; evidence-gated progression ≥0.85 + response-diff not payload-echo). Structured run logs parsed from CLI JSONL transcripts. Structured logging config for backend.

## 23. External Research Findings

Key sources (full list in `research_report.md` on disk and section Sources):
- Anthropic — multi-agent research system (orchestrator-worker, token economics ~15× chat, resumability) ✓
- Anthropic — Claude Code sandboxing (filesystem + network isolation, egress proxy, credentials outside) ✓
- FrugalGPT (arXiv 2305.05176) — LLM cascade; judge/verifier is the hard part ✓
- AutoMix (NeurIPS 2024) — cheap self-verification router ✓
- OTel GenAI semantic conventions ✓
- MCP spec + Wiz MCP security analysis — confused deputy, tool poisoning, OAuth 2.1/PKCE, egress allowlists, supply-chain pinning ✓
- OWASP LLM01 prompt injection — structural, no model fix; isolation is the control ✓
- chudi.dev bug-bounty automation (3-month practice) — evidence-gated progression (≥0.85), SQLite+sqlite-vec memory, response-diff validation, ban circuit-breaker, max 4 concurrent probers ✓/⚠
- Claude Code subagent model routing bug (#43869) — route at parent level ✓
- sqlite-vs-vector-db research (FTS5+RRF below ~1M vectors) ✓/⚠

**UNVERIFIED:** Amazon Science "Keyword Search Is All You Need" (AAAI 2026), tygartmedia absolute pricing (conflicts with official pricing — trust official), MassTransit mirror domain, Sandlock preprint (not peer-reviewed), some Celery/Redis specifics.

## 24. Recommended Final Architecture

```
                         USER (human)
                              │
                              ▼
                    CONTROL PLANE ────────────► Dashboard (WS2 frontend) / CLI (opencode)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              ORCHESTRATOR         STATE DB (SQLite/Postgres)
        (frontier model, saga)     programs·scans·findings·evidence·jobs
                    │
                    ▼
             JOB QUEUE (Arq/RQ) ── retry/backoff ──► DLQ ──► Human review
                    │
                    ▼
               WORKERS (sandboxed)
        ┌──────────┼───────────┐
        ▼          ▼           ▼
   Recon Agent  Hunter×17   Validator
        │          │           │
        └──────────┼───────────┘
                   ▼
              DEDUP + EVIDENCE
                   │
                   ▼
             REPORT AGENT
                   │
             HUMAN APPROVAL GATE
                   │
                   ▼
             SUBMIT (manual/H1 MCP gated)
                   │
              OBSERVABILITY (OTel + cost)
```

Deployment: local single-node first (SQLite, Arq, cron timer); SaaS later on VPS with Postgres, TLS-terminated reverse proxy, secrets manager, container sandbox, egress proxy.

## 25. Implementation Roadmap

| Phase | Scope | P0/P1 | Est. Effort | Risk |
|-------|-------|-------|-------------|------|
| Phase 0 — Cleanup | remove junk (WS1 boot images/Magisk, empty docs/, dead refs, 63MB .opencode stub), fix docker daemon, git-init WS1 | P0 | small | low |
| Phase 1 — Foundation | rotate H1 token; `.env` hygiene; `.dockerignore`; WS2 venv recreate; commit WS2 regex fix; scope-enforcement in `start_scan()`; findings pipeline (B1) | P0 | medium | high (security) |
| Phase 2 — Recon Automation | cron/systemd timer + `bb-hunt` + state.json diff + notify (ntfy) | P1 | medium | low |
| Phase 3 — Agent Orchestration | saga job state machine, checkpoint/resume, watchdog, concurrency caps | P1 | medium | medium |
| Phase 4 — Validation | validator code (response-diff, scope re-check,≥0.85), sandbox PoC | P1 | medium | medium |
| Phase 5 — Evidence | per-finding evidence dir + DB links, screenshots/HAR capture | P1 | small | low |
| Phase 6 — Reporting | report template + bundler; wire H1 MCP attachment upload (human-gated) | P1 | small | low |
| Phase 7 — SaaS | fix B1-B6, frontend e2e, oauth/mfa/RBAC later, Stripe keys | P2 | large | high |
| Phase 8 — Observability | OTel metrics, cost per run, FP-rate dashboard | P2 | medium | low |
| Phase 9 — Production Hardening | sandboxing (bubblewrap/Docker), egress proxy, secrets manager, CI, TLS | P2 | large | medium |

## 26. Priority Matrix

P0 (do first): rotate token · submit/close Kiwi · docker daemon · git-init WS1 · scope enforcement + findings pipeline (WS2) · secret hygiene (.env/.dockerignore) · evidence dir (stop /tmp).
P1: cron diff recon + notify · saga/queue + watchdog · validator code · report template · pdtm + anew · WS2 e2e test.
P2: SaaS hardening · OTel · model routing · sandboxing · amass/feroxbuster/semgrep install · sqlite-vec memory.
P3: masscan/wfuzz/testssl · VPS deployment · teams/RBAC/oauth.

## 27. Risks

- **Secret exposure** (H1 PAT on disk; token plaintext incident) — rotate now; monitor.
- **SSRF/abuse liability** if WS2 deployed as-is — scope enforcement must land pre-deploy.
- **Prompt injection** from analyzed web content — sandbox per agent (§21).
- **WAF/rate-limit bans** from 17 parallel probers — cap concurrency, backoff, circuit-breaker.
- **Runaway AI cost** with 17 agents × free→paid models — cost attribution + alerting.
- **Data loss** (no git, /tmp evidence) — git + evidence contract.
- **Tool supply-chain** (sudo curl wordlist) — pin/checksum.

## 28. Quick Wins

1. `sudo systemctl enable --now docker`
2. `git init` + commit WS1 (with .gitignore for secrets/binaries)
3. Install `anew` + `pdtm` (one command each)
4. Move evidence writes out of `/tmp` (env var + contract)
5. Update `meesho/NEXT_STEPS.md` (APK exists)
6. Commit WS2 regex fix + recreate venv
7. Add `.dockerignore` to WS2 backend
8. Verify wordlists at `/usr/share/seclists/` (was empty listing — recheck)

## 29. Long-Term Improvements

- VPS continuous recon + diff notifications
- Model cascade with schema-gate validation and drift re-validation
- Fully sandboxed agent runtime (bubblewrap + egress proxy)
- SaaS multi-tenant production hardening (OAuth/MFA/RBAC, durable queue, object storage for evidence)
- OTel observability with cost dashboards

## 30. Final Recommendations

1. **Keep WS1 as your daily local hunting mode** — fix its backbone (git, evidence, state, cron diff recon, actually submit Kiwi).
2. **Keep WS2 as the productized SaaS** — but DO NOT deploy publicly until B1 (findings pipeline), B2 (scope enforcement), B4 (durable state), B5 (secrets) are fixed. The 17-hunter engine and local-tool evidence are genuinely valuable.
3. **Adopt the shared schema:** Program→Scope→Asset→Finding→Evidence→Report→Submission in both modes.
4. **Adopt evidence-gated progression + human submission gate as immutable rules.**
5. **Route models cheap-first with strong validation; never auto-submit.**
6. **Sandbox all content-processing agents; keep secrets outside sandboxes.**
7. **Measure FP-rate and cost per run from day one.**

---

## Sources

- System/tool audit: direct inspection (this session).
- MCP: live tool access + `list_mcp_resources`.
- OpenCode: `~/.config/opencode/opencode.json`, agents/, skills/.
- Claude: `~/.claude.json` (names only inspected).
- WS1/WS2: two parallel explore-agent deep audits (read-only).
- External: Anthropic multi-agent research; Anthropic Claude Code sandboxing; MCP spec/Wiz; FrugalGPT (arXiv:2305.05176); AutoMix (NeurIPS 2024); OTel GenAI conv; OWASP LLM01; Claude Code subagent model routing issue #43869; chudi.dev bug-bounty automation; sqlite-vs-vector-db research; practitioner guides (SkillShikshya/Netlas/HackerNoon/BugHunterTools).
- Research deliverable on disk: `/home/mohit/research_report.md`.

*End of audit.*