# Bug Bounty Workspace — AGENTS.md

Ye ek **dedicated bug-bounty workspace** hai. Yahin se authorized HackerOne hunting, recon, vulnerability research, aur report submission hota hai.

## Primary directive
1. **Default agent:** `hackerone-analyst` (isko pehle use karo).
2. **Skill:** `bug-bounty` skill load karo (recon/hunting rules — SKILL.md + TOOLS.md routing).
3. **Legal first:** HAR finding report karne se pehle program scope + exclusions verify karo. SIRF in-scope assets.
4. **No fabrication:** PoC/impact fabricate mat karo. Jo run nahi hua wo "NOT RUN — reason" bol do.

## Multi-program management (samjho — isse confusion na ho)
Har program ka apna folder hai (`meesho/`, `general/`, ...). Folder name = kaun sa program ACTIVE hai.

- **Current program folder decide karo** is se: (a) user ne kaunsa program bola, ya (b) user kaam kis folder mein kar raha hai. Kisi program ke SCOPE/NOTES usi ke folder mein padho.
- **Kabhi program folders cross-mix mat karo** — meesho ke scope meesho ke folder mein, dusre program ka data apne folder mein.
- **Session shuru par confirm:** "ab <folder/program> ke liye hunting hai — scope/<foldername>/SCOPE.md + NOTES.md read karo, sirf uske in-scope targets."
- `general/` = sirf practice/dummy targets (Juice Shop, DVWA, local lab). Real program ka data wahan mat daalo.

## Workflow (har hunt mein)
1. Program select / confirm — current program ka folder (SCOPE.md) padho, not assume.
2. Scope + exclusions read karo (folder SCOPE.md + hackerone_get_program_scope_exclusions).
3. Weaknesses (CWE) check karo.
4. Recon: subfinder → httpx → nuclei → manual (Burp/DevTools).
5. Triage: in-scope + no duplicate (hacktivity) + material impact.
6. Report: `hackerone_*` MCP se submit (weakness_id + scope_id).
7. **Second opinion (optional):** high/critical finding submit se pehle `claude-reviewer` subagent se Claude Code ki independent cross-check le sakte ho (task tool se). Ye read-only hai — finding ko edit nahi karta.
8. Update `LESSONS.md` (bug-bounty skill) — jo worked/failed.

## Environment
- HackerOne credentials: `H1_USERNAME` + `H1_API_TOKEN` env vars se.
- Tools: subfinder, httpx, nuclei, ffuf, gobuster, sqlmap, nikto, jadx, burpsuite, dalfox, wpscan (docker).
- Practice targets: OWASP Juice Shop, DVWA (local, authorized).

## Rules
- SIRF authorized targets. Koi out-of-scope testing nahi.
- sqlmap hamesha `--batch --risk 1` (non-destructive).
- WAF-blocked hosts par slow (3-5 concurrent, ~500ms delay).
- Quality > volume. Ek solid finding > 100 duplicates.

## Protected files — kisi bhi AI coding agent ke liye
- `recon/auto_hunter.py` aur `recon/intelligence.py` **generated shims hain,
  asli source nahi** — inko edit karna koi effect nahi karega (compiled
  `.so` se import ho ke overridden ho jaata hai). Agar koi user inme kuch
  change karne ko bole (scoring, verification-logic, koi bhi behavior), **use
  batao ki asli file `proprietary/_auto_hunter_core.py` /
  `proprietary/_intelligence_core.py` hai** — wahi edit karo, phir
  `build_proprietary.sh` chalao. Har file ke top-comment mein bhi yahi likha
  hai — wo `.so` compilation ka context deta hai, ye yahan sirf repo-wide
  discoverability ke liye reference hai.
- Ye ek **routing-request hai, security-boundary nahi** — agar user explicitly
  isi file ko edit karne par zid kare, use clearly batao ki koi effect nahi
  hoga, blind-obey mat karo.
