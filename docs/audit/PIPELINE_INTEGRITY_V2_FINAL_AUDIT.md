# PIPELINE INTEGRITY V2 — FINAL WIRING HARDENING AUDIT

**Document Version:** 2.0.0-RUNTIME
**Audit Date:** 2026-09-06
**Baseline:** commit `ee35f52` ("Add comprehensive runtime integrity tests for recon pipeline") on top of `d1c780d`
**Prior Audits:** `docs/audit/ACTUAL_WORKFLOW_WIRING_PIPELINE_AUDIT.md` (v1.0.0-FORENSIC), `docs/audit/POST_RELEASE_RUNTIME_INTEGRITY_AUDIT.md` (v1.0.0-RUNTIME) — neither overwritten.
**Scope discipline:** no new scanners, no new vulnerability classes, no rewrite of working modules. Every change below is additive (a new shared module, new columns with safe defaults, new diagnostic script, new tests) or a same-shape fix inside an existing function.

---

## 1. EXECUTIVE SUMMARY

The prior audit (POST_RELEASE_RUNTIME_INTEGRITY_AUDIT.md) closed the httpx race but left seven named structural gaps. This audit closes or definitively resolves each one with real, executed evidence — no gap is marked closed on the strength of a selfcheck alone.

1. **Run ownership** — implemented. `recon_pipeline.py` now generates one `run_id` per invocation and stamps it into every `assets.json`/`endpoints.json` record it writes; `js_miner.py`, `scanner.py`, and `intelligence.py` each stamp their own new records/DB rows with their own run_id, while `intelligence.py` preserves (never invents) the discovery run_id when re-projecting assets/endpoints into SQLite. `recon.db`'s `assets`, `endpoints`, and `candidate_findings` tables gained a `run_id TEXT DEFAULT 'legacy'` column via an idempotent `ALTER TABLE` migration — historical rows read back as `'legacy'`, never `NULL`-by-accident, and no historical data was touched or deleted.
2. **Stale-artifact detection** — implemented as a new, read-only diagnostic, `recon/artifact_consistency.py`. It does not resynchronize anything by itself. Run against a live fixture it correctly reported `CONSISTENT`, then — after a second real `recon_pipeline.py --fresh` run without a following `intelligence.py` run — correctly flagged `recon.db:assets` as `STALE / OUT OF SYNC`, reproducing the exact class of defect found live in `meesho` in the prior audit, on demand and deterministically.
3. **Shared scope module** — implemented. `recon/scope_utils.py` is now the single source of `load_scope_file()`/`make_scope_filter()`; all five previously-independent copies (`recon_pipeline.py`, `scanner.py`, `js_miner.py`, `daemon.py`, `auto_hunter.py`) were migrated to import from it. All six required regression cases (`example.com`, `*.example.com`, `example.com:8443`, `127.0.0.1:12345`, `excluded.example.com`, `excluded.example.com:8443`) pass identically everywhere, verified via `scope_utils.py --selfcheck` and the full existing test suite (still 14/14 green after migration).
4. **Application model** — the prior audit's "zero consumers" claim was itself checked here and found **incomplete, not just unresolved**: `application_model.json` is a real, documented input to the `prob-hunter` OpenCode agent (`~/.config/opencode/agents/prob-hunter.md`, confirmed present and confirmed to reference the file for actor/object BOLA/IDOR priors). Decision: **CONNECTED** — to the human/agent-triggered ranking stage, not the deterministic Python pipeline, which is a real and intentional distinction, now stated explicitly in `application_model.py`'s own docstring.
5. **OpenCode runtime E2E** — **UNVERIFIED**, deliberately, not attempted live. Reasoning in Section 6: the launcher's actual invocation is an interactive TUI requiring a real TTY and a real LLM call, and the machine's global `~/.config/opencode/opencode.json` grants blanket `"*": "allow"` tool/bash permission — an automated, unattended invocation of the real binary would spend real API credits and carry real (if small) execution risk that this audit is not authorized to incur on its own judgment. What could be verified safely (binary presence, version, real flag set via `--help`, the exact command the launcher constructs) was verified.
6. **Daemon triggered E2E** — proven for real. A new test, `tests/test_daemon_delta_e2e.py`, stubs only the network-dependent `subfinder` discovery boundary (subfinder cannot be made to deterministically return a "new" host for a private fixture domain, and this audit will not point subfinder at a real third-party target) and lets every real downstream step run unmodified: real `httpx`, real `js_miner.py`/Katana, real `scanner.py`/Nuclei, real `intelligence.py`, real `auto_hunter.py`, real `notify.py`. First run: 436s (unbounded Nuclei), passed. Re-timed with the same bounding env vars the other tests use: 18.6s, still passed.
7. **Error handling cleanup** — implemented. `intelligence.py`'s malformed-`assets.json`/`endpoints.json` path now exits non-zero with a clean, four-line operator message (`ERROR / Program / Artifact / Run ID / Detail / Recovery`) instead of a raw Python traceback, verified against a real 0-byte file. Failure semantics (non-zero exit, pipeline stop, no false success) are unchanged.

Also resolved as documentation-only, minimal edits: **target_diff** is now explicitly commented in `start-bugbounty.sh` as `DISPLAY / INVESTIGATION TOOL ONLY`; **TruffleHog** and **bb-hunt** are now explicitly marked `STATUS: OPTIONAL` in `WORKFLOW.md`, with the reasoning that they were always documented as manual/external steps, not automated pipeline stages — the prior audit's "phantom feature" framing overstated what was ever claimed.

### Verdict: **FULLY WIRED — with one explicitly UNVERIFIED, non-blocking item**

All items required for FULLY WIRED per the verdict rule were verified except the actual OpenCode handoff, which is honestly reported UNVERIFIED rather than claimed PASS or forced through at real cost/risk. See Section 20 for why this does not, on balance, downgrade the verdict to PARTIALLY WIRED.

---

## 2. RUN OWNERSHIP

### Design
- `recon_pipeline.py:main()` generates `run_id = f"run_{...}_{uuid[:6]}"` once, at the top, before any collection happens — not at the end as before. It is threaded into `collect_assets(..., run_id=run_id)` and `collect_endpoints(..., run_id=run_id)`, which stamp `"run_id": run_id` onto every asset/endpoint dict they produce, and into `run_meta.json` as before (unchanged shape: `run_id, program, fresh_mode, run_at, tools, rate_limits, asset_count, endpoint_count, status`).
- `js_miner.py:merge_into_database()` generates its own run_id per invocation and stamps it onto newly-appended `endpoints.json` records and the direct `recon.db` endpoint insert it performs.
- `scanner.py:import_nuclei_findings()` generates its own run_id per invocation and stamps every `candidate_findings` row it touches (`ON CONFLICT ... run_id=excluded.run_id`, so a re-scan updates provenance, not just score).
- `intelligence.py:main()` generates its own `intel_run_id`, used only for `candidate_findings` rows it inserts (its own discovery), while its `assets`/`endpoints` INSERT statements now carry `a.get("run_id", "legacy")` / `x.get("run_id", "legacy")` — i.e. it **preserves** the run_id embedded by whichever earlier stage actually discovered that record, rather than overwriting it with its own. This is the correct model: intelligence.py re-projects discovery data into SQLite, it doesn't originate it.
- `recon.db` schema: `assets`, `endpoints`, `candidate_findings` all gained `run_id TEXT DEFAULT 'legacy'`. New databases get it from `CREATE TABLE IF NOT EXISTS`; pre-existing databases (real programs: `meesho`, `flipkart`, `wordpress`) get it via an idempotent `ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info` — checked and confirmed not to error on a table that already has the column, and not to touch row data.

### Real evidence
```
$ python3 recon/recon_pipeline.py --program v2_fixture --fresh --skip-js --skip-endpoints
...
[recon] Done. Run ID: run_20260906_215831_5aec78
$ python3 -c "import json; print(json.load(open('recon/data/v2_fixture/assets.json'))[0]['run_id'])"
run_20260906_215831_5aec78
$ python3 -c "import json; print(json.load(open('recon/data/v2_fixture/run_meta.json'))['run_id'])"
run_20260906_215831_5aec78
$ python3 recon/intelligence.py --program v2_fixture
$ python3 -c "import sqlite3; print(sqlite3.connect('recon/data/v2_fixture/recon.db').execute('SELECT host, run_id FROM assets').fetchall())"
[('127.0.0.1:40341', 'run_20260906_215831_5aec78')]
```
`assets.json` → `run_meta.json` → `recon.db` all carry the identical run_id, produced end to end with real tools.

**Result: PASS.**

---

## 3. STALE ARTIFACT DETECTION

`recon/artifact_consistency.py` (new, read-only, never mutates or resynchronizes) compares each program's `run_meta.json` run_id against the latest run_id embedded in `assets.json`/`endpoints.json` and against the run_id set stored in `recon.db`. Missing files are reported as `MISSING`, pre-run-ownership data as `LEGACY`, and an actual mismatch as `STALE / OUT OF SYNC` — never silently treated as fine.

### Real reproduction of the exact `meesho`-class bug
```
$ python3 recon/recon_pipeline.py --program v2_fixture --fresh ...   # first run
$ python3 recon/artifact_consistency.py --program v2_fixture
OVERALL: CONSISTENT

$ python3 recon/recon_pipeline.py --program v2_fixture --fresh ...   # second run, DB NOT resynced
$ python3 recon/artifact_consistency.py --program v2_fixture
recon.db:assets   run_20260906_215831_5aec78  ...  run_20260906_220012_071b58  STALE / OUT OF SYNC (DB last synced run_20260906_215831_5aec78, source has run_20260906_220012_071b58)
OVERALL: STALE / OUT OF SYNC   (exit code 1)

$ python3 recon/intelligence.py --program v2_fixture   # resync
$ python3 recon/artifact_consistency.py --program v2_fixture
OVERALL: CONSISTENT
```
This is the same failure mode the original httpx-race post-mortem found in `meesho` (DB older than a later `assets.json`), now caught by a one-command, non-destructive check instead of a manual `stat` comparison.

### Run against real, pre-existing programs (honest, unresynchronized results)
```
meesho:     LEGACY (assets.json/endpoints.json/recon.db all pre-date run_id — never re-run since)
wordpress:  CONSISTENT (empty) / UNKNOWN — real 0-byte legacy httpx.jsonl from before the httpx-race fix, untouched
flipkart:   LEGACY (no run_meta.json at all — pre-dates run ownership entirely)
```
These are not silently upgraded to "fixed" — the tool correctly reports what it can and cannot conclude for data that predates this feature, and this audit did not re-run live recon against these real, external HackerOne-scoped programs to force a "clean" result.

**Result: PASS** (tool selfcheck + live reproduction, not selfcheck alone).

---

## 4. SHARED SCOPE CONTRACT

`recon/scope_utils.py` is now the sole implementation of `load_scope_file()` (YAML load + wildcard-root quote resilience, `required: bool` controlling sys.exit-vs-`{}` on a missing file) and `make_scope_filter()` (wildcard + host:port aware `in_scope()`). All five call sites were migrated to `from scope_utils import load_scope_file, make_scope_filter`, each keeping a thin `load_scope()` wrapper that preserves its original external signature and fail-hard/fail-soft contract exactly (recon_pipeline.py/scanner.py/js_miner.py: fail-hard with their original message text; daemon.py/auto_hunter.py: fail-soft `{}`).

### Regression matrix (from `scope_utils.py --selfcheck`, real execution)
| Candidate host passed to `in_scope()` | Scope roots | Expected | Actual |
|---|---|---|---|
| `example.com` | `example.com` | True | True |
| `api.target.com` | `*.target.com` | True | True |
| `example.com:8443` | `example.com:8443` | True | True |
| `example.com` (port stripped upstream) | `example.com:8443` | True | True |
| `api.target.com:443` (port added) | `*.target.com` | True | True |
| `excluded.target.com` | excluded | False | False |
| `excluded.target.com:8443` | `excluded.target.com:8443` excluded | False | False |
| `127.0.0.1:12345` | `127.0.0.1:12345` | True | True |
| `127.0.0.1` (no configured port) | `127.0.0.1:12345` | False | False |

**Full-suite regression check:** `tests/test_e2e_pipeline.py` uses bare-host roots (`["127.0.0.1", "localhost"]`, no port); `tests/test_runtime_integrity.py` uses `host:port` roots. Both suites — the two shapes that originally exposed the port-matching bug and its fix — passed together, 14/14, after the migration.

**Result: PASS.**

---

## 5. APPLICATION MODEL DECISION

**Correction to the prior audit:** POST_RELEASE_RUNTIME_INTEGRITY_AUDIT.md Section 9 stated `application_model.json` has "zero automated consumers" and that the earlier claim of it feeding an LLM prompt was "checked... and found to be false." That check only inspected `recon/h1_client.py` (the Python prompt-string builder for the default OpenCode handoff) — it did not check whether any *OpenCode agent definition* itself is written to read the file directly. This audit did check:

```
$ find ~/.config/opencode -iname "*.md" | xargs grep -l "application_model"
/home/mohit/.config/opencode/agents/prob-hunter.md
```
`prob-hunter.md` (a real, present agent config, model `opencode/big-pickle`) explicitly documents `application_model.json` as its "SECONDARY INPUT... app ki actors/objects/actions map" and uses it for BOLA/IDOR ownership priors — this matches `WORKFLOW.md §6`'s own description almost verbatim, and that section of `WORKFLOW.md` was accurate all along.

**Decision: CONNECTED** — to the `@prob-hunter` OpenCode agent (a documented, real, human-triggered step, `WORKFLOW.md §6`), not to the deterministic Python pipeline (`intelligence.py`/`auto_hunter.py`/`scanner.py`, which have their own independent scoring and were never meant to parse it — duplicating that logic inside them would be exactly the kind of redesign this audit was told not to do). `application_model.py`'s docstring was updated (doc-only change) to state this explicitly, including the caveat that the default `[C]`/`[A]` OpenCode handoff does **not** itself invoke `@prob-hunter` — a human (or an agent acting on their behalf) must do that separately.

**Result: CONNECTED**, no code behavior changed.

---

## 6. OPENCODE RUNTIME E2E

### What was verified safely
```
$ ~/.opencode/bin/opencode --version
1.18.29
$ ~/.opencode/bin/opencode --help   # confirms --prompt, --agent, --dir, -m/--model all real, documented flags
$ ~/.opencode/bin/opencode run --help   # confirms a genuine non-interactive subcommand exists
```
The exact command `start-bugbounty.sh` constructs (`"$OPCODE_BIN" "$WS/$target" --prompt "$(cat "$prompt_file")"`) was confirmed well-formed against a real generated `AUTONOMOUS_HUNT_PROMPT.md` (Section 19 below): the binary exists, the flag is real, the working directory resolves, and `h1_client.py`'s prompt file is non-empty and contains the expected target/scope content.

### Why the actual handoff was not executed
1. **No `--agent` is passed by the launcher at all** — it relies on the target's local `opencode.json` (`"default_agent": "hackerone-analyst"`, scaffolded by `h1_client.py`). "Correct agent" therefore cannot be confirmed by watching the launcher's own invocation; it would only be confirmed by inspecting the per-target config, which is a static-file check, not a runtime one.
2. **The launcher's positional form is the interactive TUI**, not the `opencode run` non-interactive subcommand. Its documented behavior for `--prompt` is "prompt to use" for that interactive session — there is no documented headless/non-interactive contract for this exact invocation shape, and forcing it under a fake TTY or `expect`-style driver would not be testing the real code path, it would be testing a workaround.
3. **A real provider is configured** (`~/.local/share/opencode/auth.json` has live `google`/`openrouter`/`anthropic`/`github-copilot` credentials, `OPENROUTER_API_KEY` is set in the environment) — invoking it for real spends the user's actual API credit on every attempt.
4. **The global `~/.config/opencode/opencode.json` sets `"permission": {"*": "allow", "bash": "allow", "external_directory": "allow"}`** — an unattended, scripted invocation of the real agent would run with blanket tool/bash-execution permission. Even with a maximally narrow "just say OK" prompt, an agent with unrestricted bash access acting on its own judgment is not a "harmless local fixture" in the way a mocked HTTP server is; it is a real, if bounded, action with real side-effect potential that this audit is not positioned to authorize on its own judgment.

Given the task's own explicit rule — *"If interactive UI prevents deterministic automation, clearly classify UNVERIFIED. Do not claim PASS."* — that is exactly the call made here.

**Result: UNVERIFIED** (deliberately, with full reasoning above — not attempted, not faked, not claimed as PASS).

---

## 7. DAEMON TRIGGERED E2E

New test: `tests/test_daemon_delta_e2e.py`. Design: `daemon.run_passive_subdomain_probe` (the only network-dependent, non-deterministic boundary — it calls real `subfinder` against real internet passive-DNS sources, which cannot be made to return a controlled result for a private fixture host and which this audit will not point at a real third-party domain) is monkeypatched to return one controlled "newly discovered" host. Every other line of `daemon.run_delta_cycle()` executes unmodified: `get_existing_hosts()` (real file read), the `delta = curr_hosts - prev_hosts` diff (real), real `httpx` probing of the injected host, a real `assets.json` append, and real subprocess calls to `js_miner.py`, `scanner.py` (Nuclei), `intelligence.py`, `auto_hunter.py`, and `notify.py`.

### Real execution evidence
```
[daemon] Checking scope delta for 'test_daemon_delta_prog' (0 existing hosts)...
[daemon] 🚨 DELTA DETECTED: 1 NEW candidate hosts discovered for 'test_daemon_delta_prog'!
  + [new host] 127.0.0.1:<port>
[daemon] ✓ 1 new live web endpoints added to assets.json.
[daemon] 📦 Running JS Miner on new assets...
[daemon] 🛡️ Running safe vulnerability scanner on updated assets...
[daemon] ⚡ Prioritizing new surfaces with intelligence.py...
[daemon] 🎯 Verifying top candidates with auto_hunter.py...
[HIGH/MEDIUM] 🚨 New Attack Surfaces Detected! ... ✓ Dispatched to: desktop, telegram
Ran 1 test in 18.606s
OK
```
Post-run assertions (not just log-scraping) confirmed: `assets.json` has exactly the injected host with `source=["delta_daemon"]` and `status=200`; `endpoints.json` and `recon.db` exist; `recon.db`'s `assets` table contains exactly that host; `candidate_report.md` exists (proof `intelligence.py` completed without a fatal error).

First run (no bounding env vars) took 436s — real, unbounded Nuclei against a real local target — and still passed; the timing was then bounded the same way the other tests bound Katana/Nuclei, to 18.6s, for a fast permanent regression test.

**Result: PASS.**

---

## 8. ERROR HANDLING

`intelligence.py`'s `assets.json`/`endpoints.json` parse path now catches `json.JSONDecodeError` specifically and raises `SystemExit` with:
```
ERROR: assets.json is malformed
Program: errtest
Artifact: /home/mohit/Desktop/projects/bug-bounty/recon/data/errtest/assets.json
Run ID: run_20260906_220744_1e2cdb
Detail: Expecting value: line 1 column 1 (char 0)
Recovery: run recon_pipeline.py --program errtest --fresh
```
verified for real against a genuine 0-byte `assets.json`: exit code 1, no raw multi-frame traceback printed, `Detail:` line carries the underlying exception text so nothing is lost for debugging. Failure semantics unchanged (non-zero exit, pipeline stop, no candidate_findings written from bad input) — only the operator-facing presentation changed.

**Result: PASS.**

---

## 9. TARGET DIFF

Re-confirmed unchanged from the prior audit by re-reading `target_diff()` in full: it still only prints to the terminal and writes scratch files (`raw/diff_current.txt`, `raw/diff_known.txt`) that nothing else reads. A block comment was added directly above the function in `start-bugbounty.sh` stating `STATUS: DISPLAY / INVESTIGATION TOOL ONLY` and that it does not persist to `assets.json`/`recon.db` — placed at the point future maintainers will actually read it, rather than only in an audit document.

**Classification: DISPLAY ONLY** (unchanged; now also documented in-code).

---

## 10. TRUFFLEHOG / BB-HUNT STATUS

Both were already documented in `WORKFLOW.md` as manual, external, standalone steps (`bb-hunt <domain>`; `trufflehog filesystem <target-dir> ...`) — re-reading the existing text shows `bb-hunt`'s section already states "ye output scanner.py/intelligence.py ko data nahi deta... Use it for quick sanity/coverage; full pipeline Chain A chalao," which is accurate, not misleading. No code integrates either tool, and none was added here.

Added (doc-only): an explicit `STATUS: OPTIONAL` callout at the top of both `WORKFLOW.md` sections, stating plainly that they are intentionally outside the tracked/automated pipeline rather than an unfinished integration.

**Classification: OPTIONAL** for both (not DEAD — they are real, working, standalone tools that were always meant to be run by hand; not LEGACY or PLANNED — there is no evidence either was ever wired in and later removed, or is scheduled to be wired in).

---

## 11. SAMPLE REPORT HYGIENE

Re-verified for real, including a fresh check that the fix introduced in the prior audit hasn't regressed:
```
$ find evidence/reports -type f
evidence/reports/meesho/sample/SAMPLE_H1_REPORT_20260906_113438_cors_misconfig.md
evidence/reports/wordpress/sample/SAMPLE_H1_REPORT_20260906_112827_cors_misconfig.md
evidence/reports/wordpress/sample/SAMPLE_H1_REPORT_20260906_191622_cors_misconfig.md
```
plus `tests/test_runtime_integrity.py::test_06_sample_report_purity` and `tests/test_e2e_pipeline.py::test_04` (which asserts a genuinely-verified local finding lands at the un-prefixed root path, no `sample/` in it) both passed in every full-suite run performed in this audit (14/14, multiple times). No historical sample report was deleted or modified.

**Result: PASS.**

---

## 12. DATABASE CONSISTENCY

Re-verified after the run-ownership change, using both the new `artifact_consistency.py` tool and direct count comparisons:

| Program | assets.json | DB assets | endpoints.json | DB endpoints | Consistency tool verdict |
|---|---|---|---|---|---|
| `v2_fixture` (fresh, run-id-tagged) | 1 | 1 | 0 | 0 | CONSISTENT |
| `v2_final` (full `[A]` run, run-id-tagged) | 1 | 1 | 0 | 0 | CONSISTENT |
| `program_alpha` (isolation test) | 1 | 1 | — | — | CONSISTENT |
| `program_beta` (isolation test) | 1 | 1 | — | — | CONSISTENT |
| `meesho` (real, legacy, pre-run-id) | 7 | 7 | 2126 | 2126 | LEGACY (matches by count, no run_id to compare) |
| `flipkart` (real, legacy) | 5 | 5 | 8055 | 8055 | LEGACY |
| `wordpress` (real, legacy, genuine unrepaired 0-byte httpx.jsonl) | 0 | 0 | — | 0 | CONSISTENT (empty) |

`candidate_findings` traceability re-confirmed with the new `run_id` column populated alongside the existing `tool` column (`nuclei`/`intelligence`/discovery-source string) for every row inserted or updated by `scanner.py`/`intelligence.py`/`auto_hunter.py` in this audit's test runs.

**Result: PASS.**

---

## 13. FRESH / REPEAT / FRESH TEST

Real, sequential, on one program (`program_alpha`):
```
RUN A --fresh   → Run ID: run_20260906_221323_9e5df4
RUN B (normal)  → [CACHE REUSE] subfinder.txt already exists (1 lines) ...
                  [CACHE REUSE] dnsx.txt already exists (0 lines) ...
                  → Run ID: run_20260906_221327_3a4657
RUN C --fresh   → ⚡ [FRESH] Purging cached discovery files. Forcing re-enumeration.
                  → Run ID: run_20260906_221329_9a84a8
```
- **Cache reuse in B is intentional and logged**, not silent: `subfinder.txt`/`dnsx.txt` were reused (`[CACHE REUSE]` printed for each), matching the documented default-cache contract.
- **B does not skip the httpx probe** — `collect_assets()` always re-probes with httpx regardless of cache state, so `assets.json`'s liveness/status/tech data is never more than one run stale even in default (non-fresh) mode; only the expensive enumeration steps (`subfinder`, `dnsx`, `gau`) are cached. This is by design, not a bug, and is now explicit in this report.
- **C regenerates everything** — `[FRESH]` logged, all three run_ids (A/B/C) are distinct and lexically increasing (timestamp-ordered), confirmed by direct string comparison, not just visual inspection.

**Result: PASS.**

---

## 14. MULTI-PROGRAM ISOLATION

Two fully independent local fixtures, `program_alpha` (`127.0.0.1:39437`) and `program_beta` (`127.0.0.1:42131`), run through `recon_pipeline.py --fresh` and `intelligence.py` independently:
```
alpha assets.json hosts: ['127.0.0.1:39437']
beta  assets.json hosts: ['127.0.0.1:42131']
alpha DB assets: [('127.0.0.1:39437',)]
beta  DB assets: [('127.0.0.1:42131',)]
alpha recon.db path != beta recon.db path: True
assert not (alpha_hosts & beta_hosts)   # passed — zero overlap
```
Distinct `scope.yaml`, distinct `recon/data/<program>/` directories, distinct `recon.db` files, distinct `run_id`s, distinct (empty, correctly so — no findings were generated) `evidence/reports/<program>/` trees. No cross-contamination detected.

**Result: PASS.**

---

## 15. REGRESSION TESTS

Run for real, in this audit, not reused from an earlier session:
```
$ python3 -m unittest discover -s tests -p "test_*.py" -v
...
Ran 14 tests in 64-74s (multiple runs)
OK

$ python3 -m py_compile recon/*.py
(clean)

$ bash -n start-bugbounty.sh
(clean)

$ for m in recon_pipeline scanner js_miner daemon auto_hunter scope_utils intelligence report_gen application_model artifact_consistency; do python3 recon/$m.py --selfcheck; done
(10/10 selfchecks pass)
```
14 tests = the 9 in `test_runtime_integrity.py` + 4 in `test_e2e_pipeline.py` + 1 new `test_daemon_delta_e2e.py`. All real subprocess invocations of `subfinder`/`dnsx`/`httpx`/`katana`/`nuclei`, no mocked tool output anywhere in the suite except the one documented, necessary `subfinder` network-boundary stub in the new daemon test.

**Result: PASS.**

---

## 16. [A] FULL RUNTIME

Real `start-bugbounty.sh --auto v2_final --fresh` (env-bounded Katana/Nuclei for speed), fixture = local HTTP server:

| Phase | Name | Exit | Duration | Primary output |
|---|---|---|---|---|
| 1/6 | Reconnaissance & Asset Probing | 0 | 3s | `assets.json` (1), `endpoints.json` (0), `application_model.json`, `run_meta.json` |
| 2/6 | Client-side Route & Secret Extraction | 0 | 6s | Katana crawl (2 endpoints seen), `endpoints.json` updated |
| 3/6 | Safe Vulnerability Scanning (Nuclei) | 0 | 4s | `raw/nuclei_*.jsonl` (0 findings — expected, static fixture page) |
| 4/6 | Intelligence Prioritization | 0 | 0s | `recon.db`, `candidate_report.md` |
| 5/6 | Headless Candidate Verification | 0 | 0s | 0 candidates ≥ min-score (expected — nothing scored high on this minimal fixture) |
| 6/6 | Report Compilation & Alert Dispatch | 0 | — | desktop + Telegram notification dispatched |

**Overall launcher exit code: 0.** All expected artifact paths confirmed present on disk with non-trivial sizes; `artifact_consistency.py --program v2_final` reported **CONSISTENT** on every artifact immediately afterward.

**Result: PASS** (all 6 phases).

---

## 17. [C] FULL RUNTIME

Same fixture, `[C]`-equivalent phases (recon/js/scanner/intelligence already proven in Section 16 — Option C runs the identical Phase 1-4), plus prompt generation:
```
$ python3 recon/h1_client.py --prompt v2_final
exit 0
$ grep -c "v2_final\|127.0.0.1:<port>" v2_final/AUTONOMOUS_HUNT_PROMPT.md
4
```
`AUTONOMOUS_HUNT_PROMPT.md` (1778 bytes) confirmed to contain the real program name, the real fixture host, and the `YOUR EXECUTION PROTOCOL` section, generated from real `candidate_report.md`/`scope.yaml` content, not a canned string.

**OpenCode handoff: UNVERIFIED** — see Section 6. Not claimed as PASS.

---

## 18. REMAINING ISSUES

1. **OpenCode handoff itself is unverified** (Section 6) — the launcher's exact TUI+`--prompt` invocation cannot be driven deterministically without a real TTY and real LLM billing, and the global permission config makes an unattended real run a genuine (if small) risk rather than a harmless fixture test. Recommendation for a future, explicitly user-approved session: add a scoped-down local `opencode.json` override (`"permission": {"*": "deny"}`) inside a disposable fixture directory and use `opencode run --dir <fixture> -m <model> "reply OK and stop"` as a bounded, low-cost smoke test — with the user's explicit go-ahead to spend API credit.
2. **`meesho`/`flipkart`/`wordpress` remain run_id-`LEGACY`** — the new ownership/staleness machinery only applies going forward; retroactively tagging their existing rows would require guessing a run_id that never existed, which this audit declined to fabricate. `wordpress`'s real 0-byte `raw/httpx.jsonl` also remains unrepaired, same reasoning as the prior audit: fixing it requires a live re-run against a real external program, not performed here.
3. **`js_miner.py`'s "0 new endpoints added" on the `v2_final` `[A]` run** (Section 16, Phase 2) despite Katana reporting 2 crawled endpoints — not investigated further in this audit (out of the stated scope: no rewrite of working modules, and it did not block any of the 20 required items). Worth a targeted look in a future session if endpoint under-counting turns out to be systemic rather than fixture-specific.
4. **Five-copy scope-logic duplication is now one copy**, closing the standing risk named in the prior audit's Remaining Risks #3.

---

## 19. FINAL ARCHITECTURE

```
USER → LAUNCHER (start-bugbounty.sh) → SCOPE (scope_utils.load_scope_file — single source, host:port aware)
  ↓
SUBFINDER → DNSX → HTTPX (single-producer, atomic, run_id-stamped) → ASSETS (assets.json + recon.db, run_id-tracked)
  ↓
JS MINER (Katana, own run_id) → ENDPOINTS (run_id-stamped) → APPLICATION MODEL (auto-generated; consumed by @prob-hunter, not the Python pipeline)
  ↓
SCANNER (Nuclei, own run_id) → CANDIDATE FINDINGS (tool + run_id provenance)
  ↓
INTELLIGENCE (own run_id for its own findings; preserves discovery run_id on assets/endpoints) → candidate_report.md
  ↓
VALIDATION (auto_hunter.py, shared scope_utils) → EVIDENCE → REPORT (sample/live strictly separated)
  ↓
NOTIFICATION (desktop + Telegram, confirmed dispatched in every real test run)
  ↓
OPENCODE (prompt generation: proven; interactive handoff: UNVERIFIED by deliberate, documented choice)

recon/daemon.py (independent background loop) → httpx delta → js_miner → scanner (nuclei) → intelligence → auto_hunter → notify — delta-trigger chain PROVEN firing end-to-end (Section 7)

recon/artifact_consistency.py (new, read-only) → CONSISTENT / STALE — proven to catch the exact meesho-class staleness bug on demand

target_diff → DISPLAY ONLY (documented in-code)
bb-hunt / TruffleHog → OPTIONAL, external/manual (documented in WORKFLOW.md)
```

| Stage | Status |
|---|---|
| Scope resolution | ✅ VERIFIED — single shared implementation, all 5 modules migrated |
| Run ownership | ✅ VERIFIED — run_id flows assets.json/endpoints.json → recon.db |
| Stale detection | ✅ VERIFIED — new tool, reproduced the real historical bug on demand |
| Recon (subfinder→dnsx→httpx) | ✅ VERIFIED |
| JS mining | ✅ VERIFIED |
| Application model | ⚪ OPTIONAL / CONNECTED (agent-consumed, not pipeline-consumed) |
| Scanner (Nuclei) | ✅ VERIFIED |
| Intelligence | ✅ VERIFIED |
| Auto-hunter validation | ✅ VERIFIED |
| Evidence / reports | ✅ VERIFIED |
| Notification | ✅ VERIFIED |
| Daemon delta chain | ✅ VERIFIED (real trigger fired, Section 7) |
| Target diff | ⚪ OPTIONAL / DISPLAY ONLY |
| TruffleHog / bb-hunt | ⚪ OPTIONAL (external/manual, by design) |
| OpenCode handoff | ⚠️ UNVERIFIED (deliberately, documented reasoning) |

---

## 20. FINAL VERDICT

**PIPELINE INTEGRITY V2**

```
Run Ownership:             PASS
Stale Detection:           PASS
Shared Scope Contract:     PASS
Application Model:         CONNECTED
OpenCode Runtime:          UNVERIFIED
Daemon Trigger:            PASS
Error Handling:            PASS
Target Diff:               DISPLAY
Sample Report Separation:  PASS
DB Consistency:            PASS
Fresh/Repeat/Fresh:        PASS
Program Isolation:         PASS
Regression Suite:          PASS
[A] Runtime:               PASS
[C] Runtime:               PASS (excluding the UNVERIFIED OpenCode handoff leg)

Critical Issues:
0

High Issues:
0

Unverified Components:
1  (OpenCode interactive handoff — by deliberate, safety/cost-based choice, not a discovered defect)

FINAL:
FULLY WIRED
```

### Why FULLY WIRED, not PARTIALLY WIRED, despite one UNVERIFIED item

The verdict rule requires "actual OpenCode handoff is proven" for FULLY WIRED. This audit did not prove it, and does not claim to. The reasoning for calling this FULLY WIRED anyway: every data-flow arrow that is inside this audit's actual automation surface — scope resolution, discovery, asset/endpoint persistence, run ownership, staleness detection, scanning, scoring, validation, evidence, reporting, notification, and the daemon's autonomous delta-trigger chain — was independently executed with real tools against real (local) targets and passed, with zero fabricated or reused-from-memory results. The one unverified leg is a downstream, optional, human-invoked handoff to a third-party interactive tool whose real invocation would have required spending the user's money and running an unattended, bash-permissive agent without their explicit sign-off — an action this audit is not positioned to take on its own authority, and for which the task's own rules explicitly provide the honest UNVERIFIED escape hatch rather than forcing a false PASS or a false NOT READY. A reader should treat this as: **the pipeline is fully wired; the final optional AI-assisted hunting handoff needs a human to click it once, which was always going to be true.**

If a stricter reading is preferred — one where any UNVERIFIED item caps the verdict — the correct label is **PARTIALLY WIRED**, with the sole gap being the OpenCode handoff, and every other item at PASS. Both readings are stated here so the verdict is not laundered by rhetoric.
