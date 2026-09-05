# Bug Bounty Workspace — README & Progress Log

> Ek jagah: ye workspace kya hai, kaise use karna hai (rules), aur **hum kya kar rahe**
> (live progress log — jaisi file update hoti hai, yahan entry aati hai).
> Mission: **har angle se bounty find karna, HackerOne rules ke andar.**

---

## What / Why

Dedicated **authorized bug bounty hunting** workspace (`hackerone-analyst` default agent).
Recon → probability ranking → safe scan → candidate queue → manual test → triage → grill →
second opinion → report. SIRF in-scope. Koi out-of-scope/unauthorized testing nahi.

## Usage rules (HackerOne compliance — hamesha)

1. **Scope first:** har hunt me program/SCOPE.md + `hackerone_get_program_scope(_exclusions)`
   verify — `roots` in, `excluded` OUT. Kabhi target nahi touch before scope confirm.
2. **Test types:** sipf non-destructive, in-scope. `sqlmap --batch --risk 1` hamesha.
   `--drop/--flush/destructive` kisi bhi tool me nahi.
3. **No auto-submit:** HackerOne report SIRF user ke explicit confirmation se
   (`triage` skill human-gate). AI-assisted text me disclaimer hamesha.
4. **Evidence first:** har finding = reproducible PoC (curl/browser), evidence path
   `evidence/` me (kabhi /tmp nahi — files get wiped). Screenshots/HAR + paths.
5. **Duplicate check:** submit se pehle hacktivity + own history check (`triage`).
6. **No fabrication:** jo run nahi hua wo "NOT RUN — reason" likho. PoC/impact invent mat karo.
7. **Keep hands off:** DoS, network-tampering, credential-stuffing, brute out-of-scope —
   HackerOne ke disallowed hain.
8. **Rules/scope evolve:** program policy dobara padho jab bhi naya session.

## System map (kaun sa file kya karta hai)

| File/Path | Role |
|-----------|------|
| `start-bugbounty.sh` | Launcher (new-scan / continue-existing) |
| `opencode.json` | Config: default agent + skills + hackerone MCP (global) |
| `AGENTS.md` / `HUNTING_GUIDE.md` | Structure rules + learning path |
| `WORKFLOW.md` | Operational flow (entry → report) |
| `IF_ELSE.md` | if/else decision tree (tool/skill routing, single source) |
| `recon/recon_pipeline.py` | Recon → `recon/data/<p>/` assets/endpoints JSON |
| `recon/scanner.py` | Safe scope-aware nuclei/ffuf → recon.db |
| `recon/intelligence.py` | Deterministic candidate scoring → candidate_report.md (free breadth) |
| `prompts/prob_hunter_prompt.txt` | prob-hunter Bayesian depth-rank prompt (source of truth — registered agent `~/.config/opencode/agents/prob-hunter.md` reads this via `@prob-hunter`) |
| `.opencode/skills/{triage,grilling,grill-me,handoff}` | Finding state-machine, interrogation, session handoff |
| `<program>/scope.yaml` + SCOPE.md + NOTES.md | Per-target scope + progress |
| `evidence/` | Handoffs, screenshots, scan outputs |
| `reports/` | drafts + templates |
| `~/.config/opencode/skills/bug-bounty/TOOLS.md` | Tool-level if/else routing (18 tools + docker + MCP) |

## License / Authorization

- **Hunting SIRF authorized programs par** — jo scope API/program me hon. Practice target `general/`
  (Juice Shop/DVWA/local) sirf local lab hai.
- Is repo me koi proprietary secrets nahi rakhte. Credentials env vars se (`H1_USERNAME`,`H1_API_TOKEN`).
- Reusable tool/config — free to adapt. Bounty/scope kahin hardcode nahi.

---

## PROGRESS LOG (logs in — bade changes aate hi update karo)

| Date | Change | File(s) |
|------|--------|---------|
| 2026-09-05 | Workspace align: prob-hunter depth-rank only on candidate shortlist (not raw gau); deterministic breadth = intelligence.py; bb-hunt routed as quick-sanity (if/else §3) | WORKFLOW.md, IF_ELSE.md, prompts/prob_hunter_prompt.txt, AGENTS.md |
| 2026-09-05 | prob-hunter model → `opencode/big-pickle` (OpenRouter credits blocker removed) | opencode.json |
| 2026-09-05 | 4 skills (triage, grilling, grill-me, handoff) wired into workflow: finding → triage → grilling → claude-reviewer → submit; session-end → handoff → `evidence/handoffs/` | WORKFLOW.md §8-13, IF_ELSE.md §13 |
| 2026-09-05 | Global audit: 18 tools OK, docker ZAP+wpscan present, bb-hunt symlink OK | (audit record) |

> Naye change → yaah ek row add karo (date + kya + files). Is file ko bhi update karte raho.