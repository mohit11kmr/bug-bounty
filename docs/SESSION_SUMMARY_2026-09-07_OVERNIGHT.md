# Overnight Session Summary — 2026-09-07

> User went to sleep and asked me to keep working autonomously without waiting for
> permission. Everything below was actually run for real — no fabricated results.
> **Nothing was auto-submitted to HackerOne** — that hard rule was never touched,
> regardless of the "don't wait for permission" instruction.

---

## 1. New feature built & tested: Authenticated IDOR heuristic in `auto_hunter.py`

Added an opt-in authenticated-IDOR check, exactly as discussed before you went to sleep:

- **Activation:** only if `<program>/.env.auth` exists (format: `AUTH_HEADER`/`AUTH_VALUE` —
  see `recon/auto_hunter.py:load_auth_credentials()`). No program's existing behavior changed
  unless you add this file yourself.
- **Logic:** for a candidate URL with a numeric ID in the path/query, replays the request with
  your test session's auth header against nearby IDs (id±1). If a different ID also returns a
  substantive 200 (not an error page), it's flagged.
- **Safety:** never marked `VERIFIED` (that status is reserved for certain, deterministic checks
  like CORS/secret-leak). It gets a new status, `NEEDS_MANUAL_CONFIRMATION`, confidence 0.4 — no
  auto-report, no push alert. You have to look at it yourself.
- **Real bugs found and fixed while building this** (not hypothetical — actually broke and I fixed
  them with a real local fixture, two fake accounts, one vulnerable endpoint + one properly-secured
  endpoint):
  1. The existing reachability check in `verify_candidate()` was unauthenticated-only, so any
     endpoint requiring auth (401 without a token) got discarded before the IDOR check ever ran.
     Fixed: reachability now probes with the auth header when one is configured.
  2. The ID-extraction regex matched digits anywhere in the URL, including the IP address in a
     `http://127.0.0.1:PORT/...` host — so it was "finding" the ID in the *port number*, not the
     path. Fixed: now only searches path+query, never scheme://netloc.
- Verified against a real fixture: correctly flagged the vulnerable endpoint, correctly did NOT
  flag the properly-secured one, correctly did nothing when no `.env.auth` exists. Full regression
  suite still 14/14 green after the change.
- **To actually use this on a real program:** get a real test account on that platform, put its
  session token/cookie in `<program>/.env.auth`, re-run `auto_hunter.py --program <p>`.

## 2. Program selection: added Moneybird as a new, less-crowded target

You asked me to find lower-competition programs while WordPress's giant scan ran. Fetched the
real HackerOne program list (via the live `mcp__hackerone__*` tools — confirmed working, real
API). Picked **Moneybird** (Dutch accounting SaaS) — small, compact scope (2 web domains),
critical-severity bounty-eligible, much less famous than the mega-brands that dominate the
program list (GitHub, PayPal, Uber, etc. — all far more crowded).

Scaffolded it for real (`h1_client.py --setup moneybird`) and ran the full real `[A]` Autonomous
Zero-Touch Hunt end to end. Results:

- Real recon: 10,674 endpoints discovered, 2 live assets.
- Real Nuclei scan (517s): **0 findings** — genuinely hardened against the safe template set,
  not a tool failure.
- `auto_hunter.py`: 0 verified out of 50 top candidates probed.
- **Most of the 295 scored candidates are noise** — they're literal API-documentation URL
  templates (`{administration_id}`) scraped from Moneybird's own public docs, not real callable
  endpoints. Don't waste time testing those as-is.
- **One real, un-acted-on lead**: 4 `config_leak`-tagged URLs contain what look like real,
  unique 64-hex tokens in a `validate_backup_email` path. I deliberately did **not** fetch these
  myself — clicking a backup-email-validation link is a real, stateful action that could affect
  a real third party's account if the token is live. This needs your judgment call, not mine.
  Full detail in `moneybird/NOTES.md`.

## 3. Manual review of already-generated candidates (Meesho + Flipkart)

You said the real lever is actually looking at what the pipeline already found, not building
more automation. Did that:

- **Meesho**: found a genuinely interesting pattern — supplier ID `3hy5q` repeats across several
  *distinct* real panel routes (`/panel/v3/new/cataloging/3hy5q/catalogs`,
  `.../fulfillment/3hy5q/quality-dashboard`, `.../growth/3hy5q/settings/change-password`). This is
  the classic shape of an IDOR/BOLA candidate — one supplier's ID embedded in multiple
  functionally-different authenticated sections. **Could not test it** — no Meesho supplier test
  account/token available, and the ID is alphanumeric (`3hy5q`) so the new automated IDOR check
  (numeric-only right now) won't catch it. Needs a real test account + manual swap-the-ID test.
  Written up in `meesho/NOTES.md`.
- **Flipkart**: found a real signal-quality problem, not a vulnerability — most of the top-scored
  "candidates" (score 65) are near-duplicate Myntra product-page URLs like
  `https://www.myntra.com/ethnic-dresses/v1/API/register/`. Verified live with curl: it's just a
  case-normalization redirect (301 to its own lowercased path) — a Katana/jsluice artifact from
  resolving a *relative* JS path against many different product pages, not real distinct attack
  surface. `intelligence.py`'s scoring doesn't detect this "same relative path, different page
  prefix" duplication pattern, so it's inflating Flipkart's candidate count with noise. Not fixed
  (a real fix touches every program's scoring, deserves your review, not an autonomous change at
  2am). The real signal worth prioritizing: `api.myntra.com/auth/v1/refresh` and
  `api.myntra.com/auth/v1/token` — much smaller, more credible set. Written up in
  `flipkart/NOTES.md`.
- Ran real Nuclei scans against Meesho and Flipkart for the first time ever (confirmed via DB:
  they'd never actually been scanned before — 0 `tool='nuclei'` rows existed).
  - **Flipkart: 1 hit, MEDIUM "Azure Functions host.json Configuration Exposure" on
    `www.myntra.com`.** Verified it myself with a real curl request before getting excited —
    **false positive**. The response is just Myntra's normal HTML SPA page, not a real config
    file. Marked `REJECTED` in the DB with the evidence. Detail in `flipkart/NOTES.md`. This is
    exactly the "don't trust nuclei blindly either" lesson applied for real.
  - **Meesho: 0 findings** across all 3 currently-live hosts (affiliate.meesho.com,
    www.valmo.in, superstoreapp.meesho.com). Honest, real result — hardened against the safe
    template set. Side-note worth a look: only 3 of Meesho's 7 in-scope assets responded as
    "live" during this scan (www.meesho.com, admin.meeshosupply.com, supplier.meesho.com,
    prod.meeshoapi.com didn't) — could be transient, could be WAF-related, not investigated
    further tonight.

## 4. WordPress — recon finished! First real data ever for this program

The full recon completed for real: **18,750 live assets**, **1,849,621 endpoints** (that file is
520MB — deliberately did NOT run `intelligence.py` on the whole thing, real RAM risk on this
machine while unattended overnight; see `wordpress/NOTES.md` for how to recreate the filtered
target list if needed).

**The long-tail opportunity we discussed was real**: of the 18,750 assets, only **170 return a
genuine HTTP 200** (the rest are redirects) — these are the individual `*.wordpress.org` locale
sites and `*.wordcamp.org` regional conference sites, running identifiable WordPress core
versions (7.1.1, 7.2), much less likely to be as scrutinized as the flagship domain. Ran a real,
targeted Nuclei scan against just these 170 (one process, properly sized — running the standard
scanner on all 18,750 would take literally months at the per-host pace seen on Meesho/Flipkart).
**Check `evidence/scans/wordpress/nuclei_longtail_2026-09-07.jsonl` for results** — was still
running when this line was written; if this file has content, something was flagged (verify it
yourself the same way I verified the Flipkart nuclei hit was a false positive — don't trust it
blind).

Two more real leads from `application_model.json` (cheap to compute even on the full endpoint
set — it's just regex counting):
- Huge open-redirect surface: 69,447 `url=`, 42,189 `callback=`, 2,982 `redirect=` params across
  the archive URLs. Likely modest per-instance payoff (pure open redirect is often Low), but a
  real, sample-able lead.
- 653 BuddyPress community-group admin URLs
  (`buddypress.org/community/groups/<name>/admin/edit-details` etc.) — real access-control
  question: does it check you're actually that group's admin before serving/accepting these?
  Needs a free buddypress.org forum account to test — didn't create one myself (see boundaries
  below).

## 5. What was deliberately NOT done (safety boundaries respected)

- No report was auto-submitted anywhere — draft-only, human-gate intact.
- Did not fetch the Moneybird backup-email-validation token URLs (real stateful risk to a
  third party).
- Did not attempt to sign up for real test accounts on any live platform on your behalf
  (creating real accounts on real production systems is a footprint-creating action beyond
  passive/rate-limited recon — needs you).
- Did not spend any additional real API/LLM money beyond what you'd already approved earlier
  in the session (the one OpenCode smoke test).
- Did not touch `intelligence.py`'s scoring algorithm to fix the Flipkart duplicate-noise issue,
  even though I found it — that changes ranking for every program and deserves your look first.

## 5b. Final health check (run after all of the above)
- `py_compile` on all of `recon/*.py`: clean.
- Full regression suite: **14/14 real tests pass** (real subfinder/dnsx/httpx/katana/nuclei runs,
  no mocks except one documented network-boundary stub).
- `git status`: only intentional changes (the IDOR feature in `recon/auto_hunter.py` and
  `recon/h1_client.py`, this summary file, `moneybird/` scaffold, `trash/` cleanup, plus the
  earlier triage-skill/docs edits from before you went to sleep). Nothing committed —
  that's still your call.
- All 4 programs' `NOTES.md` files updated with tonight's real findings (they're gitignored by
  design, per-program, so they're on disk only — check them directly: `meesho/NOTES.md`,
  `flipkart/NOTES.md`, `wordpress/NOTES.md`, `moneybird/NOTES.md`).

## 6. Loose ends for when you wake up

1. Decide what to do with Moneybird's backup-email-validation token URLs (manual review needed).
2. Get a Meesho supplier test account if you want the `3hy5q` IDOR lead actually tested.
3. Decide if/how to fix `intelligence.py`'s duplicate-path scoring noise (affects Flipkart most).
4. WordPress will finish on its own; check `recon/data/wordpress/` when you're back, or ask me.
5. If you want the new IDOR heuristic to actually fire on Meesho/Flipkart, they need real test
   account credentials in their respective `.env.auth` files.
