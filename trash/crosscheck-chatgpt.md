# Bug Bounty Workspace — Workflow Cross-Check (for ChatGPT)

> Paste this in ChatGPT and ask: **"Is this a well-structured bug bounty pipeline? What's missing, what's over-engineered, what should change?"**

---

## Context

I've built an automated bug bounty hunting workspace (WS1) for a solo hunter. It targets HackerOne programs, currently focused on Meesho (meesho_bbp). The workspace lives at `~/Desktop/projects/bug-bounty/`.

I want a second opinion on whether the pipeline is sound, has gaps, or is over-engineered.

---

## Actual File Structure

```
bug-bounty/
├── start-bugbounty.sh              ← Desktop launcher (menu: new/continue/quit)
├── opencode.json                   ← Default agent: hackerone-analyst, registered subagents
├── AGENTS.md                       ← Agent routing rules (who does what)
├── WORKFLOW.md                     ← Operational flow (all 13 stages documented)
├── IF_ELSE.md                      ← Single routing source (if/else decision tree)
├── HUNTING_GUIDE.md                ← Learning path
├── prompts/
│   └── prob_hunter_prompt.txt      ← Bayesian probability scoring system prompt
├── <program>/                      ← Per-target (meesho/, general/)
│   ├── scope.yaml                  ← Machine-readable engagement contract
│   ├── SCOPE.md                    ← Human-readable scope
│   └── NOTES.md                    ← Target notes
├── recon/                          ← Shared multi-program pipeline
│   ├── recon_pipeline.py           ← Phase 1: subfinder → dnsx → httpx → gau → normalize
│   ├── intelligence.py             ← Phase 2: deterministic scoring → SQLite → candidate_report.md
│   ├── scanner.py                  ← Phase 3: scope-aware nuclei + optional ffuf
│   ├── application_model.py        ← Phase 4: URL → actors/objects/actions (no LLM)
│   └── data/<program>/             ← Per-program output
│       ├── raw/                    ← subfinder.txt, dnsx.txt, httpx.jsonl, gau.txt
│       ├── assets.json             ← Live hosts (7 for meesho)
│       ├── endpoints.json          ← Deduped URLs (2126 for meesho)
│       ├── recon.db                ← SQLite (assets + endpoints + candidate_findings)
│       ├── candidate_report.md     ← Top-40 scored surfaces
│       ├── top_priority.json       ← Ranked JSON
│       └── application_model.json  ← App structure (actors/objects/actions)
├── reports/                        ← Submitted reports
└── evidence/                       ← PoCs, handoffs
```

Registered agents (in `~/.config/opencode/agents/`):
- `hackerone-analyst` — main orchestrator (default), H1 MCP tools, scope verification, submit
- `prob-hunter` — Bayesian vulnerability probability ranking (LLM call, cost-guarded)
- `security-auditor` — vuln analysis, OWASP, secret hygiene
- `claude-reviewer` — independent second-opinion (read-only, different model)
- `researcher` — web/GitHub research
- `developer` — code tasks
- `qa` — testing
- `architect` — system design
- `performance-reviewer` — optimization

Skills (in `.opencode/skills/`):
- `triage` — finding state machine (discovered → valid/duplicate/wontfix → ready-for-report)
- `grill-me` → `grilling` — report-ready interrogation (scope → root cause → impact → repro → CVSS)
- `handoff` — session continuity (save state to `evidence/handoffs/`)

---

## Pipeline Flow (13 Stages)

### Stage 0: Entry (Launcher)
`start-bugbounty.sh` → desktop click → menu: [1] New scan [2] Continue [3] Quit
- New: agent picks program → checks existing folders (no duplicates) → creates `program/` with scope.yaml
- Continue: lists existing targets → user selects → resume session

### Stage 1: Scope Verify (Legal Gate)
```bash
hackerone_get_program_scope(handle)    # H1 API — structured scopes
hackerone_get_program_scope_exclusions(handle)
```
Decision: roots = in-scope, excluded = NEVER touch. Runs before any recon.

### Stage 2: Recon (Two Chains)
**Chain A — Full Pipeline (recommended):**
```bash
python3 recon/recon_pipeline.py --program <program>
# subfinder → dnsx → httpx (tech-detect) → gau → normalize → dedupe → filter (scope.yaml)
# Output: assets.json (hosts), endpoints.json (URLs), run_meta.json
```

**Chain B — Quick Sanity:**
```bash
bb-hunt <domain>          # subfinder → httpx → ffuf → nuclei (fast, /tmp output)
bb-hunt <domain> --probe  # subs + alive only
```
bb-hunt output is separate (/tmp), doesn't feed into intelligence.py.

### Stage 3: Safe Scan
```bash
python3 recon/scanner.py --program <program> --dry-run   # always first
python3 recon/scanner.py --program <program>              # nuclei on in-scope hosts
python3 recon/scanner.py --program <program> --ffuf-host <host> --ffuf-wordlist <wl>
```
- Host allowlist = scope.yaml roots ONLY
- Destructive tags excluded (dos, rce-destructive, takeover-writes)
- Rate-limited (30 rps = rpm/2), per-host sequential
- Results → `recon.db` candidate_findings table

### Stage 4: Secrets (Cheap Win)
```bash
trufflehog filesystem <target-dir> --only-verified --no-update
```
Scans .git, JS bundles, configs for hardcoded creds. Verified = confirmed working.

### Stage 5: Intelligence (Deterministic Scoring — FREE)
```bash
python3 recon/intelligence.py --program <program> --top 40
```
URL pattern scoring (api_surface, auth, admin, config_leak, idor_param, redirect) →
SQLite + `candidate_report.md` (top-40 ranked surfaces).
No LLM. Deterministic. Free.

### Stage 6: Application Model (Deterministic — FREE)
```bash
python3 recon/application_model.py --program <program>
```
URL paths → actors (supplier/admin/consumer), objects (order/invoice/file),
actions (create/delete/export/refund), sensitive params, auth surfaces.
No LLM. Understanding layer beyond "interesting URLs".

### Stage 7: Probabilistic Ranking (LLM — COST-GUARDED) ⚠️ MANUAL TRIGGER
```
@prob-hunter recon/data/<program>/candidate_report.md
```
Bayesian-style: prior (URL patterns, tech stack) + evidence (scan hits) → posterior %.
Output: Prior Table, Ranked Hits, Hypothesis Engine (top 3-5 vuln guesses), Test Plan.
Verdict bands: 0-9% SKIP, 10-24% LOW, 25-49% MEDIUM, 50-74% HIGH, 75%+ CRITICAL-HUNT.

**Why cost-guarded:** This is an LLM call (consumes OpenRouter credits). Only runs on
shortlist (top-40 from intelligence.py), never on full recon dump. Deterministic stages
(breadth) are free; this is depth.

### Stage 8: Manual Testing
prob-hunter's TEST PLAN → manual verify top-down:
- IDOR/BOLA: chrome-devtools, cross-account object access
- SQLi: manual payloads, sqlmap --batch --risk 1 if confirmed
- XSS: dalfox confirm
- SSRF/redirect: manual ?url= ?next= payloads
- Path traversal: ../, %00
- Info disclosure: curl, nuclei
All READ-ONLY first. Non-destructive. In-scope only.

### Stage 9: Triage (Skill)
```
Skill: triage
```
State machine: discovered → needs-info | valid | duplicate | wontfix → ready-for-report.
Hard rule: `valid` only after confirmed reproduction. NEVER auto-submit.

### Stage 10: Grilling (Skill)
```
Skill: grill-me → grilling
```
Decision-tree: scope → class/root cause → impact/CVSS → reproducibility →
evidence quality → prior art → report shape. Agent gathers facts (curl, H1 MCP, hacktivity);
user makes decisions.

### Stage 11: Second Opinion
```
task → claude-reviewer (subagent)
```
Independent Claude Code cross-check: real vuln? PoC solid? severity? report-worthiness?
Read-only. Only for high/critical findings before submission.

### Stage 12: Report (H1 Submit)
```bash
hackerone_submit_report → team_handle, title, vulnerability_information, impact,
                         severity_rating, weakness_id, structured_scope_id
```
Save copy: `reports/<program>/`. AI-assisted disclaimer always included.

### Stage 13: Handoff (Skill)
```
Skill: handoff → evidence/handoffs/<target>-<date>.md
```
Session continuity. NEVER save to /tmp (files wiped).

---

## Current State (Meesho Program)

| Metric | Value |
|--------|-------|
| Program | meesho_bbp (HackerOne) |
| Scope | 7 roots (meesho.com, meeshosupply.com, meeshoapi.com, valmo.in, etc.) |
| Live hosts | 7 |
| Endpoints (deduped) | 2,126 |
| Candidates (score ≥ 40) | 123 (98 unique surfaces after dedup) |
| Nuclei scan results | 0 findings (on exposed hosts) |
| Manual testing | in progress (top-down from candidate_report) |
| Submitted reports | 0 |
| Top candidate (by score) | `supplier.meesho.com/panel/v3/new/root/login?redirect=%2F...` (83) |
| Notable candidate | `admin.meeshosupply.com/api/google/oauth?redirect=%2F` (58) |
| Key blocker | Meesho emulator: APK source missing |
| Separate hunt (Kiwi) | 1 MEDIUM finding (decision: submit or close) |

---

## Known Gaps / Design Questions

1. **bb-hunt vs pipeline disconnect** — bb-hunt outputs to /tmp, doesn't feed intelligence.py. Convention doc only, no code fix. Is this the right separation?

2. **prob-hunter cost guard** — LLM call on shortlist (top-40) only. Credits are the constraint. Is this the right tradeoff vs running on full endpoint list?

3. **application_model → prob-hunter integration** — application_model.json is free context that improves prob-hunter's scoring. Currently optional (prob-hunter works without it). Should it be required?

4. **Hypothesis → hunter routing** — prob-hunter produces vuln-class hypotheses (IDOR, SSRF, SQLi). Currently informal routing to specialized hunter agents. No integration code yet.

5. **No automated ZAP/wpscan** — docker-dependent, manual per-target. Is it worth automating?

6. **No burp-state persistence** — handoff skill saves notes, but Burp project state isn't carried across sessions. Gap or acceptable?

7. **0 findings after 123 candidates + full nuclei scan** — Is the scope too clean, or is the
   scoring/ranking missing something? Valmo.in had 11,221 nuclei requests, 0 matches.

---

## What I Want Cross-Checked

1. **Pipeline completeness:** Is any critical stage missing for a solo bug bounty hunter?
2. **Order:** Is recon → scan → intelligence → application_model → prob-hunter → manual → triage → report the right order?
3. **Over-engineering:** What can I delete or simplify without losing value?
4. **Under-engineering:** What should I add that I'm missing?
5. **Cost efficiency:** Am I burning LLM credits in the right places?
6. **The 0-finding problem:** Any suggestions for why 123 candidates + nuclei produced nothing? (Scope too clean? Scoring wrong? Need different tools?)
