# Bug Bounty AI Automation — Summary

**Date:** 2026-09-04 · **Overall Health Score: 4.5/10**

> I audited the current environment first and did not blindly modify the system. No files were changed, no secrets are reproduced here, no destructive action was taken.

---

## 1. Current State

| Area | Verdict |
|------|---------|
| Machine | Linux Mint 22.3, healthy; Docker daemon down; tmux/snap/rust missing |
| Tools (20+) | subfinder/httpx/nuclei (13,619 templates)/ffuf/dalfox/sqlmap etc. all work; amass/pdtm/anew/semgrep/zaproxy missing |
| MCP (8 servers) | github · memory · sqlite-nifty · filesystem-nifty · fetch · playwright · chrome-devtools · hackerone — all connect & function |
| OpenCode | v1.18.28, 12 agents, 15 skills; ⚠️ `"*": "allow"`, unbounded max_steps, no hooks |
| Workspace 1 (hunting) | recon works, but **evidence lives in /tmp (wiped), no git, no state, 0 reports submitted** |
| Workspace 2 (SaaS) | 17-hunter engine + FastAPI/Next.js shell, **findings pipeline missing**, scope not enforced, secrets on disk, Docker down |

## 2. Working / Broken / Missing

**Working ✅:** bb-hunt recon chain (subfinder→httpx→ffuf→nuclei), all 8 MCP servers, 17-runner scanner engine (real Mozilla hunt evidence in `sessions/`), 37 backend tests pass, H1 API integration, report drafts (Kiwi/Kayak/Priceline).

**Broken 🔴:** Docker daemon; WS2 findings pipeline; WS2 scope enforcement; WS1 evidence persistence; H1 submission flow (0 reports ever sent); WS2 venv paths; backend image bakes `.env`.

**Missing ⚠️:** git in WS1 · state DB · scheduler/cron recon · notifications · dedup · validator · evidence contract · observability · cost tracking · secrets hygiene · sandboxing.

## 3. Top 10 Problems

1. **Zero submissions ever** — Kiwi MEDIUM (submit-ready) sits unreported; pipeline stops at draft.
2. **Findings pipeline absent in WS2** — scan output never becomes `Finding` rows (product core gap).
3. **SSRF/abuse risk** — `start_scan()` accepts any host, scope never checked (B2).
4. **Exposed secrets** — live-looking H1 PAT in WS2 `.env`; token pasted plaintext in WS1 docs; JWT defaults; no `.dockerignore`.
5. **Evidence ephemerality** — WS1 writes to `/tmp`, artifacts already wiped; no evidence contract.
6. **No version control / state in WS1** — findings, scope, creds unversioned.
7. **Docker daemon down** — blocks compostack, wpscan, ZAP baseline.
8. **Unbounded autonomy** — `"*": "allow"` permissions + `bypassPermissions` + no watchdog/rate caps.
9. **No observability/cost** — 17 agents × LLM spend invisible; FP-rate unknown.
10. **Supply-chain/quality debt** — sudo curl wordlist unpinned; stale claims (meesho blocked though APK exists, "browser verification pending" though Playwright logs found a concrete bug).

## 4. Top 10 Improvements

1. **Rotate the H1 token** and move secrets to env-only (P0, security).
2. **Submit (or close) the Kiwi MEDIUM draft** via H1 MCP, human-gated (P0).
3. **Implement findings pipeline** in WS2: parse runner NDJSON → Finding rows (P0).
4. **Enforce scope in `start_scan()`** — match target against `program.scope` before launch (P0).
5. **git-init WS1** + `.gitignore`; commit state (P0).
6. **Evidence contract** — per-finding dir + screenshots/HAR; never `/tmp` (P0).
7. **Start Docker** + add `.dockerignore` to WS2 backend (P0).
8. **Cron/systemd-timer diff recon** using `bb-hunt` + state.json + ntfy notify (P1).
9. **Saga job state machine** — checkpoint/resume, watchdog, concurrency cap ≤4 probers (P1).
10. **Validator code** — response-diff + scope re-check + confidence ≥0.85 gate (P1).

## 5. Recommended Architecture

**One platform, two modes:**

- **Mode A — Local CLI (daily hunting):** opencode `hackerone-analyst` + `bb-hunt` + H1 MCP + git + evidence dir + SQLite state + cron diff-recon. This is WS1 evolved.
- **Mode B — SaaS (productized):** SecScanAI shell + fixed findings/scope pipelines + durable jobs + sandbox. This is WS2 hardened. **Do not deploy publicly until P0 fixes land.**

Shared core: Program→Scope→Asset→Finding→Evidence→Report→Submission schema; 17-hunter skill library; data/dedup/validator; human submission gate; observability.

```
USER ─► Orchestrator ─► Job Queue ─► Sandboxed Workers (Recon / 17×Hunters / Validator)
                    └── State DB ─► Dedup+Evidence ─► Report ─► HUMAN GATE ─► Submit
```

## 6. Next 7 Actions

1. Rotate exposed H1 token (manual, security-critical).
2. `sudo systemctl enable --now docker`.
3. `git init` WS1 + `.gitignore` + first commit (no secrets).
4. Fix WS2 B1+B2: findings parser + scope enforcement in `start_scan()`.
5. WS2: add `.dockerignore`, recreate venv, commit the regex fix.
6. WS1: adopt evidence-dir contract (no more `/tmp` writes).
7. Decide Kiwi: submit via H1 MCP (human-gated) or close draft.

## 7. Evidence Trail

Full detail: `AI_AUTOMATION_AUDIT.md` · Machine-readable: `AI_AUTOMATION_INVENTORY.json` · Research: `/home/mohit/research_report.md`