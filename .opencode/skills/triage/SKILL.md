---
name: triage
description: Move candidate findings through a triage state machine — discovered, needs-info, ready-for-report, submitted, wontfix — verifying, deduplicating, and grilling each finding before it becomes a report. Use when a new finding lands, a report draft needs review, or the user says 'triage this finding'.
---

# Triage — Finding State Machine

Move candidate findings through a small state machine before any report is written. This keeps draft-forever findings from accumulating and never being submitted.

## States

One **category** role per finding:

- `valid`: real, in-scope, reportable
- `invalid`: false positive, out-of-scope, informational-only
- `duplicate`: already reported (own history or hacktivity)

State roles (one at a time):

- `discovered`: raw candidate, not yet evaluated
- `needs-info`: waiting on the user for more info or evidence
- `ready-for-report`: fully specified, submission-quality brief exists
- `submitted`: human confirmed submission
- `wontfix`: invalid, duplicate, out-of-scope, or non-qualifying

Every triaged finding carries exactly one category role and one state role. If in doubt, flag it and ask the user before acting.

## Triage flow

1. **Gather context.** Read the finding, its evidence artifacts, the program scope (SCOPE.md/AGENTS.md, H1 program scope via MCP). Parse any prior triage notes. **Also check `recon/data/<program>/recon.db`'s `candidate_findings` table for rows already `status='VERIFIED'`** — the Python autonomous pipeline (`recon/auto_hunter.py`, run via `[A]`/daemon) uses its own separate state machine (`TRIAGED → VALIDATING → VERIFIED | REJECTED`) and may have already independently confirmed a finding before this session started. Treat a pre-existing `VERIFIED` row as your `discovered` starting point already carrying a confirmed reproduction (CORS reflection, secret leak, etc. — read its `notes` column for the evidence) — don't silently miss it or re-run the same probe from scratch. Query: `sqlite3 recon/data/<program>/recon.db "SELECT url,tag,score,notes FROM candidate_findings WHERE status='VERIFIED'"`.
2. **Verify the claim.** Reproduce the issue from the recorded steps before believing it. Run the exact request/payload against the target (authorized scope only). Report what happened: confirmed (with request→response path), failed, or insufficient detail (a strong `needs-info` signal). NEVER tag a finding `valid` without a confirmed reproduction.
3. **Check redundancy.** Search own prior findings/history and H1 hacktivity for the same issue on the same asset. If a duplicate, mark `duplicate` + `wontfix` and reference the prior report.
4. **Check scope.** Does the affected asset match the program's in-scope list exactly? If not → `wontfix` (out-of-scope). Do not submit out-of-scope findings.
5. **Grill if needed.** If the finding needs fleshing out (weak impact, unclear severity, missing evidence), call the Skill tool for **grilling** and interrogate into shape.
6. **Apply the outcome:**
   - `ready-for-report`: write a submission-quality brief (title, severity, affected endpoint, steps to reproduce, impact, remediation) and save it with the finding's evidence.
   - `needs-info`: list exactly what the user must provide (that's the blocker).
   - `wontfix`: record why — invalid, duplicate, out-of-scope, non-qualifying — so it doesn't resurface.

## Hard rules

- **Human gate on submission.** Never submit to HackerOne automatically. `submitted` state is only set after the user confirms they submitted (or you showed them exactly what to paste and they said go).
- **Every submitted report needs the standard disclaimer** that AI-assisted findings must be reviewed per program rules — don't claim human-only work.
- Any AI-generated comment/report text posted anywhere must start with a note that it was AI-assisted during triage.
- If the user says "triage everything," work through open `discovered`/`needs-info` findings oldest-first, presenting one at a time with your recommendation and waiting for direction.