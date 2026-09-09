<img src="assets/logo.svg" alt="TriagePilot" width="360">

# How to Use TriagePilot

TriagePilot is a bug-bounty automation and verification assistant. It runs
entirely on your own machine — recon, scanning, and verification all happen
locally, using your own HackerOne credentials. A lightweight account server
only handles login and your subscription/trial status.

> Detailed Hindi command-by-command walkthrough: [`docs/MERA_HUNTING_MANUAL.md`](docs/MERA_HUNTING_MANUAL.md)

---

## 1. Install

```bash
git clone <your-private-repo-url>
cd TriagePilot
./install_dependencies.sh      # installs subfinder, dnsx, httpx, gau, katana, nuclei
chmod +x start-bugbounty.sh
```

Requires Python 3.12 (the bundled verification engine is a compiled extension
tied to that exact version) and a Linux machine (tested on Ubuntu/Debian).

## 2. Launch

```bash
./start-bugbounty.sh
```

First run walks you through:
1. **Account** — register/login (free 4-day trial, then a subscription is required)
2. **HackerOne credentials** — your own API token, so TriagePilot can discover
   the programs you're already authorized on ([hackerone.com/settings/api_token](https://hackerone.com/settings/api_token))

## 3. Pick a target

From the Main Menu, `[N]` (New Scan) gives you four ways to pick a target:

- Cash-bounty programs only
- All programs (paid + VDP)
- Type a known handle directly
- **Newest/least-crowded programs** — sorted by how recently they joined HackerOne, so you're not competing with thousands of hunters who found it first
- Company mode (`[5]` inside New Scan) — for monitoring your own domain, no HackerOne program needed

## 4. Run a hunt

Once a target is set up, the recommended action is:

**`[A]` Autonomous Zero-Touch Hunt** — recon → scan → verify → draft report, fully automatic. No manual triage needed for the deterministic checks (CORS misconfig, secret exposure, GraphQL introspection); those are only marked **VERIFIED** when the tool has actually confirmed them against the live target — never fabricated.

## 5. Two ways to run continuously (instead of one target at a time)

- **`[P]` Autopilot** — one switch. Turn it ON and it keeps discovering fresh programs, setting them up, hunting them, and moving to the next one — forever, until you turn it off. Auto-tunes scan intensity to your machine's CPU/RAM.
- **`[M]` Watchdog** — pick one specific site (yours, or a program you're hunting) and it re-checks it on an interval you choose (15 min / 1 hr / 6 hr / 24 hr / custom), alerting you the moment something new shows up.

## 6. Get notified

`[T]` sets up Telegram alerts — every VERIFIED finding is pushed to your phone the moment it's confirmed, with a draft report attached.

## 7. Check status anytime

- `[D]` System Diagnostics — every tool/credential/account status, one screen
- `[V]` Dashboard — candidates, verified findings, and last-run summary across all your targets
- `[J]` Background Jobs — what's actually running right now

---

## Subscription

Free trial: 4 days from account creation. After that, an active subscription
is required to keep scanning. See [`legal/TERMS_OF_SERVICE.md`](legal/TERMS_OF_SERVICE.md).

## Help, Support & Feedback

See [`SUPPORT.md`](SUPPORT.md).

---

**TriagePilot** v1.0.0
