---
name: handoff
description: Compact the current hunting session into a handoff document so a fresh agent can continue the work without losing context or evidence. Use when switching agents, ending a session, or pausing a hunt — especially before closing a terminal so findings survive.
---

# Handoff — Session-to-Agent Continuity

Write a handoff document summarising the current hunting session so a fresh agent can continue the work. **Save it to the workspace evidence directory — `evidence/handoffs/` — NOT to `/tmp`** (temporary files get wiped; this is how past findings were lost).

## Content

- **Target & scope**: program, target host(s), in-scope URL, check the SCOPE.md/AGENTS.md reference
- **Session summary**: what was done, what was found, what is in progress
- **Evidence pointers**: reference artifacts by path — screenshots, HAR captures, curl outputs, scan results (never embed their full content; reference by path)
- **Findings status**: for each candidate finding — state, confidence, evidence links, next action
- **Suggested skills section**: name which skills the next agent should call the Skill tool for (e.g. `grilling` for a finding, `bug-bounty` for recon)
- **Next steps**: explicit, ordered

## Rules

- Do not duplicate content already captured in other artifacts (reports, SCOPE.md, evidence files). Reference them by path instead.
- **Redact sensitive information** — API keys, tokens, session cookies, PII. Never write credentials into the handoff.
- If the user passed an argument, treat it as a description of what the next session will focus on and tailor the doc accordingly.
- After writing, report the file path so the user can verify.