# HUNTING_GUIDE.md — Beginner → Pro Bug Bounty Path

Is workspace ka structured hunting guide. Har stage ka purpose + expected output.

## Phase 0 — Setup (done)
- [x] opencode dedicated workspace (default agent: hackerone-analyst)
- [x] bug-bounty + research skills registered
- [x] hackerone MCP (report submit, scope, hacktivity)
- [x] Tools: subfinder, httpx, nuclei, ffuf, gobuster, sqlmap, nikto, jadx, burpsuite, dalfox, wpscan

## Phase 1 — Learn (practice no risk)
1. OWASP Juice Shop / DVWA par recon + XSS/SQLi practice.
2. `dalfox` se XSS confirm, `sqlmap --batch` se SQLi.
3. Finding likhna seekho: root cause, PoC, impact, remediation.

## Phase 2 — First real hunt (public program)
1. `hackerone_get_program` → scope + exclusions padho.
2. `hackerone_get_program_scope` → assets list karo.
3. recon: `bb-hunt <domain>` ya manual chain.
4. Triage: in-scope? duplicate? impactful?
5. Report submit with scope_id + weakness_id.

## Phase 3 — Confirm & report checklist
- [ ] Test SIRF in-scope host
- [ ] PoC reproducible (curl/browser evidence)
- [ ] Hacktivity mein duplicate nahi
- [ ] Impact clearly stated (what attacker gets)
- [ ] Correct CWE + severity

## Phase 4 — Level up
- Write up your finds in `LESSONS.md`
- Re-read disclosed reports for patterns
- Expand scope (ESP: Extra Scope Program)

## Tools cheat-sheet
```bash
bb-hunt <domain>              # fast full recon
subfinder -d <domain> -all    # subdomains
httpx -l subs.txt -td -o alive.txt
dalfox pipe < urls.txt        # XSS confirm
wpscan --url <wp> --enumerate # wordpress
sqlmap -u <url> --batch --risk 1
```
