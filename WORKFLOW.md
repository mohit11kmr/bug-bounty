# Bug Bounty Workspace — WORKFLOW.md

> Complete end-to-end hunting workflow. Read this with AGENTS.md (structure) + HUNTING_GUIDE.md
> (learning path) + TOOLS.md (if/else tool routing). This file is the OPERATIONAL flow —
> launcher se report tak, har stage ka input/output.

---

## 0. Directory layout (source of truth)

```
bug-bounty/                         ← WORKSPACE (project)
├── start-bugbounty.sh              ← LAUNCHER (desktop click → menu)
├── opencode.json                   ← default agent: hackerone-analyst, prob-hunter subagent + skills
├── AGENTS.md / HUNTING_GUIDE.md    ← structure rules + learning path
├── WORKFLOW.md                     ← (ye file) operational flow
├── prompts/prob_hunter_prompt.txt  ← prob-hunter Bayesian scoring system prompt
├── <program>/                      ← per-target folder (meesho/, general/, ...)
│   └── scope.yaml + SCOPE.md + NOTES.md
├── recon/                          ← shared multi-program pipeline
│   ├── recon_pipeline.py           ← Phase 1: recon → assets.json + endpoints.json
│   ├── scanner.py                  ← Phase 2: safe nuclei/ffuf scan → recon.db
│   ├── intelligence.py             ← Phase 3: deterministic score → candidate_report.md (free breadth)
│   └── data/<program>/             ← per-program output (raw/, json, sqlite)
└── reports/ + evidence/            ← kya submit kiya / PoC
```

> Phase order: recon_pipeline (1) → scanner (2) → intelligence (3) → prob-hunter (4, LLM depth-rank) → manual (5).

---

## 1. ENTRY — launcher (start-bugbounty.sh)

User desktop se click karta hai → menu aata hai:

```
[1] Start NEW scan        [2] Continue EXISTING target     [3] Quit
Existing targets in workspace: [x] meesho  ...
```

| Option | Flow | Output |
|--------|------|--------|
| **1. New scan** | agent `hackerone-analyst` scan karta hai → workspace-existing SKIP → user select → folder create (scope.yaml+SCOPE.md+NOTES.md) → session open | `<program>/` folder ready |
| **2. Continue existing** | existing target list (scope.yaml wale folders) → user select → `--continue` session resume | same session continue |
| **3. Quit** | — | — |

New-target duplicate guard: agar candidate handle kisi existing folder se match kare
(meesho_bbp → meesho), naya folder nahi banta.

**NOTES.md convention (har program folder me):** goal / progress / findings(triage) —
candidate_report.md kuch bata hai wo update karo.

---

## 2. SCOPE VERIFY (har target pe pehla step — legal gate)

```text
IF  scope.yaml pehle se hai:
    READ  program/SCOPE.md + hackerone_get_program_scope + get_program_scope_exclusions
    CONFIRM  target host literally in-scope hai; out-of-scope kabhi touch nahi.
ELSE
    launcher new-scan se folder banao, phir scope verify.
```

> Root rule: `roots` me hain to in-scope; `excluded` me hain to OUT — kabhi mat test karo.

---

## 3. RECON — do chains (same target, alag depth)

### Chain A — pipeline (RECOMMENDED — isi se scanner/intelligence chalta hai)

```bash
python3 recon/recon_pipeline.py --program <program>
# → recon/data/<program>/raw/{subfinder,dnsx,httpx,gau}.txt
# → recon/data/<program>/{assets,endpoints}.json
```

If/else per source — `TOOLS.md` se (mirror):
```text
IF  subdomains unknown            → subfinder → dnsx → httpx (tech+status)
ELIF live hosts already known     → sirf httpx probe
ELIF need archived URLs/params    → gau (endpoints.json me jata hai)
ELSE move to scan
```

### Chain B — fast bb-hunt (quick look, single command)

```bash
bb-hunt <domain>            # subfinder → httpx → ffuf → nuclei
bb-hunt <domain> --probe    # subs + alive only
```
Output: `/tmp/opencode/hunt/<target>/`. **Note:** ye output `scanner.py`/`intelligence.py`
ko data nahi deta (wo sirf `recon/data/<program>/` padhte hain). Use it for quick
sanity/coverage; full pipeline Chain A chalao.

---

## 4. SAFE SCAN — scanner.py (scope-aware nuclei + optional ffuf)

```bash
python3 recon/scanner.py --program <program> --dry-run     # pehle hamesha dry-run
python3 recon/scanner.py --program <program>               # accepted filters me, rate-limited
python3 recon/scanner.py --program <program> --ffuf-host <in-scope-host> --ffuf-wordlist <wl>
```

- Host allowlist = scope.yaml in-scope roots ONLY.
- Destructive categories (dos, rce-destructive, takeover-writes) excluded.
- Nuclei hits import hoti hain `recon.db` (`candidate_findings` table).

**If/else (TOOLS.md mirror):**
```text
IF  known-CVE check needed        → nuclei -t http/ -severity critical,high,medium
ELIF WordPress present            → wpscan --enumerate
ELIF ports/services needed        → nmap -sV --top-ports 100 (in-scope only, no aggressive timing)
ELIF full DAST coverage wanted    → ZAP baseline (docker, in-scope URL)
ELSE manual per finding
```

## 4.5 SECRETS — trufflehog (exposed credentials, cheap win)

```bash
trufflehog filesystem <target-dir> --only-verified --no-update
# verified = key actually works (tool khud service ping karta hai) — fake/example keys ignore
```

- Sasta breadth: `.git`, JS bundles, configs, backups me hardcoded API keys/tokens/db creds.
- `--only-verified` zyada signal: sirf **true-positive** keys report hon (KISS — verified hi count hoti).
- Gitleaks alternative: `gitleaks git --remote <repo-url>` (open repos ke liye).
- Hit mila → manual endpoint check + triage (expected: info-disclosure / cred exposure).

---

## 5. CANDIDATE QUEUE — intelligence.py (deterministic scoring, FREE breadth)

```bash
python3 recon/intelligence.py --program <program> --top 40
# → recon/data/<program>/candidate_report.md + recon.db me findings
```

Deterministic rule scoring (no LLM): tag ke hisaab se weight, redirect-query normalization,
top-N surfaces. Har entry kanha par hai (score, tag, URL) — ye candidate_report.md banata
hai jo prob-hunter (next) ka input hai.

---

## 5.5 APPLICATION MODEL — app ko URL list nahi, app samajho (deterministic, FREE)

```bash
python3 recon/application_model.py --program <program>
# → recon/data/<program>/application_model.json
```

URL paths se deterministic heuristics (no LLM) extract karta hai: **actors** (supplier/admin/
consumer/affiliate), **objects** (order/catalog/invoice/file/payment/fulfillment), **actions**
(create/update/delete/export/refund/upload), **sensitive params** (`?id=` / `?order_id=` /
`?redirect=`) aur **auth-surfaces** (admin/panel/dashboard paths).

> Kehna kya: intelligence kahta hai "kaunse URL 40 me hain" (breadth). Application model
> kahta hai "**app me kya kya hai, kaun access kar sakta hai**" (understanding). Ye hi missing
> layer hai — "interesting URLs" se "interesting vulnerability guesses" tak ka pul.

Human refinement (optional but full value yahi se):
```
application_model.json me ownership_graph + workflow_states bharo
  ownership_graph: [{"actor": "supplier", "object": "order"}]
  workflow_states: [["order_created", "order_refunded"]]   # transition test-able
```

---

## 6. PROBABILISTIC RANKING — prob-hunter (LLM depth-rank, sirf shortlist par)

> Deterministic breadth (intelligence.py, free) ke BAAD hi call — kabhi raw gau par nahi.
> Ye "kya test karu" nahi, "**konsa pehle aur kyun**" decide karta hai + exact manual test.

Trigger (if/else):
```text
IF  candidate_report.md exists (intelligence.py chala)   → @prob-hunter candidate_report.md
ELIF sirf raw recon files hain                          → pehle pipeline+intelligence, phir prob-hunter
ELIF 1-2 suspicious endpoints only                      → skip prob-hunter, seedha manual
```

Input: **top-40 shortlist** `recon/data/<program>/candidate_report.md` (kabhi full gau/httpx
nahi — LLM credits burn). Output:
1. PRIOR TABLE (endpoint | param | prior | evidence | posterior % | verdict)
2. RANKED HITS (sorted)
3. TEST PLAN (top 3-5, read-only manual steps)
4. ASSUMPTIONS & GAPS

Verdict bands: 0-9% SKIP · 10-24% LOW · 25-49% MEDIUM · 50-74% HIGH · 75%+ CRITICAL-HUNT.

> prob-hunter sirf PADHTA hai (grep/cat), kuch edit nahi karta. Manual-testing ORDER isi se
> decide hota hai — real finding isi list ke top me milegi. (Cost guard: LLM call hai,
> isliye sirf shortlist par.)

---

## 7. MANUAL TESTING — asli value yahan hai

prob-hunter ka TEST PLAN + candidate_report.md ko top-down manually verify karo:

| Vuln class | Tool | Evidence lookup |
|-----------|------|-----------------|
| IDOR / BOLA / authz | chrome-devtools (login flow, second account) | object id change → cross-account read/modify |
| SQLi | manual payloads → sqlmap `--batch --risk 1` if confirmed | error/reflection |
| XSS | dalfox confirm (in-scope params) | reflected/dom |
| SSRF / open redirect | manual, `?url= ?next=` | respond on your server / 302 Location |
| Path traversal / LFI | manual `../`, `%00`, double-encode | file content echo |
| Info disclosure | curl/nuclei | stack trace, .git, debug headers |
| Bot-walled (403 Akamai) | `curl_cffi impersonate="chrome120"` slow fuzz | bypass need verified first |

> sab kuch READ-ONLY-first. Payload only in-scope + non-destructive.

---

## 8. TRIAGE — skill (finding state machine)

**Trigger:** koi bhi new finding manual test par confirm → Skill tool `triage`.

State machine, har finding: `discovered → needs-info | valid | duplicate | wontfix → ready-for-report`.

```text
IF  claim unreproducible     → needs-info (exact blocker batao)
IF  out-of-scope             → wontfix (never submit)
IF  duplicate (hacktivity)   → duplicate + wontfix (reference prior report)
IF  confirmed + in-scope     → valid
ELSE human gate — NEVER auto-submit
```
Hard rule: `valid` sirf confirmed reproduction ke baad. Submission SIRF user ke confirmation se.

---

## 9. GRILLING — skill (report-ready interrogation)

**Trigger:** finding `ready-for-report` se pehle → Skill `grill-me` (router) jo `grilling` chalaata hai.
Decision-tree rounds: scope → class/root cause → impact/CVSS → reproducibility → evidence quality
(evidence dir, kabhi /tmp) → duplicates/prior art → report shape. Fire hamesha agent khud fact
len (curl repro, H1 MCP scope, hacktivity) — user se sirf decisions.

Saral niyam: report tabhi likha/submit jab user confirm kare. AI-assisted disclaimer hamesha.

---

## 10. SECOND OPINION (high/critical se pehle)

`claude-reviewer` subagent (task tool) — independent Claude Code cross-check:
real vuln? PoC solid? severity? report-worthiness? **Read-only, finding ko edit nahi karta.**

---

## 11. REPORT — hackerone submit

```bash
hackerone_submit_report → team_handle, title, vulnerability_information, impact,
                         severity_rating, weakness_id, structured_scope_id
```
Budhi details: program/SCOPE.md + hackerone_get_program_weaknesses se weakness_id,
scope me se structured_scope_id. Report file: `reports/<program>/` me save karo.

---

## 12. HANDOFF — skill (session continuity)

**Trigger:** session switch/end/pause agent se pehle → Skill `handoff`.
Save: `evidence/handoffs/<target>-<date>.md` — KABHI /tmp nahi (files wiped, findings lost).
Content: target+scope, session summary, evidence pointers (paths, embed nahi), finding states,
suggested skills for next agent, next steps. Redact credentials/PII.

---

## 13. LEARN & UPDATE — improvement loop

- Har session ke baad `LESSONS.md` (bug-bounty skill) — worked/failed/verified.
- candidate_report.md triage entries update karo.
- New tools/methods → TOOLS.md if/else me add.

---

## QUICK CHEAT-SHEET (one-liners)

| Stage | Command |
|-------|---------|
| Launch | `./start-bugbounty.sh` (desktop click) |
| Recon (full) | `python3 recon/recon_pipeline.py --program <p>` |
| Recon (fast, no DB) | `bb-hunt <domain>` |
| Safe scan | `python3 recon/scanner.py --program <p> --dry-run` |
| Candidate queue | `python3 recon/intelligence.py --program <p> --top 40` |
| Rank endpoints (LLM) | `@prob-hunter recon/data/<p>/candidate_report.md` |
| Triage finding | Skill `triage` (state machine) |
| Report-ready grill | Skill `grill-me` → `grilling` |
| Second opinion | `task → claude-reviewer` |
| Session end/pause | Skill `handoff` → `evidence/handoffs/` |
| Report | `hackerone_submit_report` |

---

## KNOWN GAPS (tofix queue)

1. **bb-hunt vs pipeline** — ab if/elif routed (IF_ELSE.md §3): bb-hunt = quick sanity only
   (/tmp output, no DB), pipeline = full workflow input. No code change needed; convention document hai.
2. **prob-hunter credits** — model run ke liye OpenRouter credits chahiye (dispatch fail hota
   hai without them). Config sahi hai, credit constraint hai. Shortlist input isi liye —
   token burn kam karna.
3. **ZAP/wpscan async steps** — docker-dependent, manual per-target decide.