# Bug Bounty — IF/ELSE DECISION TREE (single routing source)

> Har decision yahan se. Read top-to-bottom, pehla match jo apply ho wahi use karo.
> Tool-level micro-routing ka reference: `~/.config/opencode/skills/bug-bounty/TOOLS.md`.
> Workflow stages: WORKFLOW.md. Ye file = quick if/else router.

---

## 0. SESSION START — kya karna hai?

```text
IF  user new target scan chahta hai        → launcher [1] Start NEW scan
ELIF user existing target continue karta   → launcher [2] Continue EXISTING target
ELIF user kisi specific target par report  → hackerone-analyst (default)
ELIF user probability ranking chahta hai   → @prob-hunter analyze <artifacts>
ELIF user code fix/refactor chahta hai     → developer
ELIF user test/verify chahta hai           → qa
```

---

## 1. NEW TARGET — launcher [1]

```text
IF  target folder already exists (scope.yaml wala)  → skip create, warn + continue session
ELIF candidate handle fuzzy-matches existing folder  → skip (duplicate guard), same folder open
ELIF target naya hai                                → folder + scope.yaml/SCOPE.md/NOTES.md banake session
```

---

## 2. SCOPE

```text
IF  root me hai (SCOPE.md / hackerone_get_program_scope)   → in-scope, test allowed
ELIF excluded me hai                                       → NEVER touch (strict)
ELIF uncertain                                             → verify via scope API pehle
```

---

## 3. RECON — kaunsa chain? (bb-hunt if/elif)

```text
IF  full pipeline data chahiye (scanner+intelligence+DB ke liye)
      → python3 recon/recon_pipeline.py --program <p>      # Chain A — PRIMARY
ELIF sirf ek-baar quick sanity check chahiye (40 sec, koi DB nahi, /tmp output)
      → bb-hunt <domain> --probe                           # Chain B — quick look only
ELIF bb-hunt se full sfr pesseski CVE scan chahiye
      → bb-hunt <domain>                                    # full mode (fuzz+nuclei)
ELSE seedhi manual (JS/API already patched)                 → skip recon, manual
```

> **bb-hunt is NOT a replacement for the pipeline.** Difference:
> bb-hunt output `/tmp/opencode/hunt/` me jaata hai — `scanner.py`/`intelligence.py`
> use kabhi NAHI padhte. Pipeline output `recon/data/<p>/` me jaata hai — DB me bhi.
> Rule: `scanner.py`/`intelligence.py` se pehle HAMESHA pipeline chalao (Chain A).
> bb-hunt sirf "target ka live ya dead, kitne subs hai" minute-ka jawab dene ke liye.

---

## 3b. PROB-HUNTER — kab call karein? (probability ranking)

```text
IF  candidate_report.md already exists (intelligence.py chala hai)
      → @prob-hunter <shortlist file>  # top-40 deterministic score se hi LLM de-skope kare
ELIF sirf raw recon files hain (pipeline abhi nahi chala)
      → pehle pipeline chalao (3), phir intelligence.py, phir prob-hunter
ELIF sirf 1-2 suspicious endpoints hain, full queue nahi chahiye
      → seedhe manually test, prob-hunter skip (expensive, overkill)
```

> WHY SHORTLIST: prob-hunter LLM-based hai (credits). Full gau.txt se score karwana
> hundreds of lines me token burn karega bina signal. intelligence.py deterministic
> (free) pehle top-40 shortlist banata hai; prob-hunter usi par prior+evidence lagata
> hai → wo exact 3-5 manual tests pick karta hai. Deterministic = breadth, prob-hunter = depth.

---

## 4. SUBDOMAIN/AUTH — TOOLS.md A

```text
IF  subdomains unknown     → subfinder -d <dom> -silent | sort -u > subs.txt
THEN httpx -l subs.txt -silent -status-code -title -tech-detect -o alive.txt
ELIF live hosts known      → sirf httpx probe
```

---

## 5. ENDPOINT/BRUTEFORCE — TOOLS.md B

```text
IF  JSON API clean verbs (200/404)         → ffuf (-mc 200,201,301,401,403,405,500)
ELIF directory structure only              → gobuster dir
ELIF subdomain brute                       → gobuster dns
ELIF SPA (client-rendered)                 → JS-bundle enumeration (route F) prefer over bruteforce
ELSE move manual
```

---

## 6. VULN-SCAN — TOOLS.md D / D1 / D1b

```text
IF  known-CVE check        → nuclei -t http/ -severity critical,high,medium
ELIF WordPress             → wpscan --enumerate  (docker wrapper)
ELIF ports/services/ver    → nmap -sV --top-ports 100  (in-scope only, no -T5)
ELIF flags needed on svc   → nmap --script vuln   (# non-destructive)
ELIF full DAST coverage    → ZAP baseline docker (in-scope URL)   # slow, symmetric use
ELSE lightweight targeted (dalfox/sqlmap) per finding
```

> ZAP baseline ACTIVE hai — sirf in-scope, non-destructive. WAF-hosted skip.
> Scanner.py pehle hamesha `--dry-run` (config check), phir asli.

---

## 7. SQLLI — TOOLS.md C

```text
IF  GET param suspected    → manual payloads → sqlmap -u <url> --dbs --batch --level 1 --risk 1
ELIF POST suspected        → sqlmap --data '...' -p key --batch --level 2 --risk 1
ELIF only confirm need     → manual ' OR '1'='1 / " OR 1=1-- / 1 AND SLEEP(5) → sqlmap if chance
ELSE move on

# ALWAYS --batch --risk 1. NEVER --drop/--flush/destructive.
```

---

## 8. XSS — TOOLS.md D2

```text
IF  URL list/params to test       → cat urls.txt | dalfox pipe --silence -o xss.txt
ELIF single URL+param            → dalfox url 'url' --silence -o xss.txt
ELIF blind XSS                   → dalfox url '…' --blind <xsshunter-url> -o xss.txt
ELSE manual reflect check
```

---

## 9. APK/JSR — TOOLS.md E/F

```text
IF  APK present            → jadx -d /tmp/out <apk> ; grep -rEi "api\.|/api/|graphql|secret|https?://"
ELIF APK pehle download    → apkeep/apkpure/apkmirror → jadx
ELIF SPA page open         → chrome-devtools evaluate_script → regex "/api/..."
ELIF need JS w/o browser   → curl main JS → grep local
```

---

## 10. AUTH/LOGIN/BROWSER — TOOLS.md G

```text
IF  need login/OTP/session/IDOR  → chrome-devtools (fill/click/snapshot/fetch)
ELIF file upload/drag/complex    → playwright MCP
ELSE browser quick-test          → chrome-devtools
```

---

## 11. BOT-WALL — TOOLS.md H

```text
IF  403 Akamai (curl)         → curl_cffi impersonate="chrome120" + mobile UA; slow fuzz (3-5 conn, ~500ms)
ELIF 403 Cloudflare           → chrome-devtools/playwright (browser) not raw HTTP
ELSE normal fuzz
```

---

## 12. FAILURE HANDLING

```text
IF  docker daemon not running     → sudo systemctl start docker → retry
IF  curl/nuclei/ffuf reset 000/403 → SKIP host (WAF/geo). Next. NO hammering.
IF  ffuf/gobuster 0 results       → SPA thinking: JS-bundle enumeration + manual. Not "no routes".
IF  sqlmap connection issue       → manual payloads only; report if clean repro
IF  nuclei timeout/none           → -rate-limit 5, fewer templates
IF  jadx corrupt APK              → re-download; verify `file` says Zip/DEX
IF  tool produces finding         → VERIFY manually (curl/browser) before counts as finding
```

---

## 13. PRIORITIZE + REPORT

```text
IF  prob-hunter score 75%+      → CRITICAL-HUNT, manual pehle
ELIF 50-74%                    → HIGH
ELIF 25-49%                    → MEDIUM
ELIF 10-24%                    → LOW
ELSE 0-9%                      → SKIP

IF  new finding confirmed       → Skill `triage`   (state machine: valid/dup/wontfix/ready)
ELIF ready-for-report           → Skill `grill-me` → `grilling` (mandatory interrogation)
ELIF high/critical reviewer     → task `claude-reviewer` (independent cross-check)
ELIF user confirms submission   → hackerone_submit_report (NEVER auto-submit)
ELIF session switch/end/pause   → Skill `handoff`  → evidence/handoffs/ (KABHI /tmp)
ELSE out-of-scope/dup/no-impact → recycle (record + wontfix), never report
```

---

## TOOL AVAILABILITY (sab installed — audit Sep 2026)

`subfinder httpx nuclei ffuf gobuster sqlmap nikto jadx burpsuite dalfox wpscan nmap dnsx naabu waybackurls assetfinder katana gau` — SAB OK.

Docker images: `zaproxy:stable`, `wpscanteam/wpscan:latest` present.
Agents: hackerone-analyst (all), prob-hunter (subagent), claude-reviewer (all) + route agents.
MCP: hackerone configured. Chain A (pipeline) live (recon.db 123 findings). bb-hunt chain currently UNUSED (no hunt dir output).