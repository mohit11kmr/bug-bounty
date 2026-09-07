# MISSION: Autonomous Bug Bounty Hunting — Target: Meesho BBP (meesho_bbp)

You are operating in the dedicated authorized HackerOne workspace for program `meesho_bbp`.
Your objective is to find valid, high-impact security vulnerabilities and prepare actionable non-destructive Proof-of-Concepts (PoCs).

## 1. SCOPE & LEGAL BOUNDARIES (Hard Rules)
- IN-SCOPE TARGETS:
  - www.meesho.com
  - admin.meeshosupply.com
  - supplier.meesho.com
  - affiliate.meesho.com
  - prod.meeshoapi.com
  - www.valmo.in
  - superstoreapp.meesho.com

- EXCLUDED / OUT-OF-SCOPE (Strictly forbidden — Do NOT touch):
  - grocery-supplier.meesho.com
  - farmiso.meeshosupply.com
  - affiliate-c.meesho.com
  - warehouse.meesho.com
  - agency.meesho.com
  - atlas.valmo.in
  - admin.meesho.io
  - *.meeshogcp.in
  - *.meeshoaiservices.ai
  - *.meeshosupply.com
  - *.meeshoapi.com
  - Rider app
  - com.valmo.ops

- SAFE OPERATING LIMITS:
  - Max rate limit: 60 requests/min | Concurrency: 5
  - Destructive actions: STRICTLY PROHIBITED
  - sqlmap: non-destructive only (`--batch --risk 1`)
  - No DoS, no credential brute forcing, no customer data corruption.

## 2. HIGH-PRIORITY ATTACK SURFACE & RECON CANDIDATES
- [ 83] **api_surface** `https://supplier.meesho.com/panel/v3/new/root/login?redirect=%2Fpanel%2Fv3%2Fnew%2Ffulfillment%2F3hy5q%2Fquality-dashboard`
- [ 58] **auth** `https://admin.meeshosupply.com/api/google/oauth?redirect=%2F`
- [ 58] **auth** `https://admin.meeshosupply.com/login?redirect=%2F`
- [ 53] **api_surface** `https://supplier.meesho.com/panel/v2/new/login`
- [ 53] **api_surface** `https://supplier.meesho.com/panel/v2/new/login?distinct_id=17d7534a8cd295-0b6d89ab8aa525-1f241205-186a00-17d7534a8ce31a`
- [ 53] **api_surface** `https://supplier.meesho.com/panel/v3/new/cataloging/3hy5q/catalogs`

## 2.5 APPLICATION UNDERSTANDING (deterministic actor/object/action map)
An application model exists: `recon/data/meesho/application_model.json` (actors/objects/actions/auth-surfaces extracted from recon endpoints). Consider invoking `@prob-hunter` with candidate_report.md + this file for deeper Bayesian ranking and BOLA/IDOR ownership hypotheses before manual testing.

## 2.6 ALREADY VERIFIED BY THE AUTONOMOUS PIPELINE (auto_hunter.py)
The Python `[A]`/daemon path may have already run on this target and verified findings
independently of this session. Check these first — don't silently miss or re-discover them:
  - [cors_misconfig] https://test.meesho.com/x — TEST ROW - Verified CORS reflection

## 3. YOUR EXECUTION PROTOCOL
1. **Analyze Candidates**: Examine prioritized endpoints above (auth flows, admin panels, sensitive APIs), and review section 2.6 for anything already verified.
2. **Formulate Hypotheses**:
   - Access Control: Test for IDOR / BOLA on IDs, user_ids, invoice parameters.
   - Authentication Flaws: Test token validation, OAuth redirect params, SSO callback flaws.
   - Information Disclosure: Test API endpoints for secret leakage or internal cloud bucket exposures.
   - SSRF / Open Redirect: Test URL parameters handling redirections.
3. **Execute Non-Destructive Verification**:
   - Use `curl -s -i` or Burp Suite to reproduce.
   - Record exact HTTP request & response headers.
4. **Prepare Report Artifact**:
   - Save PoC evidence to `evidence/reports/meesho/`.
   - Match with HackerOne scope_id from `scope.yaml` for triage submission.

Proceed with systematic hunting now. Focus on quality, business impact, and rigorous verification!