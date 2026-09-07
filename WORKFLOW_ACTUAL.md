# WORKFLOW_ACTUAL.md — Jo Sach Mein Ho Raha Hai (Code-Verified)

> Ye file `WORKFLOW.md` se ALAG hai. `WORKFLOW.md` ek intended/aspirational operational
> guide hai (mostly `[C]` — human + OpenCode agent wale flow ke liye likha gaya).
> Ye file **actual code scan/audit karke** likhi gayi hai (`docs/audit/*.md` ke real,
> executed evidence se) — jo bhi yahan likha hai, wo `start-bugbounty.sh` +
> `recon/*.py` mein padh-ke aur **real tools chala ke** confirm kiya gaya hai, sirf
> docs padh ke nahi. Last verified: 2026-09-06, commit `fda1415`.
>
> Do alag paths hain jo `WORKFLOW.md` mix kar deta hai — is file mein dono clearly
> separate hain: **[A] Autonomous** (pura Python, koi human-gate nahi) vs **[C] Complete**
> (Python pipeline + OpenCode interactive handoff, jahan human/agent triage karta hai).

---

## PART 1 — TREE STRUCTURE

### 1.1 Project directory tree (jo actually use hoti hai)

```
bug-bounty/
├── Bug Bounty.desktop              ← desktop icon → start-bugbounty.sh
├── start-bugbounty.sh              ← LAUNCHER (sab yahin se shuru)
├── opencode.json                   ← global OpenCode config (permission: allow-all!)
│
├── <program>/                      ← har target ka apna folder (meesho/, flipkart/, wordpress/, ...)
│   ├── scope.yaml                  ← roots + excluded (source of truth for scope)
│   ├── SCOPE.md                    ← human-readable scope summary
│   ├── NOTES.md                    ← progress notes
│   ├── opencode.json               ← per-target OpenCode config (default_agent, MCP, permission)
│   └── AUTONOMOUS_HUNT_PROMPT.md   ← [C] path only — h1_client.py --prompt se generate hota hai
│
├── recon/                          ← poora automation engine (12 Python modules)
│   ├── scope_utils.py              ← [SHARED] scope.yaml load + in-scope check (single source)
│   ├── h1_client.py                ← HackerOne API + target scaffold + prompt generator
│   ├── recon_pipeline.py           ← Phase 1: subfinder→dnsx→httpx→gau (+ js_miner + app_model auto-trigger)
│   ├── js_miner.py                 ← Phase 2: Katana JS crawl → endpoints + secrets
│   ├── application_model.py        ← actors/objects/actions extractor (OpenCode @prob-hunter ke liye)
│   ├── scanner.py                  ← Phase 3: Nuclei safe scan → candidate_findings
│   ├── intelligence.py             ← Phase 4: deterministic scoring → candidate_report.md + DB sync
│   ├── auto_hunter.py              ← Phase 5 ([A] only): auto-verify (CORS/secrets/traversal)
│   ├── report_gen.py               ← VERIFIED milte hi HackerOne markdown draft banata hai
│   ├── notify.py                   ← desktop + Telegram alert dispatch
│   ├── daemon.py                   ← background loop: delta-detect → poora chain re-trigger
│   ├── artifact_consistency.py     ← [DIAGNOSTIC] run_id staleness checker (read-only)
│   └── data/<program>/             ← per-program generated output
│       ├── raw/                    ← subfinder.txt, dnsx.txt, httpx.jsonl, gau.txt, katana_js.jsonl, nuclei_*.jsonl
│       ├── assets.json             ← normalized live-host list (run_id tagged)
│       ├── endpoints.json          ← normalized URL list (run_id tagged)
│       ├── application_model.json  ← actors/objects/actions map
│       ├── recon.db                ← SQLite: assets, endpoints, candidate_findings (all run_id tagged)
│       ├── candidate_report.md     ← top-40 scored surfaces
│       ├── top_priority.json
│       └── run_meta.json           ← run_id, tools versions, counts, status
│
├── evidence/
│   ├── reports/<program>/          ← report_gen.py output
│   │   ├── H1_REPORT_*.md          ← REAL verified findings only
│   │   └── sample/SAMPLE_H1_REPORT_*.md  ← --sample test drafts (never real)
│   ├── scans/<program>/            ← scanner.py raw nuclei/httpx probe files
│   └── handoffs/                   ← session handoff notes (OpenCode skill)
│
├── tests/                          ← real integration tests (real subfinder/httpx/katana/nuclei)
│   ├── test_runtime_integrity.py
│   ├── test_e2e_pipeline.py
│   └── test_daemon_delta_e2e.py
│
├── WORKFLOW.md                     ← intended/manual [C] flow (OpenCode skills-based)
├── WORKFLOW_ACTUAL.md              ← (ye file) code-verified actual wiring
├── docs/audit/                     ← forensic audit reports (real evidence, run logs)
└── (.gitignore'd: recon/data/, evidence/ — kabhi git push nahi hote)
```

### 1.2 Pipeline flow tree — [A] AUTONOMOUS ZERO-TOUCH HUNT

```
start-bugbounty.sh
  └─ target_menu → key "A" (ya "F" for --fresh) → run_zero_touch_hunt()
       │
       ├─[Phase 1/6]─ recon_pipeline.py --program <p> --skip-js [--fresh]
       │     ├─ subfinder (passive subs)         → raw/subfinder.txt
       │     ├─ dnsx (DNS resolve)                → raw/dnsx.txt
       │     ├─ httpx (live probe, single-writer) → raw/httpx.jsonl  → assets.json
       │     ├─ gau (archive URLs)                → raw/gau.txt      → endpoints.json
       │     └─ application_model.py (auto)       → application_model.json
       │
       ├─[Phase 2/6]─ js_miner.py --program <p>
       │     └─ katana (JS crawl+jsluice)  → raw/katana_js.jsonl → endpoints.json (merge)
       │        + application_model.py (re-triggered)
       │
       ├─[Phase 3/6]─ scanner.py --program <p>
       │     └─ nuclei (safe tags, rate-limited) → candidate_findings (tool='nuclei')
       │
       ├─[Phase 4/6]─ intelligence.py --program <p>
       │     └─ deterministic scoring → candidate_findings (tool='intelligence') + candidate_report.md
       │
       ├─[Phase 5/6]─ auto_hunter.py --program <p> --min-score 50
       │     └─ for each TRIAGED candidate (score≥50):
       │           real HTTP probe → CORS reflection? secret leak? traversal? admin-panel?
       │           ├─ VERIFIED  → report_gen.py (real draft, evidence/reports/<p>/H1_REPORT_*.md)
       │           │              → notify.py (desktop + Telegram alert)
       │           └─ REJECTED  → notes="Non-vulnerable during active probe"
       │
       └─[Phase 6/6]─ count reports generated → notify.py summary alert
```
**Koi human-gate nahi is path mein.** Triage/Grilling/Second-opinion (WORKFLOW.md ke skills)
yahan **invoke hi nahi hote** — `auto_hunter.py` ka apna simple state machine hi sab kuch
decide karta hai (`TRIAGED → VALIDATING → VERIFIED | REJECTED`).

### 1.3 Pipeline flow tree — [C] COMPLETE SCAN & OPENCODE PROMPT

```
start-bugbounty.sh → target_menu → key "C" → run_complete_hunt()
       │
       ├─[Phase 1/5]─ recon_pipeline.py --skip-js   (same as [A])
       ├─[Phase 2/5]─ js_miner.py                    (same as [A])
       ├─[Phase 3/5]─ scanner.py                     (same as [A])
       ├─[Phase 4/5]─ intelligence.py                (same as [A])
       └─[Phase 5/5]─ h1_client.py --prompt <p>
             └─ candidate_report.md + scope.yaml → AUTONOMOUS_HUNT_PROMPT.md
                   │
                   └─ OpenCode launch: opencode "<target-dir>" --prompt "$(cat prompt)"
                        (interactive TUI, uses target's opencode.json → default_agent:
                         "hackerone-analyst"; human ab yahan se WORKFLOW.md ka §6-13
                         follow karta hai: @prob-hunter → manual test → triage skill →
                         grilling skill → claude-reviewer → hackerone_submit_report)
```
**Yahan human-gate REAL hai** — auto_hunter.py is path mein call hi nahi hota. Report
submission sirf human confirm karne ke baad, OpenCode ke andar.

### 1.4 Pipeline flow tree — DAEMON (background, continuous)

```
start-bugbounty.sh --daemon  (ya menu "M" → daemon_menu)
  └─ daemon.py --program <p> [--interval N | --once]
       │
       └─ every cycle: run_delta_cycle(program)
             ├─ subfinder -dL <roots> (passive re-probe)
             ├─ delta = curr_hosts − prev_hosts (assets.json ke known hosts se)
             ├─ IF delta == 0 → "All quiet", exit
             └─ IF delta > 0 →
                   ├─ httpx probe on new hosts → assets.json (append, source=delta_daemon)
                   ├─ js_miner.py
                   ├─ scanner.py (Nuclei)        ← [confirmed wired — pehle missing tha]
                   ├─ intelligence.py
                   ├─ auto_hunter.py --min-score 60
                   └─ notify.py (delta alert)
```
Ye [A] jaisa hi hai, bas trigger "naya subdomain mila" hai, na ki manual button-press.

---

## PART 2 — DETAILED, STAGE-BY-STAGE (actual code, actual flags, actual outputs)

### 2.1 ENTRY — `start-bugbounty.sh`

Real main menu (jo terminal mein dikhta hai):
```
N  Start NEW Scan             → new_scan() → HackerOne API se target scaffold
M  Continuous Recon Daemon    → daemon_menu() → single-cycle / background-loop / stop
T  Telegram & Phone Alerts    → notify.py --setup-telegram
D  System Diagnostics         → diagnostics_check() → tool/API/docker check
Q  Quit
1..n  (existing target select) → target_menu()
```
CLI bypass (no menu): `./start-bugbounty.sh --auto <target> [--fresh]` ya `--daemon [args]`.

Target select ke baad, **target_menu()** (per-target dashboard):
```
A  AUTONOMOUS ZERO-TOUCH HUNT     → run_zero_touch_hunt (Part 1.2)
F  FRESH ZERO-TOUCH HUNT (Force)  → same + --fresh
C  Complete Scan & OpenCode       → run_complete_hunt (Part 1.3)
1  Interactive Shell/Session
2  Recon Pipeline Only            → recon_pipeline.py standalone
3  Deep JS Miner (Katana)         → js_miner.py standalone
4  Safe Vulnerability Scan        → scanner.py standalone
5  View Candidate Report          → candidate_report.md cat/less
6  Recon Diff Engine              → target_diff() — DISPLAY ONLY, DB mein kuch nahi likhta
7  View Scope & Notes
0  Back
```

### 2.2 SCOPE — `recon/scope_utils.py` (single source of truth, sab modules yahi use karte hain)

`load_scope_file(path, required, not_found_msg)` — YAML load karta hai, wildcard-root
quote issue auto-fix karta hai. `make_scope_filter(scope)` — `in_scope(host)` function
deta hai jo:
1. Exact root match (`host` ya `host:port` dono forms check karta hai)
2. Excluded list check (wildcard `*.` aware)
3. Root subdomain wildcard match

**Important:** ye function pehle 5 alag files mein duplicate tha (drift ka risk tha —
ek jagah fix hota, doosri jagah nahi) — ab sab isi ek file se import karte hain
(`recon_pipeline.py`, `scanner.py`, `js_miner.py`, `daemon.py`, `auto_hunter.py`).

### 2.3 RECON — `recon/recon_pipeline.py`

```bash
python3 recon/recon_pipeline.py --program <p> [--skip-js] [--skip-endpoints] [--fresh]
```
- **Default (no `--fresh`):** `subfinder.txt`/`dnsx.txt`/`gau.txt` agar exist karte hain
  to REUSE hote hain (log: `[CACHE REUSE]`) — sirf `httpx` probe HAMESHA fresh chalta hai
  (isliye assets ka status/tech kabhi 1-run se zyada stale nahi hota).
- **`--fresh`/`--force`:** raw files delete karke sab kuch dobara chalata hai.
- **Single-producer httpx:** `httpx` ka stdout Python khud read+write karta hai
  (per-PID temp file → validate → atomic `os.replace`) — koi race condition nahi.
- Output: `assets.json`, `endpoints.json` (agar `--skip-endpoints` nahi), `run_meta.json`
  (`run_id`, tool versions, counts) — sab ek hi `run_id` se tagged.
- Agar `--skip-js` nahi diya: khud `js_miner.py` subprocess se call karta hai.
- Agar `endpoints.json` bann jaye: khud `application_model.py` subprocess se call karta hai.

### 2.4 JS MINING — `recon/js_miner.py`

```bash
python3 recon/js_miner.py --program <p> [--dry-run]
```
Katana crawl (`-jc -jsl -xhr -depth 2`) live assets par → JS files se regex se API
routes/secrets nikalta hai → `endpoints.json` mein merge (dedupe by URL) → `recon.db`
endpoints table mein bhi direct insert karta hai → phir `application_model.py` re-run
karta hai.

### 2.5 APPLICATION MODEL — `recon/application_model.py`

```bash
python3 recon/application_model.py --program <p>
```
Deterministic regex (NO LLM) — URL paths se **actors** (admin/supplier/consumer/affiliate),
**objects** (order/catalog/payment/file...), **actions** (create/delete/export...),
**sensitive params**, **auth-surfaces** nikalta hai → `application_model.json`.

**Kaun consume karta hai?** `intelligence.py`/`scanner.py`/`auto_hunter.py` — koi nahi
(unki apni independent scoring hai). Consumer hai **`@prob-hunter`** — ek OpenCode agent
(`~/.config/opencode/agents/prob-hunter.md`) jo `[C]` path mein human manually invoke
karta hai BOLA/IDOR priors ke liye. **Yani ye file connected hai, par sirf `[C]`
(manual/agent) flow se — `[A]` autonomous flow isse kabhi nahi padhta.**

### 2.6 SCANNER — `recon/scanner.py`

```bash
python3 recon/scanner.py --program <p> [--dry-run] [--run-on live|all|list:x,y] [--no-nuclei] [--ffuf-host <h> --ffuf-wordlist <wl>]
```
`assets.json` se targets uthata hai (empty ho to scope.yaml roots pe fallback) →
Nuclei chalata hai (`exposure,config,misconfig,tech,cve,default-login` tags,
DoS/RCE/injection tags explicitly EXCLUDED, rate-limited) → hits `candidate_findings`
mein `tool='nuclei'`, apna `run_id` ke saath insert/update hote hain.

### 2.7 INTELLIGENCE — `recon/intelligence.py`

```bash
python3 recon/intelligence.py --program <p> --top 40
```
`assets.json` + `endpoints.json` padh ke deterministic keyword-weight scoring
(swagger/api → +25, .env/config → +30, admin/debug → wagera) → `recon.db` mein
`assets`/`endpoints` table poori tarah REBUILD karta hai (delete+reinsert — ye pipeline
ka "DB source of truth sync point" hai), score≥40 wale `candidate_findings` mein
(`tool='intelligence'`) → `candidate_report.md` likhta hai.

**Malformed `assets.json`/`endpoints.json` par:** ab clean error deta hai
(`ERROR: assets.json is malformed / Program / Artifact / Run ID / Recovery`), exit 1 —
raw Python traceback nahi.

### 2.8 AUTO-HUNTER — `recon/auto_hunter.py` (SIRF [A]/daemon path mein, [C] mein nahi)

```bash
python3 recon/auto_hunter.py --program <p> --min-score 50 [--dry-run]
```
`candidate_findings` se `TRIAGED`/`triage` status, score≥min uthata hai → real
non-destructive HTTP probes:
- **CORS:** `Origin: https://attacker-verification...` bhejke check karta hai
  `Access-Control-Allow-Origin` reflect + `Access-Control-Allow-Credentials: true`
- **Secret leak:** response body mein AWS keys / `DB_PASSWORD=` / PEM headers regex
- **GraphQL introspection**, **admin/auth panel discovery** (keyword + status 200)
- **Normal HTTP 200 API = kabhi VERIFIED nahi** — false-positive elimination hardcoded

VERIFIED → status update + `report_gen.py` call + `notify.py` alert.
REJECTED → `notes='Non-vulnerable during active probe'`.

### 2.9 REPORT — `recon/report_gen.py`

```bash
python3 recon/report_gen.py --program <p> [--sample] [--candidate-id N]
```
CWE mapping (cors_misconfig→CWE-942, sqli→CWE-89, rce→CWE-94, ...), curl command
auto-sanitize karta hai (Bearer/Cookie/API-Key tokens `[REDACTED]`).
- **Real finding** (no `--sample`) → `evidence/reports/<p>/H1_REPORT_*.md`
- **`--sample`** → `evidence/reports/<p>/sample/SAMPLE_H1_REPORT_*.md` + in-file
  "SAMPLE TEST FIXTURE" banner — kabhi root path mein contaminate nahi hota.

**Important: ye sirf DRAFT banata hai, HackerOne ko actual submit NAHI karta.** Real
submission ya to manual hai, ya `hackerone_submit_report` MCP tool se (jo `[C]`/OpenCode
session ke andar human confirm karke chalata hai).

### 2.10 NOTIFY — `recon/notify.py`

Desktop notification (`notify-send`) + Telegram bot (agar `--setup-telegram` se
configured) — `dispatch_alert(title, message, severity)` function. `auto_hunter.py`,
`daemon.py` isko VERIFIED finding / delta detect hone par call karte hain.

### 2.11 DAEMON — `recon/daemon.py`

```bash
python3 recon/daemon.py --program <p> --once     # single delta check
python3 recon/daemon.py --program <p> --interval 3600   # background loop
python3 recon/daemon.py --status | --stop
```
Part 1.4 mein tree diagram hai. Real-tested: delta detect hone par pura chain
(httpx→js_miner→scanner→intelligence→auto_hunter→notify) genuinely fire hota hai
(confirmed via `tests/test_daemon_delta_e2e.py`, real subprocess calls).

### 2.12 DIAGNOSTIC — `recon/artifact_consistency.py` (NAYA — manual chalana padta hai)

```bash
python3 recon/artifact_consistency.py --program <p>
```
Read-only check: `run_meta.json` ka `run_id` vs `assets.json`/`endpoints.json`/`recon.db`
ke `run_id` — agar DB purane run ka hai aur JSON files naye run ka, to
`STALE / OUT OF SYNC` (exit 1) bolta hai. **Ye koi automatic step nahi hai** — launcher
ise kabhi khud nahi chalata, tumhe manually run karna padega agar shak ho ki DB stale hai.

### 2.13 [C] PATH KA AAGE KA HISSA — OpenCode handoff

`h1_client.py --prompt <target>` → `AUTONOMOUS_HUNT_PROMPT.md` banata hai
(candidate_report.md + scope.yaml se) → launcher `opencode "<target-dir>" --prompt "..."`
chalata hai. Target ka apna `opencode.json` (`default_agent: hackerone-analyst`,
permission: allow-all) load hota hai. Yahan se **WORKFLOW.md ka §6 onwards** applicable
hai (prob-hunter → manual testing → triage skill → grilling skill → claude-reviewer →
hackerone_submit_report → handoff skill) — **ye sab manual/OpenCode-agent driven hai,
[A] autonomous path isse bilkul alag hai aur inme se kuch bhi use nahi karta.**

---

## PART 3 — [A] vs [C]: SABSE ZAROORI FARAK (ek line mein)

| | **[A] Autonomous** | **[C] Complete + OpenCode** |
|---|---|---|
| Verification | `auto_hunter.py` (Python, khud CORS/secret/traversal check) | Human/agent manual (chrome-devtools, sqlmap, dalfox...) |
| Application model use | Kabhi nahi | `@prob-hunter` (agar human invoke kare) |
| Human gate | ❌ Koi nahi | ✅ Triage/Grilling/Second-opinion skills |
| Report | Auto-draft (`report_gen.py`) | Manual likha ya `hackerone_submit_report` |
| Kab use karo | Bahut saare targets par jaldi broad-sweep | Deep, high-value ek target par |

---

## PART 4 — WORKFLOW.md se FARAK (jo maine discussion mein bataya tha)

1. `WORKFLOW.md` ka launcher menu (`[1] New [2] Continue [3] Quit`) outdated hai — actual
   `N/M/T/D/Q` hai (Part 2.1).
2. `--fresh` flag `WORKFLOW.md` mein missing hai.
3. `js_miner.py`, `auto_hunter.py`, `daemon.py`, `report_gen.py`, `notify.py`,
   `scope_utils.py`, `artifact_consistency.py` — in 7 modules ka `WORKFLOW.md` mein
   **zero mention** hai, jabki ye sab real, wired, tested code hai.
4. `WORKFLOW.md` ek hi linear flow dikhata hai jo asal mein sirf `[C]` hai — `[A]`
   (jo shayad zyada use hota hai, kyunki isme koi human step nahi chahiye) poori tarah
   missing hai us doc se.

**Recommendation:** `WORKFLOW.md` ko `[C]`-specific rehne do (wo apni jagah sahi hai —
manual/deep-hunt guide), aur is file (`WORKFLOW_ACTUAL.md`) ko `[A]`+wiring reference
ke liye rakho. Dono files ka purpose alag hai, isliye merge karne ki zaroorat nahi.
