# BUG BOUNTY AUTOMATION SUITE — RELEASE DEPENDENCIES MATRIX

**Document Version:** 1.0.0
**Release Date:** 2026-09-06
**Auditor:** Principal Security Automation Architect & DevSecOps Engineer
**Workspace:** `/home/mohit/Desktop/projects/bug-bounty`
**Git Baseline:** `f1c531c949159695f00f5708a6675c862cb1ffdd`

---

## 1. EXECUTIVE SUMMARY

This document establishes the formal dependency contract for the Bug Bounty Automation Suite. Tools are categorized strictly by their operational requirement tier:
- **Tier 1 (Required Automation Core):** Essential for running the automated reconnaissance, crawler, scanner, intelligence triage, and report generation pipelines.
- **Tier 2 (Optional / Manual Enrichment):** Available on the system for manual deep testing, parameter fuzzing, SQLi verification, mobile APK analysis, and proxying.
- **Tier 3 (AI / Agent Runtime):** Required for autonomous hunt prompt handoff, interactive terminal agents, and MCP integrations.
- **Tier 4 (Diagnostic & Infrastructure):** Local container runtimes and alternative scanners used for lab targets and environment diagnostics.

---

## 2. TIER 1: REQUIRED AUTOMATION CORE

These tools are invoked directly by automated pipeline scripts (`recon_pipeline.py`, `js_miner.py`, `scanner.py`, `report_gen.py`, `notify.py`, `start-bugbounty.sh`).

| Binary | System Path | Installed Version | Primary Invocation Point | Failure Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **`python3`** | `/usr/bin/python3` | 3.12.3 | Core pipeline runtime (`recon/*.py`) | Pipeline aborts; fatal exit code 1 |
| **`subfinder`** | `/usr/local/bin/subfinder` | v2.16.0 | `recon_pipeline.py:135` (Phase 1) | Graceful fallback; logs error; 0 subdomains found |
| **`httpx`** | `/usr/local/bin/httpx` | v1.6.8 | `recon_pipeline.py:180`, `scanner.py:192` | Critical probe fails; aborts phase with exit code 1 |
| **`katana`** | `/usr/local/bin/katana` | v1.1.0 | `js_miner.py:188` (Phase 2) | Logs error; skips JS crawling; returns empty endpoints |
| **`nuclei`** | `/usr/local/bin/nuclei` | v3.11.1 | `scanner.py:212` (Phase 3) | Logs error; skips vulnerability scanning |
| **`gau`** | `/usr/local/bin/gau` | v2.2.3 | `recon_pipeline.py:236` (Phase 1) | Non-fatal warning; continues with 0 archive URLs |
| **`curl`** | `/usr/bin/curl` | 8.5.0 | `notify.py:108`, `report_gen.py:142` | Telegram alert fails; PoC generation unaffected |
| **`jq`** | `/usr/bin/jq` | jq-1.7 | `start-bugbounty.sh` JSON parsing | Menu/stats display fallbacks |
| **`git`** | `/usr/bin/git` | 2.43.0 | Workspace management, diffing | Version tracking fails |

---

## 3. TIER 2: OPTIONAL & MANUAL ENRICHMENT TOOLS

These tools are pre-installed and available on the workstation for targeted manual testing, secondary validation, and specialized scopes (e.g. mobile APKs, WordPress, parameter fuzzing).

| Binary | System Path | Installed Version | Usage Scope | Execution Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- |
| **`dnsx`** | `/usr/local/bin/dnsx` | v1.2.1 | Active DNS brute-forcing / CNAME resolution | Optional active recon; strictly rate-limited |
| **`ffuf`** | `/usr/bin/ffuf` | 2.1.0-dev | Directory & API fuzzing (`scanner.py:332`) | Scoped via `--ffuf-host`; requires valid wordlist |
| **`dalfox`** | `/usr/local/bin/dalfox` | 3.2.2 | Parameter XSS analysis | Manual verification on verified endpoints |
| **`sqlmap`** | `/usr/bin/sqlmap` | 1.8.4#stable | Database injection testing | **MANDATORY:** `--batch --risk 1` (non-destructive) |
| **`burpsuite`** | `/usr/local/bin/burpsuite` | Community 2024+ | Interactive proxy & traffic inspection | Manual authenticated testing |
| **`jadx`** | `/usr/local/bin/jadx` | 1.5.6 | Android APK decompilation | Android scopes only (e.g. Meesho APK) |
| **`nikto`** | `/usr/bin/nikto` | 2.5.0 | Legacy web server configuration scan | Manual fallback |
| **`wpscan`** | `/usr/local/bin/wpscan` | Wrapper/Docker | WordPress vulnerability auditing | Scoped to WordPress targets (`wordpress/`) |

---

## 4. TIER 3: AI & AGENT RUNTIME

Required for autonomous hunting handoffs, terminal AI pair programming, and prompt feeding.

| Component | Path | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **`opencode`** | `~/.opencode/bin/opencode` | 1.18.29 | Autonomous AI terminal agent loaded with `AUTONOMOUS_HUNT_PROMPT.md` |
| **`node`** | `/usr/bin/node` | v22.23.2 | JavaScript runtime for agent MCP sidecars and browser automation |
| **`npx`** | `/usr/bin/npx` | 10.9.8 | Package runner for MCP servers |

---

## 5. TIER 4: DIAGNOSTIC & INFRASTRUCTURE

| Component | Path | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **`docker`** | `/usr/bin/docker` | 29.1.3 | Container runtime for WPScan and local authorized practice labs |
| **`gobuster`** | `/usr/bin/gobuster` | 3.6.0 | Secondary content discovery alternative |

---

## 6. PYTHON RUNTIME & ENVIRONMENT

- **Python Version:** 3.12.3
- **Dependencies:** Standard library only (`sqlite3`, `subprocess`, `urllib.request`, `json`, `pathlib`, `re`, `argparse`, `dataclasses`, `typing`).
- **Optional Parser:** `PyYAML` (optional fallback for `.yaml` scope files; automatically falls back to regex parser if uninstalled).
- **Process Isolation:** All subprocess commands use explicit argument arrays (no `shell=True`) to prevent shell injection.

---

## 7. CREDENTIAL & PERMISSION ENFORCEMENT

- **HackerOne API:** Stored in `.env.h1` (`H1_USERNAME`, `H1_API_TOKEN`). Permissions enforced to `600` on launcher startup.
- **Telegram Notifications:** Stored in `.env.notify` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Permissions enforced to `600`.
- **Sanitization Contract:** `report_gen.py` scrubs `Authorization`, `Cookie`, `X-API-Key`, `Token`, and `Bearer` headers in curl commands, replacing secrets with `[REDACTED]`.
