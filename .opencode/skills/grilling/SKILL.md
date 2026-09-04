---
name: grilling
description: Interview the user relentlessly about a finding, report draft, hunt plan, or decision at stake. Use when the user wants to stress-test a finding before writing a HackerOne report, validate severity/impact/scope, or uses any 'grill' trigger phrases.
---

# Grilling — Finding & Plan Interrogation

Interview the user relentlessly until you reach a shared understanding. Map this as a **decision tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask *now* without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, multiple paragraphs OK, include multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a *later* round, not this one.

Finding *facts* is your job, never the user's. When a frontier question needs a fact from the environment (reproducing a PoC with `curl`, checking H1 program scope via the hackerone MCP, querying hacktivity for duplicates, reading logs/network requests), do it yourself — dispatch a sub-agent or run the tool. Don't ask the user for anything you could look up yourself. The *decisions* are the user's: put each to them and wait.

**Bug-bounty checklist to grill on (typical rounds, adapt to the tree):**

1. **Scope** — Is the target/program in scope? Is this endpoint/asset listed? (Check `SCOPE.md` / AGENTS.md / program scope via H1 MCP — don't ask the user for what the API says.)
2. **Class & root cause** — What vulnerability class is this? Where is the root cause in the request/response flow?
3. **Impact** — Who/what is harmed, at what severity (CVSS-ish)? What is the realistic business impact — is it reportable or informational?
4. **Reproducibility** — Minimal steps: exact request, exact payload, exact response. Can a fresh agent reproduce from the draft?
5. **Evidence quality** — Do we have screenshots/HAR/curl output captured? Where are the artifacts (never `/tmp` — evidence dir)?
6. **Duplicates & prior art** — Any prior report on this program (hacktivity), or a known vuln in this stack?
7. **Report shape** — Title, severity, affected endpoint, steps-to-reproduce, impact, remediation. Is this submission-ready or does it need more work first?

The session is done when the frontier is empty: every branch of the decision tree visited, nothing left silently assumed. Do not write/submit a report until the user confirms you have reached a shared understanding. **Never submit to H1 automatically — human gate on every report.**