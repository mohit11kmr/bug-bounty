# 🔒 Security Testing Tools Guide (Free & Open Source)

> **Purpose:** Web application vulnerability scanning aur Bug Bounty (HackerOne) hunting ke liye free tools ka detailed reference.
> **Audience:** Developers, Security Testers, Bug Bounty Hunters
> **Scope:** XSS, SQL injection, CSRF, IDOR, SSRF, broken auth, session handling, exposed secrets, security misconfigurations

---

## 📑 Table of Contents

1. [Important Legal Note](#important-legal-note)
2. [Tool Comparison Table](#tool-comparison-table)
3. [OWASP ZAP](#1-owasp-zap)
4. [Nuclei](#2-nuclei)
5. [subfinder](#3-subfinder)
6. [httpx](#4-httpx)
7. [Nmap](#5-nmap)
8. [Wapiti](#6-wapiti)
9. [Burp Suite Community](#7-burp-suite-community)
10. [Online / No-Install Platforms](#8-online--no-install-platforms)
11. [AI-Powered Tools](#9-ai-powered-tools)
12. [Recommended Workflow](#10-recommended-workflow)
13. [Bug Bounty Hunting Checklist](#11-bug-bounty-hunting-checklist)

---

## ⚠️ Important Legal Note

> **Ye tools sirf AUTHORIZED targets par use karo.**
> - Aapke apne projects (jaise LeadGuard OS V6) — ✅ allowed
> - HackerOne / Bugcrowd ke **in-scope** assets — ✅ allowed
> - Bina permission ke kisi site par active scanning — ❌ **illegal**

**HackerOne ke liye:** Sari testing sirf un programs ke in-scope assets par karo jo HackerOne ke safe-harbor policy ke under hain. Out-of-scope testing = ban + legal issues.

---

## 📊 Tool Comparison Table

| Tool | Type | Sab kya karta hai | GUI? | Free? | Best For |
|------|------|-------------------|------|-------|----------|
| **OWASP ZAP** | Full DAST scanner | XSS, SQLi, CSRF, headers, session, IDOR | ✅ GUI + CLI | ✅ 100% | Full web app scan |
| **Nuclei** | Template-based scanner | 9000+ templates, CVEs, misconfigs | ❌ CLI | ✅ | Fast automated vuln scan |
| **subfinder** | Subdomain enum | Subdomains discover | ❌ CLI | ✅ | Recon |
| **httpx** | Host discovery | Live hosts, status codes | ❌ CLI | ✅ | Recon |
| **Nmap** | Network scanner | Ports, services, vulns | ✅ GUI + CLI | ✅ | Network/infra scan |
| **dalfox** | XSS-focused scanner | Reflected/stored/DOM XSS, param sweep | ❌ CLI | ✅ | XSS confirmation |
| **wpscan** | WordPress scanner | Plugin/theme/user vulns, enforcement | ❌ CLI (docker) | ✅ | WordPress targets |
| **Wapiti** | Black-box scanner | SQLi, XSS, XXE, SSRF, command injection | ❌ CLI | ✅ | Lightweight active scan |
| **Burp Suite CE** | Proxy/interceptor | Manual testing, IDOR, auth, SSRF | ✅ GUI | ✅ (limited) | Manual deep dive |
| **SecScanner** | Online scanner | TLS, headers, DNS, cookies, CORS (62 checks) | ✅ Web | ✅ | Quick external check |
| **VulnerAI** | Online AI scanner | XSS, SQLi, headers, auth issues | ✅ Web | ✅ | Quick online scan |
| **CheckVibe** | Online scanner | 100+ checks, exposed keys, SQLi, XSS | ✅ Web | ✅ | Quick online scan |

---

## 1. OWASP ZAP

### Overview
**Sabse complete FREE web app security scanner.** OWASP Foundation maintain karta hai. Decade+ battle-tested. Passive + active scanning, GUI, automation.

### Kya find karta hai
- SQL Injection (Advanced add-on available)
- Cross-Site Scripting (XSS) — reflected, stored, DOM
- CSRF / Anti-CSRF token handling
- Insecure HTTP headers, cookies (HttpOnly, Secure, SameSite)
- Broken access control / IDOR (manual)
- SSRF (manual + some automation)
- Command injection, path traversal, XXE
- Authentication issues

### Installation

**Windows:**
```bash
# Download installer (Java 17+ required)
# https://www.zaproxy.org/download/
winget install --id=ZAP.ZAP -e
# ya
scoop install zaproxy
# ya
choco install zaproxy
```

**Linux:**
```bash
sudo snap install zaproxy --classic
# ya Debian/Ubuntu
wget https://github.com/zaproxy/zaproxy/releases/download/v2.17.0/ZAP_2_17_0_unix.sh
```

**macOS:**
```bash
brew install --cask zap
```

**Docker:**
```bash
docker pull ghcr.io/zaproxy/zaproxy
```

### Usage

**GUI (starter):**
1. Launch ZAP → Quick Start tab
2. "Automated Scan" → URL daalo → Attack
3. Ye spider se crawl karega + passive scan + active scan

**CLI baseline scan:**
```bash
docker run -t ghcr.io/zaproxy/zaproxy zap-baseline.py -t https://example.com -r report.html
```

**Automation/API daemon mode:**
```bash
zap.sh -daemon -port 8080
```

### Pros/Cons
| Pros | Cons |
|------|------|
| 100% free, no paid tier | Slow on large apps |
| GUI for beginners | Java 17 required |
| Active + passive scanning | Some false positives |
| Huge add-on marketplace | Steep learning curve |

---

## 2. Nuclei

### Overview
**ProjectDiscovery ka template-based vuln scanner.** 9000+ community templates. Ye crawl nahi karta — specific checks run karta hai. Bahut fast.

### Kya find karta hai
- CVEs (known vulnerabilities)
- Misconfigurations
- Exposed panels/dashboards
- Secrets exposure
- Default credentials
- Known vulnerable paths

### Installation
```bash
# Go required (https://go.dev/dl/)
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# ya binary download
# https://github.com/projectdiscovery/nuclei/releases
```

### Usage
```bash
# Single URL
nuclei -u https://example.com

# Multiple URLs from file
nuclei -l urls.txt

# High severity only
nuclei -l urls.txt -severity high,critical

# JSON output
nuclei -u https://example.com -json -o results.json

# Update templates
nuclei -update-templates
```

### Full recon flow (subfinder + httpx + nuclei)
```bash
# 1. Subdomains
subfinder -d example.com -all -o subs.txt

# 2. Live hosts
cat subs.txt | httpx -silent -o live.txt

# 3. Vuln scan
nuclei -l live.txt -severity high,critical -o findings.txt
```

### Pros/Cons
| Pros | Cons |
|------|------|
| Bahut fast | Template quality vary karta hai |
| 9000+ templates | Crawling nahi (specific checks) |
| CI/CD ready | Known vulns only |
| Actively maintained | 9000 templates = false positives possible |

---

## 3. Subfinder

### Overview
**Passive subdomain enumeration tool.** DNS datasets se subdomains discover karta hai. Fast, reliable.

### Installation
```bash
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
```

### Usage
```bash
# Basic
subfinder -d example.com

# All sources + file output
subfinder -d example.com -all -o subs.txt

# Multiple domains
subfinder -dL domains.txt -o subs.txt
```

### Pros/Cons
| Pros | Cons |
|------|------|
| Passive (no touching target) | Needs API keys for best results |
| Fast, reliable | Only subdomains, not vulns |
| Many data sources | |

---

## 4. HTTPx

### Overview
**Live host discovery tool.** Kaunse subdomains live hai, status codes, titles, tech detect karta hai.

### Installation
```bash
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
```

### Usage
```bash
# Check live hosts from subfinder output
cat subs.txt | httpx -silent -o live.txt

# With title + tech detection
cat subs.txt | httpx -title -tech-detect -status-code
```

### Pros/Cons
| Pros | Cons |
|------|------|
| Fast | Only host discovery |
| Tech detection | |

---

## 5. Nmap

### Overview
**Sabse famous network scanner.** Ports, services, versions, vulnerabilities detect karta hai.
> **Is project mein installed ✅** (v7.94, `sudo apt install nmap` se).

### Usage (is project ke routing ke liye TOOLS.md #D1 dekhna)

### Installation
```bash
# Windows
# https://nmap.org/download.html
winget install --id=Insecure.Nmap -e

# Linux
sudo apt install nmap

# macOS
brew install nmap
```

### Usage
```bash
# Basic port scan
nmap example.com

# Service version detection
nmap -sV example.com

# Vulnerability scripts
nmap --script vuln example.com

# Top 100 ports fast
nmap --top-ports 100 -T4 example.com
```

### Pros/Cons
| Pros | Cons |
|------|------|
| Industry standard | Dev-hostile CLI (agar seekha nahi) |
| Port + service + vuln | Slow on full scans |
| GUI (Zenmap) available | |

---

## 5b. Dalfox

### Overview
**Fast, focused XSS scanner** (Go mein likha). Ek hi kaam karta hai — XSS — lekin karta hai achha. General scanner se faster aur thorough. Nuclei/manual se candidate milne ke baad XSS confirm karne ke liye best.

### Kya find karta hai
- Reflected XSS
- Stored XSS (partial)
- DOM XSS (with headless Chrome)
- Blind XSS (with callback earner)

### Installation (installed ✅ — binary at `/usr/local/bin/dalfox`)
```bash
# Already installed via precompiled binary. If reinstall needed:
curl -sL -o /tmp/dalfox.tar.gz https://github.com/hahwul/dalfox/releases/download/v3.2.2/dalfox-v3.2.2-linux-x86_64.tar.gz
tar xzf /tmp/dalfox.tar.gz && sudo cp /tmp/dalfox-v3.2.2-linux-x86_64/dalfox /usr/local/bin/dalfox
```

### Usage
```bash
# URL list se XSS pipe
cat urls.txt | dalfox pipe --silence --no-spinner -o xss.txt

# Single URL with param
dalfox url 'https://target.com/page?q=test' --silence -o xss.txt

# Blind XSS
dalfox url '<url>' --blind <your-earner-url>

# Fast/absence of false positives
dalfox url '<url>' --skip-bav
```

### Pros/Cons
| Pros | Cons |
|------|------|
| XSS mein best-in-class | Sirf XSS, general scanner nahi |
| Fast (Go) | Headless/DOM XSS ke liye --remote chahiye |
| CI/CD friendly | Noisy on large param sets |

### Use-case flow
1. `nuclei` se candidate XSS params mia
2. `dalfox` se confirm + PoC payload
3. Manual browser confirm → report

---

## 5c. WPScan

### Overview
**WordPress security scanner** (official, Automattic/Matt Mullenweg supported). Plugin/theme/core vulns, user enum, config issues detect karta hai.

> **Is system mein wpscan Docker wrapper ke roop mein installed hai** (`/usr/local/bin/wpscan`). Bina Ruby install kiye `wpscanteam/wpscan` image wrapper. Native command ki tarah use hota hai.

### Kya find karta hai
- WordPress core/plugin/theme known vulnerabilities
- Enumeration: users, plugins, themes, timthumb
- Weak passwords (brute-force — only if in scope + permitted)
- Configuration issues, exposed files

### Installation (installed ✅ — Docker wrapper)
```bash
# Already done. If reinstall:
docker pull wpscanteam/wpscan:latest
# wrapper at /usr/local/bin/wpscan
```

### Usage
```bash
# Full enum (plugins/themes/users)
wpscan --url https://target.com --enumerate

# Plugin vulns only (best signal)
wpscan --url https://target.com --enumerate vp

# With API token (better vuln data)
export WPSCAN_API_TOKEN="your-token"
wpscan --url https://target.com --enumerate

# Password brute (ONLY if explicitly in scope + permitted)
wpscan --url https://target.com --passwords /usr/share/wordlists/rockyou.txt
```

### Pros/Cons
| Pros | Cons |
|------|------|
| WordPress ka official scanner | Sirf WordPress targets |
| Deep plugin/theme vuln DB | Full vuln DB ke liye API token |
| Fast, accurate | Docker wrapper = first run slow |

### Use-case flow
1. `httpx` se WordPress detect karo (`-tech-detect`)
2. `wpscan --enumerate` se plugin/theme scan
3. Plugin version → nuclei/exploit-db se CVE verify
4. Report confirmed plugin vuln

---

## 6. Wapiti

### Overview
**French open-source black-box scanner.** Crawl karke forms/inputs find karta hai, phir payloads inject karta hai.

### Kya find karta hai
- SQL Injection
- XSS (reflected + permanent)
- XXE
- SSRF
- Command injection
- File inclusion
- CSRF

### Installation
```bash
pip install wapiti3
```

### Usage
```bash
# Basic scan
wapiti -u https://example.com

# HTTPS + output
wapiti -u https://example.com -f html -o report.html

# Authentication
wapiti -u https://example.com --auth-type basic -a user:pass
```

### Pros/Cons
| Pros | Cons |
|------|------|
| Lightweight | Small community |
| Real active scanner | Docs limited |
| Handles forms + auth | CLI only |

---

## 7. Burp Suite Community

### Overview
**Manual testing proxy.** Browser aur website ke beech mein baithta hai — requests capture/modify karta hai. **Yeh free version mein AUTOMATED scanner nahi deta** (woh Pro mein hai, $449/year). But IDOR, SSRF, auth testing ke liye best.

### Kya karta hai (Community)
- Intercept proxy
- Request/repeater
- Intruder (limited rate)
- Scanner — ❌ PRO only (ye yaad rakhna)

### Installation
```bash
# Download from
# https://portswigger.net/burp/communitydownload
```

### Usage
1. FoxyProxy/Browser mein proxy set karo → `127.0.0.1:8080`
2. Target browse karo → Burp captures requests
3. Repeater mein manually tamper karo (IDOR: user ID change karke test)
4. Intruder (rate-limited) se brute force / fuzz

### Pros/Cons
| Pros | Cons |
|------|------|
| Manual testing best | Scanner paywalled (Pro) |
| Industry standard | Community = limited features |
| Free forever | Intruder rate-limited |

---

## 8. Online / No-Install Platforms

Agar kuch install nahi karna — browser se URL paste karke scan:

| Platform | Kya karta hai | Account? | URL |
|----------|--------------|----------|-----|
| **SecScanner** | TLS, headers, DNS, cookies, CORS (62 checks), daily alerts | ❌ | https://secscanner.app/ |
| **VulnerAI** | XSS, SQLi, headers, auth issues, 5 scan types, PDF report | ❌ | https://vulnerai.tech/ |
| **CheckVibe** | 100+ checks, exposed API keys, SQLi, XSS, Supabase/Firebase config, SEO | ❌ | https://checkvibe.dev/free-website-security-scanner |

> ⚠️ **Yad rakho:** Online scanner ko external visibility preference bhi hota hai — sensitive targets apne local tools se test karna better hai.

---

## 9. AI-Powered Tools

### Strix — [usestrix/strix](https://github.com/usestrix/strix)
Autonomous AI pentesting agents. IDOR, auth bypass, SSRF, XSS, business logic.

```bash
# Install
curl -sSL https://strix.ai/install | bash
# Scan
strix --target url-or-repo
# CI/CD
strix -n -t ./ --scan-mode quick
```

### HunterX — [nullc0d30/HunterX](https://github.com/nullc0d30/HunterX)
AI-directed autonomous security assessment engine. Full lifecycle: recon → test → validate → report.

---

## 10. Recommended Workflow

### 🎯 Bug Bounty (HackerOne) Workflow

```
Phase 1: Recon (Passive)
  subfinder -d target.com -all -o subs.txt

Phase 2: Host Discovery
  cat subs.txt | httpx -silent -o live.txt

Phase 3: Automated Scan
  nuclei -l live.txt -severity high,critical -o nuclei_results.txt

Phase 4: Manual Deep Dive  ← SABSE IMPORTANT
  OWASP ZAP / Burp Suite par:
   - Active scan ZAP se
   - IDOR test (ID change karke)
   - Auth bypass test
   - SSRF test
   - Business logic test

Phase 5: Verify + Report
  - PoC confirm karo
  - HackerOne par structured report likho
```

### ✅ Local Project (LeadGuard) Testing

```
1. OWASP ZAP full active scan
   → XSS, SQLi, CSRF, headers, session

2. Nuclei template scan
   → known CVEs, misconfigs

3. Burp/ZAP manual
   → IDOR, auth, SSRF — auditors

4. Online scanner
   → quick external posture check
```

---

## 11. Bug Bounty Hunting Checklist

### Recon Phase
- [ ] Subdomains enumerate (subfinder)
- [ ] Live hosts filter (httpx)
- [ ] Tech stack detect (httpx -tech-detect / Wappalyzer)
- [ ] DNS records check (SPF, DMARC, CAA)
- [ ] Ports/services scan (nmap)
- [ ] JS files / endpoints enumerate (linkfinder, gau)

### Vulnerability Phase
- [ ] Nuclei template scan
- [ ] OWASP ZAP active scan
- [ ] Manual IDOR testing (ID tampering)
- [ ] Auth/session testing (JWT attacks, session fixation)
- [ ] SSRF testing (URL parameters)
- [ ] Injection testing (SQLi, XSS, command, SSTI)
- [ ] Business logic flaws
- [ ] API security testing

### Reporting Phase
- [ ] Reproduce in clean environment
- [ ] Confirm PoC with screenshots
- [ ] Impact assessment (real, not theoretical)
- [ ] Check HackerOne scope + out-of-scope
- [ ] Write structured report (summary, steps, impact, fix)
- [ ] Submit → monitor triage

---

## 🔗 Useful References

- **OWASP ZAP Docs:** https://www.zaproxy.org/docs/
- **Nuclei Docs:** https://docs.projectdiscovery.io/tools/nuclei/overview
- **HackerOne Hacktivity (prior art):** https://hackerone.com/hacktivity
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **OWASP Juice Shop (practice target):** https://owasp.org/www-project-juice-shop/

---

## 🧠 Final Advice

1. **Automated tools = low-hanging fruit.** Real bounty = manual testing.
2. **SIRF authorized targets.** Legal raho.
3. **Har finding verify karo** pehle report karne se.
4. **Practice:** OWASP Juice Shop / DVWA par free practice karo.
5. **Quality > quantity.** Ek solid IDOR/SSRF ek hazar duplicates se better.


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

🥇 1. OWASP ZAP — Sabse Best (100% Free, GUI + Install)
Ye sab karta hai: XSS, SQL injection, CSRF, IDOR, SSRF, broken auth, session handling, exposed secrets, headers — poore OWASP Top 10
- ✅ Active Scanning — real attack payloads bhejta hai (SQLi, XSS probes)
- ✅ Passive Scanning — safe, background mein
- ✅ GUI hai (mouse se chalana easy) + CLI + Docker
- ✅ 100% free, koi paid tier nahi
- ✅ Windows/Linux/macOS par chalega (Java 17 chahiye)
- ✅ Authorized targets par — everyday use ke liye perfect
Download: 👉 https://www.zaproxy.org/download/
# Linux
sudo snap install zaproxy --classic
# Windows
winget install --id=ZAP.ZAP -e
🥈 2. Nuclei — Automated Template Scanner (Free)
Ye 9,000+ vulnerability templates (CVEs, misconfigs, exposed panels) chala sakta hai — bahut fast.
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
nuclei -u https://example.com
Aapne LeadGuard project mein jo security audit kiya wahi skills yahan use hoti hain.
🥉 3. Recon Toolkit (Free, Automated Pipeline)
Ye subfinder → httpx → nmap → nuclei full automated karta hai:
- exorrtech/recon-toolkit (https://github.com/exorrtech/recon-toolkit)
- trinetlayer/Trinetlayer-Recon-Automation (https://github.com/trinetlayer/Trinetlayer-Recon-Automation)
🖥️ 4. Online / No-Install Platforms (Browser se)
Agar install nahi karna, sirf URL paste karo:
Platform	Kya check karta hai
VulnerAI (https://vulnerai.tech/)	XSS, SQLi, security headers, auth issues
CheckVibe (https://checkvibe.dev/free-website-security-scanner)	100+ checks, exposed keys, SQLi, XSS
SecScanner (https://secscanner.app/)	TLS, headers, DNS, cookies, CORS (62 checks)
Vulnify (https://vulnify.app/online-vulnerability-scanner)	SQLi, XSS, OWASP, SSL
🧠 AI-Powered Options (Free/Open Source)
- Strix (usestrix/strix (https://github.com/usestrix/strix)) — AI pentesting agents, IDOR, auth bypass, SSRF, XSS sab
- HunterX (nullc0d30/HunterX (https://github.com/nullc0d30/HunterX)) — autonomous, IDOR/SSRF/XSS/command injection
💡 Meri Recommendation (Free + Complete)
Kaam	Tool
Full scan (GUI)	OWASP ZAP
Fast automated scan	Nuclei
Online quick scan	VulnerAI / CheckVibe
Manual testing/proxy	Burp Suite Community
⚠️ Zaroori Baat:
Ye tools sirf authorized targets par use karo — jaise aapka apna LeadGuard, ya HackerOne in-scope assets. Bina permission ke kisi site par active scanning illegal hai.
Kya aap chahte ho ki main aapke LeadGuard project par OWASP ZAP ya Nuclei setup kar doon?
▣  Build · Big Pickle · 22.8s
inme se kis tool ka use hackerone se liye project par kar skte h
Aap LeadGuard OS V6 par HackerOne ke liye tools use karna chahte ho. Ek important clarification pehle:
⚠️ Aap apne khud ke LeadGuard project par testing kar sakte ho — ye to authorized hai. Lekin LeadGuard itself HackerOne ka program nahi hai (ye aapka khud ka project hai).
HackerOne par bounties ke liye aapko unke in-scope programs ke assets test karne hote hain, jo leadguard nahi hai.
✅ Kis tool ka use kar sakte ho (HackerOne hunting ke liye):
Best combo HackerOne ke liye:
Tool	Kyun
Nuclei	Sabse best — 9000+ templates, fast, ek command. Recon + vuln scan both
OWASP ZAP	Manual/active scanning, auth handling ke liye
Burp Suite Community	Manual web app testing, intercept requests (IDOR/SSRF hand testing)
subfinder + httpx + nuclei combo	Subdomain discovery → live hosts → vuln scan
🔧 Recommended Setup (Free, HackerOne-ready):
# 1. Nuclei
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# 2. subfinder (subdomain discovery)
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

# 3. httpx (live host probing)
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

# 4. OWASP ZAP
sudo snap install zaproxy --classic
🔍 Workflow HackerOne hunting ke liye:
# Step 1: Subdomains dhundho (authorized target)
subfinder -d example.com -all -o subs.txt

# Step 2: Live hosts filter karo
cat subs.txt | httpx -silent -o live.txt

# Step 3: Vulnerabilities scan karo
nuclei -l live.txt -severity high,critical -o results.txt

# Step 4: Manual testing (IDOR/SSRF/auth)
# Burp Suite ya OWASP ZAP se
💡 Sabse important kaam:
HackerOne par manual testing (Burp Suite/ZAP) kaafi bada role karta hai — IDOR, business logic, auth bypass ye automated tools se nahi nikalte. Nuclei sirf low-hanging fruit pakadta hai.
Meri recommendation:
1. HackerOne par simple/beginner programs chuno (in-scope assets dekh ke)
2. subfinder+httpx+nuclei se automated recon+scan
3. Burp Suite / ZAP se manual deep dive
⚠️ Phir se yaad rakho — sirf authorized in-scope targets. LeadGuard aapka hai, uspar free testing kar sakte ho. HackerOne ka paisa kamana hai to unke programs ke authorized assets par.
Kya aap chahte ho ki main aapke PC par Nuclei + subfinder + httpx setup kar doon?


