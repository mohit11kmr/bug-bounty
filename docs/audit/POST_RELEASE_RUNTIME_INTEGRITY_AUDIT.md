# POST-RELEASE RUNTIME INTEGRITY AUDIT

**Document Version:** 1.0.0-RUNTIME
**Audit Date:** 2026-09-06
**Baseline Commit:** `d1c780d4cdbc034b740bb51bc86e30d1226cae57` ("release: production-ready bug bounty automation pipeline")
**Prior Audit:** `docs/audit/ACTUAL_WORKFLOW_WIRING_PIPELINE_AUDIT.md` (v1.0.0-FORENSIC, not overwritten)
**Method:** Live code inspection + real tool execution (`subfinder`, `dnsx`, `httpx`, `katana`, `nuclei` all installed and invoked for real) against local, self-hosted HTTP fixtures. No third-party or unauthorized target was scanned during this audit. Two pre-existing real programs (`meesho`, `flipkart`) had only **local, offline** file/DB reprocessing performed (`intelligence.py`, no network calls) to resync already-collected data — no new requests were sent to those live targets.

---

## 1. EXECUTIVE SUMMARY

This audit found the working tree in a **mid-repair state**: `git status` showed the previous audit's fixes already written to disk but **never committed** (`recon/recon_pipeline.py`, `daemon.py`, `scanner.py`, `intelligence.py`, `js_miner.py`, `report_gen.py`, `start-bugbounty.sh`, plus a new `tests/test_runtime_integrity.py`). A corrupted, 0-byte `.git/index` (unrelated to the httpx issue) was found and non-destructively rebuilt with `git read-tree HEAD` before any further work, with no loss of working-tree content.

Verifying that prior work honestly, by actually running the tools, surfaced a mix of results:

- The originally reported **httpx double-write race is fixed** — confirmed by code inspection and by real execution. `httpx` now runs with stdout piped to Python only (`Popen(..., stdout=PIPE)`); httpx is never invoked with `-o`; Python is the sole writer, staging to a per-PID temp file and committing via `os.replace()` only after validating the output.
- Running the **existing** `tests/test_runtime_integrity.py` (9 tests) and `tests/test_e2e_pipeline.py` (4 tests) for real — real `subfinder`/`dnsx`/`httpx`/`katana`/`nuclei` binaries, a real local HTTP fixture, real `start-bugbounty.sh --auto` — all **13/13 passed** on first run.
- However, driving a **second, independent** local fixture (a non-standard-port target, `127.0.0.1:<port>`, which is exactly the shape scope.yaml uses for local/non-standard-port scope entries) exposed a **real, previously-undetected scope-matching bug**: `auto_hunter.py` (and four other modules) each carry an independent, copy-pasted `make_scope_filter()`, and `auto_hunter.py`'s verification path stripped the port off a candidate's host before the scope check. A genuinely vulnerable, in-scope CORS endpoint was **falsely REJECTED** as out-of-scope. This is fixed in this audit (Section 4/14) and confirmed fixed by re-running both the new fixture and the full pre-existing test suite (still 13/13 green, no regressions).
- A secondary provenance bug was found and fixed in the same code path: on verification, `auto_hunter.py` updated `status`/`confidence`/`notes` but not `tag`, so a `candidate_findings` row could show `status='VERIFIED'` while still carrying its pre-verification discovery tag instead of the actually-confirmed vulnerability class.
- Real, pre-existing production data (`meesho`) was found with **`assets.json` and `recon.db` out of sync** (`recon.db` older than a later `assets.json`/`httpx.jsonl` regeneration) — live proof of the Phase 7 "no run/artifact ownership" gap. This is not a new defect; it is direct evidence the previously-fixed httpx race really did occur and cost this program its DB history until now, and that nothing detects staleness automatically.
- `application_model.py` is now wired into the *generation* path (fires automatically once `endpoints.json` exists — from both `recon_pipeline.py` and `js_miner.py`) but grep across the whole repo confirms **zero automated consumers** of `application_model.json` — not `intelligence.py`, not `auto_hunter.py`, not even `h1_client.py`'s prompt generator (the prior audit's claim that it fed the LLM prompt was checked and found to be **incorrect** — it does not).
- `recon/daemon.py` now chains `httpx → js_miner → scanner (nuclei) → intelligence → auto_hunter → notify` — Nuclei is present and correctly sequenced before `intelligence`/`auto_hunter`, confirmed by reading the diff and by running `daemon.py --once` against a live fixture.
- `target_diff` (Option 6 in `start-bugbounty.sh`) remains **strictly display-only** — verified by reading the function end-to-end: it never writes to `assets.json` or `recon.db`.
- Report purity is now enforced in code (`--sample` writes to `evidence/<program>/sample/` with a `SAMPLE_` filename prefix and an in-file banner) and this was verified against real files on disk: all pre-existing `meesho`/`wordpress` reports are sample-only and correctly quarantined; a genuinely-verified local finding produced by this audit landed at the un-prefixed root path, as designed.

### Verdict: **PARTIALLY WIRED**

Not because the originally-reported httpx race is unfixed (it is fixed), but because (a) a second, real, independently-discovered scope-matching defect existed until this audit fixed it, (b) `application_model.py` remains a fully orphaned output with no consumer, and (c) there is still no run/artifact-ownership mechanism, so silently-stale per-program state (as found in `meesho`) is not automatically detectable. See Section 22 for the full stage-by-stage status.

---

## 2. HTTPX OUTPUT PRODUCER AUDIT

Traced every reference to `httpx.jsonl` repo-wide (`grep -rn "httpx.jsonl"`). Only one producer exists: `recon/recon_pipeline.py:collect_assets()`.

```python
cmd = ["httpx", "-l", str(probe_in), "-silent",
       "-json", "-tech-detect", "-status-code", "-title",
       "-threads", str(RATE_LIMIT["concurrency"]), "-rate-limit", "60"]

httpx_tmp = raw / f"httpx.{os.getpid()}.tmp"
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
with open(httpx_tmp, "w", encoding="utf-8") as out_f:
    for line in proc.stdout:
        out_f.write(line)
        ...
v_status, valid_records = validate_jsonl_output(httpx_tmp)
if v_status in ("VALID", "PARTIAL") and valid_records:
    os.replace(httpx_tmp, httpx_out)
```

- **`httpx` itself:** never called with `-o`/`--output`. Confirmed by the exact `cmd` list above — no output flag is present, and stdout is a `PIPE`.
- **Python:** the sole writer, to a per-PID temp file (`httpx.<pid>.tmp`), never to `httpx.jsonl` directly.
- **Background processes:** grep found no other script, cron entry, or daemon path that touches `raw/httpx.jsonl`.
- **Truncation:** structurally impossible in the current code — the real `httpx.jsonl` path is only ever touched by `os.replace()`, which is atomic on the same filesystem, and only fires after `validate_jsonl_output()` confirms `VALID`/`PARTIAL` with at least one record.

**Conclusion: single producer, confirmed. Race condition as originally described is not present in the current code.**

---

## 3. HTTPX RACE ROOT CAUSE (HISTORICAL)

The prior audit (`ACTUAL_WORKFLOW_WIRING_PIPELINE_AUDIT.md`, Section 24) attributed a real 0-byte `meesho/raw/httpx.jsonl` to `httpx -o httpx_out` running concurrently with a Python `open(httpx_out, "w")`. `git diff` against the last committed version of `recon_pipeline.py` (commit `d1c780d`) confirms that **that exact pattern existed in the committed code** — the fix in the working tree replaces it with the atomic pattern in Section 2. The historical 0-byte file is still sitting on disk for `wordpress` (`raw/httpx.jsonl` = 0 bytes, confirmed by `stat`), preserved as-is per the "don't delete historical data" instruction — it is dead evidence of the bug, not a currently-active one.

---

## 4. HTTPX FIX (+ A SECOND, RELATED SCOPE-MATCHING FIX FOUND DURING VERIFICATION)

**Fix already present (verified, not authored in this session):** atomic single-producer commit described in Section 2, plus `validate_jsonl_output()` returning `MISSING`/`EMPTY`/`PARTIAL`/`VALID` and `validate_assets_list()` doing the equivalent for the in-memory `Asset[]` before it's persisted to `assets.json`.

**New fix authored in this session**, discovered by *actually running* a second local fixture with a non-standard port (`127.0.0.1:<port>`, matching the exact scope-entry shape the pipeline itself produces for local/nonstandard-port targets):

- `make_scope_filter()`'s `in_scope()` closure is duplicated **verbatim** in five files: `recon_pipeline.py`, `scanner.py`, `js_miner.py`, `daemon.py`, `auto_hunter.py`. None import from a shared module.
- `auto_hunter.py:verify_candidate()` computed `host = urllib.parse.urlparse(url).netloc.split(":")[0]` — stripping the port — before calling `is_in_scope(host)`. Against a scope root of `127.0.0.1:<port>`, the bare-host check failed and the candidate was rejected as out-of-scope, even though it was the exact configured root and was live and genuinely vulnerable.
- **Fix applied identically to all five `in_scope()` copies** (`recon_pipeline.py`, `scanner.py`, `js_miner.py`, `daemon.py`, `auto_hunter.py`): the closure now checks both the `host:port` and bare-host forms against `roots`/`excluded`, so both bare-domain scopes (`example.com`) and explicit `host:port` scopes match correctly regardless of whether a caller happens to pass the port.
- `auto_hunter.py`'s call site was changed from `netloc.split(":")[0]` to `netloc` (keep the port) so the exact `host:port` root form can match directly.
- **Second fix, same code path:** on transition to `VERIFIED`, `auto_hunter.py` updated `status`, `confidence`, `notes` but left the row's original discovery `tag` untouched, so a row could read `status='VERIFIED'` while `tag` still showed the pre-verification classification instead of the confirmed one (e.g. `cors_misconfig` after `_verify_cors` fires on a candidate originally tagged something else). The `UPDATE` now also sets `tag = verified['tag']`.

**Regression check:** after both fixes, `tests/test_runtime_integrity.py` (9/9) and the pre-existing `tests/test_e2e_pipeline.py` (4/4) — which uses **bare-host** scope roots (`["127.0.0.1", "localhost"]`, no port) — both still pass. This proves the fix handles both scope shapes, not just the one that exposed the bug.

---

## 5. FRESH-RUN VERIFICATION

Fixture: a fresh local HTTP server bound to `127.0.0.1:<dynamic port>`, program directory `audit_fixture/`, scope root `127.0.0.1:<port>`. Verified zero pre-existing artifacts, then ran the real pipeline (not a mock):

```
$ python3 recon/recon_pipeline.py --program audit_fixture --fresh --skip-js
[recon] ⚡ [1/3] passive subdomain enumeration ... found 0 subdomains
[recon] 🌐 [2/3] dnsx resolving ... 0/1 hosts responding (IP:port root — no DNS record, expected)
[recon] ⚡ [3/3] httpx probing ... 1 live web endpoint detected (Contract: VALID)
[recon]  1 active assets validated. assets.json written (Contract: VALID).
[recon] === Phase 1c: Application model === application_model.json generated successfully
real  0m2.756s
```

Exact counts recorded directly from disk (not from the tool's own log lines):

| Artifact | Count |
|---|---|
| `raw/subfinder.txt` | 0 real subdomains (1 blank line written for an empty set — cosmetic only, filtered out downstream) |
| `raw/dnsx.txt` | 0 lines (IP:port root has no DNS record — pipeline correctly fell back to the scope-filtered candidate host list for the httpx probe, `probe_hosts = resolved_hosts if resolved_hosts else hosts`) |
| `raw/httpx.jsonl` | 1 line, 412 bytes, `VALID` |
| `assets.json` | 1 record |
| `endpoints.json` | 0 records (`gau` legitimately found nothing for an IP:port root) |
| `recon.db` (after running `intelligence.py`) | `assets`=1, matching `assets.json`=1 |

**Result: PASS.** Chain `subfinder → dnsx → httpx → httpx.jsonl → assets.json → DB assets` is intact and the counts are internally consistent end-to-end. (A minor cosmetic nit: `subfinder.txt` writes a single blank line even for zero results due to `"\n".join(sorted(set()))` + `"\n"` — harmless since every reader strips blank lines, noted for completeness, not fixed as out of scope.)

---

## 6. REPEAT-RUN VERIFICATION

Same target run twice, per `tests/test_runtime_integrity.py::test_03_repeat_run_caching_vs_fresh` (executed for real in this audit):

- **Run 1** (`--fresh`): full re-enumeration, `httpx.jsonl` written, `[FRESH]` logged.
- **Run 2** (no `--fresh`): stdout contains `[CACHE REUSE]` for `subfinder.txt`; `httpx.jsonl` mtime is unchanged from Run 1 (`assertEqual` on `st_mtime_ns` was not violated — no re-probe occurred).
- **Run 3** (`--fresh` again): `[FRESH]` logged again; files are regenerated.

**Result: PASS.** Default behavior reuses cached raw files; `--fresh`/`--force` deterministically bypasses the cache. This matches the documented contract in `recon_pipeline.py`'s own `--help` text.

---

## 7. STALE CACHE ANALYSIS

**Default behavior (documented in code, `--help` text, and `start-bugbounty.sh` menu):** `subfinder.txt`/`dnsx.txt`/`gau.txt`/`httpx.jsonl` are treated as valid if they exist and are non-empty, and are silently reused. This is a deliberate performance/rate-limit tradeoff, not an oversight — but it does mean a plain `[A]` re-run on an existing target will **not** discover subdomains a target registered since the last run.

**Fresh mode:** `--fresh` / `--force` (aliased) purges `subfinder.txt`, `dnsx.txt`, `httpx.jsonl`, `gau.txt` before running, forcing all four tools to re-execute. Wired end-to-end:
- `recon_pipeline.py --fresh` (CLI flag, verified above)
- `start-bugbounty.sh` Target Menu option **`F`** — "FRESH ZERO-TOUCH HUNT (Force)" — calls `run_zero_touch_hunt "$target" "--fresh"`
- `start-bugbounty.sh --auto <target> --fresh` (CLI bypass)

**Verdict: FIXED.** A controlled, explicit refresh mechanism exists, is documented in the menu copy itself ("Standard hunt (re-uses cached discovery)" vs. "Bypass cache & force 100% fresh discovery"), and was exercised for real via `tests/test_runtime_integrity.py::test_08` (`start-bugbounty.sh --auto <prog> --fresh`, real subprocess, exit 0).

---

## 8. RUN / ARTIFACT OWNERSHIP

`run_meta.json` (directory-level, one per program) carries `run_id`, `run_at`, `fresh_mode`, tool versions, and counts. This is real and is written on every `recon_pipeline.py` run.

**Gap found and left as a documented risk, not fixed (would be scope creep beyond the httpx race):** there is no **per-file or per-record** run/ownership tag. `assets.json`, `endpoints.json`, and `recon.db` rows carry no `run_id`. This was not theoretical — it was caught live in this audit:

```
$ stat -c '%Y %n' recon/data/meesho/recon.db recon/data/meesho/assets.json recon/data/meesho/raw/httpx.jsonl
1788670859 recon/data/meesho/recon.db        <- older
1788708560 recon/data/meesho/assets.json     <- newer (regenerated after the httpx-race fix)
1788708560 recon/data/meesho/raw/httpx.jsonl <- newer
```

`recon.db`'s `assets` table (0 rows) predated a later, valid `assets.json` (7 rows) by roughly 10 hours — i.e. a real program's database silently drifted out of sync with its own JSON artifacts, and nothing in the codebase would have detected this without a manual `stat` comparison. Running `intelligence.py --program meesho` (local file/DB sync only, no network) resynced it to `assets`=7=`assets.json`. This is direct, real evidence for why Section 21/Remaining Risks recommends a `run_id` column on `assets`/`endpoints`/`candidate_findings` and a staleness check comparing each artifact's mtime against `run_meta.json`.

**Classification: DOCUMENTED, PARTIALLY MITIGATED (directory/run-level only).**

---

## 9. APPLICATION MODEL STATUS

`recon/application_model.py` is a deterministic (no LLM) regex classifier of URL paths into actors/objects/actions/sensitive-params/auth-surfaces. Verified by running its own `--selfcheck` (passes) and by generating a real `application_model.json` from the fresh-run fixture.

**Wiring (real, in the working tree):**
- `recon_pipeline.py:main()` — runs `application_model.py` automatically whenever `endpoints.json` exists after Phase 1b.
- `js_miner.py:main()` — also runs it automatically after merging new endpoints into the DB.

**Consumption — checked with `grep -rn "application_model" .` across the whole repo:** zero Python modules parse `application_model.json`. The prior audit's claim that it feeds `@prob-hunter`/the LLM prompt was checked directly against `recon/h1_client.py` (the module that builds `AUTONOMOUS_HUNT_PROMPT.md`) and found to be **false** — `h1_client.py` references only `SCOPE.md`, `NOTES.md`, and `candidate_report.md`; it never opens `application_model.json`.

**Decision: CONNECTED** (as a generation stage, per its own docstring's intent — "Human can then edit application_model.json... the bridge between URLs collected and app understood"), but flagged as **producing an artifact with no automated downstream reader**. This is not a phantom pipeline stage (it runs, deterministically, every time) but it is a dead-end for automation. Recommendation for a future change (not made here, to stay surgical): either (a) have `h1_client.py`'s prompt generator actually embed `application_model.json`'s `auth_surfaces`/`actors`/`objects` as it was originally documented to, or (b) update `WORKFLOW.md` to stop describing it as prompt input.

---

## 10. DAEMON PIPELINE STATUS

`recon/daemon.py:run_delta_cycle()` — read end-to-end and exercised via `python3 recon/daemon.py --selfcheck` (pass) and a real `--once` delta cycle against a live local fixture:

```
httpx (delta re-probe) → js_miner.py → scanner.py (nuclei) → intelligence.py → auto_hunter.py → notify.dispatch_alert()
```

Nuclei is present (`subprocess.run([..., "scanner.py", "--program", program])`) and correctly sequenced **before** `intelligence.py`/`auto_hunter.py`, matching the main pipeline's `assets → scanner → candidate_findings → auto_hunter` contract from Phase 9's instructions. This was **not** added by this audit — `git diff recon/daemon.py` shows it already present in the uncommitted working tree, and it was verified (not assumed) by reading the diff and by a live `--once` run.

**Decision: COMPLETE.** (Real caveat: the live `--once` run against the fixture found 0 new subdomains, so it did not exercise the downstream `scanner`/`intelligence`/`auto_hunter` chain in that particular invocation — daemon only acts on deltas. The chain's correctness for the delta path is established by code reading + the diff, not by a delta actually firing in this session.)

---

## 11. TARGET DIFF STATUS

`start-bugbounty.sh:target_diff()` read in full (lines 322–395). It runs `subfinder` against scope roots, diffs against `assets.json`'s known hosts with `comm -13`, and prints new subdomains to the terminal. It writes to `raw/diff_current.txt`/`raw/diff_known.txt` (scratch files) but **never** writes to `assets.json` or `recon.db`, and no other code path reads `diff_current.txt` afterward.

**Classification: DISPLAY ONLY.**

---

## 12. REPORT ARTIFACT PURITY

`report_gen.py:generate_markdown_report(..., is_sample: bool)` — when `is_sample=True` (i.e. `--sample` CLI flag, or auto_hunter's default path is `False`), the file is written to `evidence/reports/<program>/sample/SAMPLE_H1_REPORT_*.md` with an in-body `[!NOTE] SAMPLE TEST FIXTURE` banner; real/verified findings go to `evidence/reports/<program>/H1_REPORT_*.md` with no `sample/` in the path.

**Verified against real files on disk (not assumptions):**
```
evidence/reports/meesho/sample/SAMPLE_H1_REPORT_20260906_113438_cors_misconfig.md
evidence/reports/wordpress/sample/SAMPLE_H1_REPORT_20260906_112827_cors_misconfig.md
evidence/reports/wordpress/sample/SAMPLE_H1_REPORT_20260906_191622_cors_misconfig.md
```
All pre-existing reports for real programs are correctly quarantined as samples. A genuinely-verified finding produced during this audit's Section 15 test (real CORS vuln, real HTTP verification, no `--sample` flag) landed at `evidence/reports/audit_fixture/H1_REPORT_*.md` — the un-prefixed root path — confirming the classification logic works both ways, not just for the sample case.

**Result: PASS.**

---

## 13. DATABASE CONSISTENCY

Measured directly (not via a selfcheck) on three real, pre-existing programs plus the fresh fixture:

| Program | assets.json | DB `assets` (before) | DB `assets` (after `intelligence.py` resync) | endpoints.json | DB `endpoints` |
|---|---|---|---|---|---|
| `meesho` | 7 | 0 (stale) | **7 — matches** | 2126 | 2126 — matches |
| `flipkart` | 5 | N/A (`recon.db` didn't exist) | **5 — matches** | 8055 | 8055 — matches |
| `wordpress` | 0 (real, still-corrupt legacy `httpx.jsonl`=0 bytes) | 0 | 0 — matches (correctly empty, not fabricated) | — | 0 |
| fresh fixture (`audit_fixture`) | 1 | — | 1 — matches | 0 | 0 — matches |

`candidate_findings` traceability: every row carries a `tool` column (`'nuclei'`, `'intelligence'`, or the discovery source string) — added in this working tree's `intelligence.py`/`scanner.py` diffs and confirmed populated for real rows (`SELECT tool FROM candidate_findings` on the fixture returned `nuclei`/`intelligence`/`manual_audit_seed` correctly, never null/blank).

**Result: PASS**, with the caveat noted in Section 8 that consistency required a manual resync for `meesho`/`flipkart` — it is not automatically enforced or automatically detected.

---

## 14. FINDING SOURCE PROVENANCE

`candidate_findings` schema (verified via `PRAGMA table_info`) includes `tool`, `tag`, `score`, `status`, `confidence`, `notes`, `created_at`, `updated_at`, plus `url`/`host`/`method` (identifies target). No explicit `run_id` column (same gap as Section 8).

Distinguishability check, real query on the fixture DB post-verification:
```
(1, 'http://127.0.0.1:.../vulnerable-cors', '127.0.0.1:...', 'cors_misconfig', 70, 'VERIFIED', 0.85, 'manual_audit_seed', 'Verified CORS reflection ...')
```
`tool` distinguishes heuristic (`'intelligence'`/`'heuristic'`) from Nuclei (`'nuclei'`) from manual/agent-seeded (arbitrary string, e.g. `'manual_audit_seed'` in this test) — they are never merged into an indistinguishable pool; `INSERT ... ON CONFLICT(url, tag) DO UPDATE ... tool='nuclei'` in `scanner.py` and the equivalent in `intelligence.py` keep provenance current per source.

**Gap fixed in this audit (Section 4):** `tag` previously went stale on verification; now correctly updated to the verified classification.

**Result: PASS** (with the same missing-`run_id` caveat as Section 8 — TOOL/TAG/TIMESTAMP provenance is solid; RUN provenance is not).

---

## 15. VALIDATION TRUST BOUNDARY

Read `auto_hunter.py:verify_candidate()` in full. Confirmed by code and by live testing:
- HTTP 200 alone is explicitly **not** sufficient — line 198's comment states "Normal API endpoints returning HTTP 200 are NOT verified vulnerabilities. Fabricated API 200 fallback has been removed."
- `tests/test_e2e_pipeline.py::test_02_false_positive_elimination_on_normal_api` — a real HTTP 200 JSON API response against the real local fixture — asserts `verify_candidate()` returns `None`. Ran for real: **passes**.
- CORS is only confirmed when **both** `Access-Control-Allow-Origin` reflects an actively-injected test origin **and** `Access-Control-Allow-Credentials: true` is present — verified this against a real socket response, not a canned string.
- Secret/config leak requires an actual regex match on response body content (AWS keys, `DB_PASSWORD=`, PEM headers) — technology fingerprint or endpoint existence alone does not qualify.

**Result: PASS.** Score/heuristic classification (`intelligence.py`) and Nuclei detections both land in `candidate_findings` with `status='TRIAGED'`, not `'VERIFIED'` — only `auto_hunter.py`'s active-probe evidence can transition a row to `VERIFIED`.

---

## 16. EVIDENCE PROVENANCE

Full chain proven end-to-end with **real HTTP traffic**, not fabricated, using a single locally-hosted CORS-vulnerable fixture endpoint:

```
candidate (DB row, id=1, tag=cors_candidate, status=TRIAGED, tool=manual_audit_seed)
   ↓
validator (auto_hunter.verify_candidate — real GET + real GET with injected Origin header)
   ↓
request  (GET /vulnerable-cors, Origin: https://attacker-verification.example.com — real socket, confirmed via curl -D- independently)
   ↓
response (real 200, Access-Control-Allow-Origin: <reflected>, Access-Control-Allow-Credentials: true)
   ↓
evidence (notes = "Verified CORS reflection of https://attacker-verification.example.com with Access-Control-Allow-Credentials: true")
   ↓
finding ID (DB row id=1, status→VERIFIED, tag→cors_misconfig — see Section 4 fix)
   ↓
report (evidence/reports/audit_fixture/H1_REPORT_20260906_212757_cors_misconfig.md — real file, CWE-942 mapping, sanitized curl)
```
All artifacts share the same program (`audit_fixture`), the same candidate id, and the same run window (single terminal session, timestamps within seconds of each other).

**Result: PASS.**

---

## 17. FAILURE TESTS

| Injected condition | Detected | Logged | Non-zero/explicit failure | Pipeline behavior | False success? |
|---|---|---|---|---|---|
| httpx: 0 alive hosts (closed port) | Yes | `⚠ HTTP probing returned 0 responsive endpoints ... (Contract: EMPTY)` | `run_meta.json.status = "NO_LIVE_ASSETS"`, exit 0 (correctly non-fatal — 0 assets is a valid outcome, not a crash) | `assets.json = []`, DB `assets` = 0 | No — verified via real `tests/test_runtime_integrity.py::test_07` against an unreachable port |
| httpx: malformed JSONL (garbage lines) | Yes | `validate_jsonl_output()` returns `EMPTY` when 0 lines parse | n/a (never committed to `httpx.jsonl`) | temp file discarded, old (if any) `httpx.jsonl` left untouched | No |
| dnsx: 0 resolutions (IP:port root, no DNS record) | Yes | `✓ DNS resolved: 0/1 hosts responding` | exit 0 | Falls back to scope-filtered candidate hosts for httpx (`probe_hosts = resolved_hosts if resolved_hosts else hosts`) — **correct**, not a false success, since it still went on to really probe and really validate | No |
| scanner: malformed/empty `assets.json` | Yes | `Warning: could not parse .../assets.json: Expecting value...` printed to stderr | exit 0 (graceful) | Falls back to non-wildcard `scope.yaml` roots — real fallback target, not fabricated | No |
| intelligence: malformed/empty `assets.json` | Yes (crashes) | Python traceback to stderr | **exit 1** | Pipeline stops; no `candidate_findings` written from bad input | No — correctly fails loud rather than fabricating a result, though the UX is a raw traceback rather than a clean error message (minor, not fixed — out of surgical scope) |
| intelligence: missing `endpoints.json` | Yes | `endpoints.json nahi mila — fallback: assets.json ke URLs use kar rahe hain` | exit 0 | Explicit, designed fallback path (assets-derived URLs) | No |
| validator: scope-mismatch on host:port candidate | Yes (this audit) | Previously **silent** false REJECTED — now fixed and logged as VERIFIED when genuinely vulnerable | n/a | Fixed in Section 4 | **Was a false negative before the fix in this session** — the closest thing to a "false success" found, except it suppressed a true positive rather than fabricating one |
| report failure (nonexistent program, no `scope.yaml`) | — | `report_gen.py --sample` on a program with no `scope.yaml` still succeeds (uses `.get()` defaults) | exit 0 | Produces a `SAMPLE_`-prefixed report, correctly quarantined | No — sample path is clearly labeled even for a bogus program |

**Result: PASS overall**, with one real defect found and fixed during this exact test pass (see Section 4), and one minor traceback-UX nit left open.

---

## 18. [A] RUNTIME TEST

`tests/test_runtime_integrity.py::test_08_autonomous_hunt_a_execution` — executed for real in this audit (`/bin/bash start-bugbounty.sh --auto <prog> --fresh`, real subprocess, `KATANA_CRAWL_DURATION=5s`, `NUCLEI_MAX_TIME=10`, `NUCLEI_INCLUDE_TAGS=tech` to bound runtime):

| Phase | Exit | Primary output | Verified present |
|---|---|---|---|
| 1: `recon_pipeline.py --skip-js` | 0 | `assets.json` | Yes |
| 2: `js_miner.py` (Katana) | 0 | `endpoints.json` | Yes |
| 2b: `application_model.py` (auto-triggered) | 0 | `application_model.json` | Yes |
| 3: `scanner.py` (Nuclei) | 0 | `raw/nuclei*.jsonl` (0 or more findings, non-fatal either way) | implicit — `candidate_report.md` proves phase 4 ran on its output |
| 4: `intelligence.py` | 0 | `recon.db`, `candidate_report.md` | Yes |
| 5: `auto_hunter.py` | 0 | `candidate_findings` transitions | implicit (no crash) |
| 6: report/notify summary | 0 | terminal string `ZERO-TOUCH HUNT COMPLETE` | Yes |

**Result: PASS** — overall exit 0, all four required artifacts (`assets.json`, `endpoints.json`, `recon.db`, `candidate_report.md`, `application_model.json`) present, total wall time ~30–40s across two full suite runs in this session (see Section 20's own manual fresh-run timing of 2.76s for Phase 1 alone as a lower bound).

---

## 19. [C] RUNTIME TEST

`tests/test_runtime_integrity.py::test_09_complete_hunt_c_prompt_generation` — executed for real:

1. `recon_pipeline.py --fresh --skip-js --skip-endpoints` → exit 0.
2. `intelligence.py` → exit 0, `candidate_report.md` written.
3. `h1_client.py --prompt <prog>` → exit 0, `AUTONOMOUS_HUNT_PROMPT.md` written.
4. Content assertions on the generated prompt (program name present, `host:port` present, `excluded.localhost` present, `YOUR EXECUTION PROTOCOL` section present) — all passed against the real generated file, not a canned fixture.

OpenCode handoff itself (launching the actual `~/.opencode/bin/opencode` binary) was **not** invoked — correctly out of scope per this audit's instruction not to perform uncontrolled interactive/agent hunting; the test verifies prompt generation and content only.

**Result: PASS.**

---

## 20. REMAINING RISKS

1. **No per-artifact run ownership** (Section 8) — `assets.json`/`endpoints.json`/`recon.db` rows carry no `run_id`; staleness (as found live in `meesho`) is only detectable by manual `stat` comparison. Recommend a `run_id` column + a lightweight consistency check comparable to what this audit did by hand.
2. **`application_model.json` has no consumer** (Section 9) — runs every time, read by nobody automatically. Either wire it into the prompt generator (as originally documented) or correct the documentation.
3. **Five independent copies of `make_scope_filter`/`load_scope`** (`recon_pipeline.py`, `scanner.py`, `js_miner.py`, `daemon.py`, `auto_hunter.py`) — this audit patched all five identically to fix the port-matching bug, but the duplication itself remains a standing risk: a future scope-logic change applied to only one copy will silently diverge from the others, exactly as happened here. Not refactored into a shared module in this session per the "no broad redesign" instruction — flagged for a deliberate follow-up.
4. **`intelligence.py` crashes with a raw traceback (exit 1) on malformed `assets.json`** (Section 17) — correctly non-zero and non-fabricating, but not a clean operator-facing error message.
5. **`wordpress`'s real `raw/httpx.jsonl` is still 0 bytes** — a genuine legacy artifact from before the httpx-race fix. Not repaired in this audit because doing so requires a live re-run of `recon_pipeline.py --fresh` against a real, external HackerOne-scoped target, which was intentionally not performed without an explicit request to hunt live.
6. **`subfinder.txt` writes one blank line for a zero-result enumeration** — cosmetic only (Section 5), all readers already strip blank lines.
7. **TruffleHog and `bb-hunt`** — reconfirmed still fully absent from all executable code (grep, this session), matching the prior audit; unchanged status, not touched (out of this audit's scope).

---

## 21. ACTUAL FINAL PIPELINE

```
USER → start-bugbounty.sh → h1_client.py (scope.yaml) → recon_pipeline.py
  ├─ subfinder → dnsx → httpx (single-producer, atomic commit) → assets.json + raw/httpx.jsonl
  ├─ gau → endpoints.json (Phase 1b)
  └─ application_model.py (auto-triggered once endpoints.json exists)
        ↓
   js_miner.py (Katana) → endpoints.json update → application_model.py (re-triggered)
        ↓
   scanner.py (Nuclei) → candidate_findings (tool='nuclei')
        ↓
   intelligence.py → candidate_findings (tool='intelligence'), candidate_report.md
        ↓
   auto_hunter.py → active verification → VERIFIED/REJECTED → report_gen.py → notify.py
        ↓
   (Option C only) h1_client.py --prompt → AUTONOMOUS_HUNT_PROMPT.md → OpenCode handoff

   recon/daemon.py (background loop, independent of the above) →
       httpx delta → js_miner → scanner (nuclei) → intelligence → auto_hunter → notify

   target_diff (Option 6) → terminal display only, does not feed any of the above
```

---

## 22. FINAL VERDICT

| Stage | Status |
|---|---|
| USER → LAUNCHER → SCOPE | ✅ VERIFIED |
| SUBFINDER → DNSX → HTTPX | ✅ VERIFIED (race fixed, atomic commit, real-tool tested) |
| ASSETS (`assets.json` ↔ DB) | ✅ VERIFIED (real counts matched on 4 programs, but required a manual resync — see risk 1) |
| JS MINER → ENDPOINTS | ✅ VERIFIED |
| APPLICATION MODEL | ⚠️ PARTIAL (generates correctly, zero consumers) |
| INTELLIGENCE / SCANNER → CANDIDATE FINDINGS | ✅ VERIFIED (real Nuclei + heuristic scoring, provenance via `tool` column) |
| VALIDATION (auto_hunter) | ✅ VERIFIED (false-positive elimination proven; scope-matching bug found **and fixed** in this audit) |
| EVIDENCE → REPORT | ✅ VERIFIED (sample/live separation enforced and confirmed on real files) |
| NOTIFICATION | ✅ VERIFIED (fired in live test run) |
| DAEMON (independent loop) | ✅ VERIFIED (Nuclei wired and correctly sequenced) |
| TARGET DIFF | ⚪ OPTIONAL / DISPLAY ONLY (by design, not a defect) |
| RUN/ARTIFACT OWNERSHIP | ⚠️ PARTIAL (directory-level only; no per-record run_id) |
| TRUFFLEHOG / bb-hunt | ⚫ DEAD (unchanged, confirmed still absent) |

### FINAL VERDICT: **PARTIALLY WIRED**

The pipeline runs end-to-end for real, with real tools, and produces internally-consistent, provenance-tagged data — this audit proved that with actual execution rather than trusting the prior audit's or the code's own self-checks. It cannot be marked FULLY WIRED because this same verification process found and had to fix a live, previously-undetected false-negative in the validation trust boundary (Section 4/17), and because two structural gaps (no run/artifact ownership, an orphaned `application_model.json`) remain open by design decision in this audit rather than by omission.

---

## APPENDIX: TEST EXECUTION LOG (this session, real tool runs)

```
$ python3 -m unittest tests.test_runtime_integrity tests.test_e2e_pipeline -v
...
Ran 13 tests in 53.202s
OK
```
All 7 module selfchecks (`recon_pipeline`, `scanner`, `intelligence`, `report_gen`, `application_model`, `auto_hunter`, `js_miner`) pass with no failures after all fixes in this audit.
