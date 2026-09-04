# PRICELINE BUG BOUNTY — PROGRESS REPORT (Claude session, 2026-09-01 overnight)

**HackerOne program:** priceline (public, offers_bounties=true, allows_bounty_splitting=true)
**H1 username:** mohit11kmr
**⚠️ Security note:** The H1 API token you pasted in chat was used read-only (list programs, fetch scope) then discarded from shell env. Recommend rotating it since it was sent in plaintext chat.

---

## 1. SCOPE (from live API, `GET /v1/hackers/programs/priceline?include=structured_scopes`)

In-scope + bounty-eligible (max_severity=critical unless noted):
- `priceline.com`, `www.priceline.com`, `cruises.priceline.com`, `flyiin.com`
- `www.getaroom.com`, `ir.bookingholdings.com`, `bookingholdings-coe.com`
- `press.priceline.com` (max_sev=medium)
- `https://www.priceline.com/pwd/v0/pcln-graphql/` (GraphQL endpoint, explicit scope entry)
- `AI_MODEL: Penny` (their chatbot — prompt injection / business-logic bypass in scope)
- `APPLE_STORE_APP_ID: 336381998`
- `GOOGLE_PLAY_APP_ID: com.priceline.android.negotiator` ← **this is what we've been working on**

Policy highlights:
- `*.priceline.com` in-scope generally (bounty decided by impact) — **this covers the internal `deva/devb/qaa/qab/qac.priceline.com` hosts found hardcoded in the app** (see below).
- MUST send header `X-Bug-Bounty: mohit11kmr` on all test requests (WAF/PerimeterX will block otherwise, though PerimeterX still blocks raw scripted requests regardless — need real browser or mobile app traffic).
- Use test bookings via HackerOne email alias `mohit11kmr@wearehackerone.com`; cancel any real reservations made.
- Two-account IDOR testing is explicitly encouraged by the policy ("create two accounts... test cross-account access").
- Video PoC required for payout; no automated-scanner-only reports.

---

## 2. WEB RECON — BLOCKED

Raw `curl` to `pwd/v0/pcln-graphql/` (introspection query) → **403, PerimeterX captcha challenge**. Scripted/curl-based testing of the web surface doesn't get past the WAF. Real browser (or the mobile app, which we pursued) needed.

---

## 3. ANDROID APP — FULL MITM PIPELINE WORKING ✅

Device: Realme C11 2021 (RMX2185), stock/unrooted, `com.priceline.android.negotiator` v17.9.399 (399) installed from Play Store.

**What's set up and confirmed working right now:**
- `mitmdump` running on the PC, listening on port 8080, writing flows to `/tmp/mitm_captures/priceline_traffic.flow` (background PID — check with `ps aux | grep mitmdump`).
- `adb reverse tcp:8080 tcp:8080` active (phone reaches the proxy via localhost over USB).
- Phone's WiFi manual proxy set to `127.0.0.1:8080` (done by user).
- mitmproxy CA cert installed as a **User** trusted cert on the phone (Settings → Security → Trusted certificates → User → "mitmproxy").
- **APK patched and re-signed** to make TLS interception actually work:
  - `android:debuggable="true"` added to manifest → activates the app's own pre-existing (but normally inert) `debug-overrides` network-security-config which trusts user CAs.
  - Fixed ~85 resource-table breakages introduced by apktool decompile/recompile round-tripping (inline `<aapt:attr>` gradients extracted as `$name` private resources that aapt2 can't recompile; empty `animated-vector`/`animated-selector` transitions that got silently dropped, causing `Resources$NotFoundException` crashes on the Sign In / Create Account screens specifically). Fixed by neutralizing animated transitions to plain `<selector>`s and stubbing genuinely-missing resource IDs as transparent-color values-items.
  - Rebuilt with `apktool b --use-aapt2`, signed with a debug key (`/tmp/debug.keystore`, pass `android`), installed via `adb install-multiple` (base + arm64_v8a + xhdpi splits, all re-signed with the same key — required, mixed signatures fail install).
- **Confirmed: full HTTPS decryption works.** Live traffic seen for `www.priceline.com`, Firebase, Forter (fraud detection), Kochava (attribution), Facebook, Google Ads — i.e. no certificate pinning blocking us at the network layer for these hosts.
- **Confirmed: Sign In and Create Account screens load without crashing** (post resource-fixes). Standard email/password flow, Google/Facebook social sign-in buttons present.

**Artifacts on disk (all under `/tmp`, will survive until reboot/cleanup):**
- `/tmp/priceline_apktool/` — the patched apktool decompile (source of truth for further edits)
- `/tmp/priceline_patched_signed.apk`, `/tmp/split_arm64.apk`, `/tmp/split_xhdpi.apk` — currently-installed signed APKs
- `/tmp/priceline_decompiled/` — jadx decompile (readable Java/Kotlin source, for code reading — this one wasn't repackaged, just for reading)
- `/tmp/mitm_captures/priceline_traffic.flow` — captured traffic so far (mostly startup telemetry, not yet auth flows)
- `/tmp/debug.keystore` — signing key for any future rebuilds (`pass:android` for both store and key)

---

## 4. INTERESTING LEADS FOUND (not yet exploited/confirmed)

1. **Internal hostnames hardcoded in the shipped app**: `deva.priceline.com`, `devb.priceline.com`, `qaa.priceline.com`, `qab.priceline.com`, `qac.priceline.com` (from `com.priceline.ace.core.network.Environment` enum in the decompiled code). These are covered by the `*.priceline.com` scope note. Worth checking if any are reachable and less hardened than prod (staging environments often are).
2. **Accountless OTP auth module**: `com.priceline.commons.accountlessauth` package, hits `account-less-auth/api/v1` (from `RestApiPath.kt`). This is a phone/email OTP-based guest-auth flow — haven't found the UI trigger for it yet in this app version (the Sign In / Create Account screens use email+password, not OTP). It might only appear during guest checkout on a booking flow, or in a different entry point. **This was the original target of interest** (matches the classic OTP rate-limit / enumeration bug class).
3. GraphQL endpoint introspection blocked by WAF from scripted requests — worth trying via the app itself (its own requests to `pwd/v0/pcln-graphql/` should pass WAF since they'll look like normal app traffic once we capture them through the working MITM setup).

---

## 5. NEXT STEPS (pick up here)

1. Check `ps aux | grep mitmdump` — if it's still running, the capture file is still being appended. If not, restart: `mitmdump -w /tmp/mitm_captures/priceline_traffic.flow --listen-port 8080 &` and redo `adb reverse tcp:8080 tcp:8080`.
2. Navigate the app further to find the accountless-auth/OTP trigger (try: Search Hotels → pick a hotel → Book → guest checkout, or "Forgot Password", or check if entering a phone number anywhere triggers it instead of email).
3. Once OTP flow traffic is captured, inspect the request/response for: OTP length/complexity, rate-limiting (send it 5-10 times fast, watch for a 429 or lack thereof), whether the verify-OTP response leaks anything (timing difference between wrong-OTP and expired-OTP, or the actual code in a debug/staging response).
4. Try the two-account IDOR pattern explicitly encouraged by policy: create two real test accounts (via `mohit11kmr@wearehackerone.com` style aliasing — check if `+` sub-addressing works, e.g. `mohit11kmr+1@wearehackerone.com`), get an authenticated session for account A, then try referencing account B's booking/trip IDs (sequential? UUID? predictable?) on endpoints under `pws/v0/...`.
5. Before drafting any report: re-read the Priceline policy's non-qualifying list (session-token-in-URL is explicitly already known/excluded; rate-limiting issues are excluded unless they enable a bigger impact like account takeover).
6. Anything you plan to submit needs a video PoC per policy — plan to record the phone screen (or use `adb shell screenrecord`) once a real finding is confirmed.

Nothing was submitted anywhere. No real bookings were made. The app on the phone is patched (not the original signed Play Store build) — if you want the real detection-fingerprint-authentic queen app for further prod parity testing, it may need reinstalling from Play Store (this loses the MITM ability again until re-patched the same way).
