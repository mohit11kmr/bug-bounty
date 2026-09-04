# Kiwi.com Bug Bounty — Complete Work & Evidence Report

**Engagement:** Authorized HackerOne vulnerability research on Kiwi.com
**In-scope:** `www.kiwi.com` · `*.kiwi.com` · `*.skypicker.com` (all bounty wildcards)
**Research date:** 2026-08-30 → 31
**Methodology:** Official sandbox test-bookings + live API/cross-origin testing via CDP-driven guest flow + passive recon.

---

## 1. Discovery / Reconnaissance

### 1.1 Subdomain enumeration (passive)
- `subfinder -d kiwi.com -d skypicker.com` + certspotter/Crtsh → **2,120 subdomains** captured (`/tmp/opencode/kiwi_subs.txt`)
- Alive probing (`httpx`) → 59 live hosts (`/tmp/opencode/kiwi_alive.txt`)
- DNS fingerprinting: Fastly wildcard fanout (`151.101.x.42`, ~505 hosts); remaining on GCP/Cloud Run, email SaaS (Mailgun/Customer.io/Google Workspace), VIO/Holibob/StatusPage etc.

### 1.2 Subdomain takeover scan (2120 subs, 31 CNAMEs)
| Result | Detail |
|---|---|
| `go.kiwi.com` | A→CloudFront→S3 (eu-west-1), serves `NoSuchKey` 404 for index; bucket **still owned** → not claimable now |
| `terraform-modules.skypicker.com` | CloudFront→S3, `AccessDenied` XML; bucket owned → not claimable now |
| `nyrujhhu3yuk.nest.skypicker.com` | CNAME→`gv-kf2bduhpnlc3y3.dv.googlehosted.com` (**does not resolve** — dangling, but Google domain-verification token only, low value) |
| `mail.kiwi.com`/`mail.skypicker.com` | CNAME→`ghs.google.com` live (Google Workspace) — flag-only |
| **Overall** | **No immediately claimable dangling takeover.** Kiwi DNS hygiene is good. |

---

## 2. Environment & Tooling

- Chrome copy-profile at `/home/mohit/.config/google-chrome-rd` launched with `--remote-debugging-port=9222`
  (raw CDP over WebSocket + `fetch('http://127.0.0.1:9222/json')`).
- CDP driver scripts (in `/tmp/opencode/`):
  - `cdp.mjs` — page eval / navigation / getAllCookies
  - `cdp_frame.mjs`, `cdp_evalframe.mjs`, `cdp_fillcard.mjs` — cross-origin React card iframe driven via
    `Target.attachToTarget` (OOPIF) + `Input.insertText`
  - `cdp_net.mjs`, `cdp_all.mjs`, `cdp_req.mjs`, `cdp_req2.mjs` — network capture of booking BFF API traffic
  - `cdp_cookies.mjs`, `cdp_csrf.mjs`, `cdp_csrf2.mjs` — cookie/SameSite/CSRF analysis
  - `cdp_fresh.mjs`, `cdp_read.mjs` — fresh-incognito-context tests
- Manual API testing with `curl` + python JSON parsing.

---

## 3. Sandbox Test Bookings (official testing method)

Method per Kiwi program policy: `&sandbox=true` (GDPR-sandbox) + `sandbox_payment=true` cookie + test card
`4111 1111 1111 1111 / 12/42 / 123 / TEST APPROVE`. Guest booking flow completed end-to-end twice.

| Booking ID | Route | Dates | Airlines | Amount | Invoice # | Invoice hex | Token |
|---|---|---|---|---|---|---|---|
| **836540056** | DEL ↔ BOM | 2026-09-12/21 | QP6520 (Akasa Air), AI9487 (Air India) | ₹15,317.75 | **2026-124796** | `4541b58c22114e92` | `8993c95a-f43a-41a4-8eea-5156393beaf5` |
| **836546238** | DEL ↔ GOA | 2026-10-05/16 | AI Express (IX), IndiGo (6E) | ₹18,402.54 | **2026-124797** | `7511843770b84a24` | `b4f1b412-3477-4089-99cf-e8db69e9d18e` |

Both confirmed with `/en/trips/<id>/thank-you/` "Payment received". Passenger: TEST TEST (id 129710516).
Payment card iframe host observed: `fe.payments-kiwi-dev.com` (**out of scope — not a kiwi.com/skypicker.com registrable domain**).

---

## 4. Findings & Assessments

### 4.1 [LOW / INFORMATIONAL] CORS misconfiguration — booking-api.skypicker.com
**Verified evidence:**
```
GET /mmb/v1/bff/web/bookings/836546238/live_boarding_pass?is_browser=true&language=en-GB&currency=INR
    Host: booking-api.skypicker.com          (IN SCOPE: *.skypicker.com)
    Origin: https://evil.com
 => HTTP 200
    access-control-allow-origin: https://evil.com        <-- arbitrary origin REFLECTED
    access-control-expose-headers: KW-Simple-Token

OPTIONS (preflight) with Access-Control-Request-Headers: kw-simple-token, Origin: https://evil.com
 => HTTP 200
    access-control-allow-origin: https://evil.com
    access-control-allow-methods: HEAD,DELETE,GET,HEAD,OPTIONS,PATCH,PUT,POST
    access-control-allow-headers: DNT,X-Mx-ReqToken,Keep-Alive,User-Agent,X-Requested-With,Cache-Control,Content-Type,
        X-WHOIAM,X-WHOIAM-SESSION,X-FORTER,X-Riskified,X-Application,authorization,KW-Partner-Token,KW-User-Token,
        KW-Simple-Token,KW-Auth-Token,KW-Marketplace-Token,KW-Marketplace-Secret-Token,X-API-Version,X-Client-Version,
        X-Client-Timestamp,X-Paylib-Auth-Retry
    access-control-expose-headers: KW-Simple-Token
    (NO access-control-allow-credentials observed)
```
**Assessment:**
- Arbitrary `Access-Control-Allow-Origin` reflection + full privileged header allow-list.
- **Mitigating:** no `Access-Control-Allow-Credentials`; auth is header-based (`kw-simple-token`), not cookie-based;
  attacker needs the victim's booking token to read anything → no standalone impact today.
- **Escalation path:** if XSS/token-leak anywhere in the booking path is found, arbitrary-origin reflection turns
  booking data readable from attacker origin. **Candidate worth submitting ONLY as part of a demonstrated chain.**

### 4.2 [N/A / INFORMATIONAL] Invoice PDFs on files.kiwi.com served without authorization
**Verified evidence:**
- MMB invoice API requires `kw-simple-token` (401 without).
- But the invoice PDF itself: `GET https://files.kiwi.com/invoices/sandbox/invoice_2026_4541b58c22114e92_836540056.pdf`
  → **HTTP 200 with NO token** (also 200 in fresh curl without cookies).
- Filename pattern `invoice_2026_<16hex>_<bookingId>.pdf`; GCS bucket `booking-invoice-documents-5c099d6f` (list → 403).
- Second booking → independent hex `7511843770b84a24`. Cross-comparison: only 3/16 positions shared (random overlap);
  16-hex chars = 64-bit, **not derivable** from booking id / invoice number / timestamps (md5/sha1/sha256 checked).
- Invoice contents: passenger name, itinerary, prices, supplier legal entity — **no email/phone/ID**.
**Assessment:** unguessable *capability-URL* design (64-bit random per invoice, no directory listing, no enumeration
vector). Under program policy exclusions → **N/A. Do not submit.**

### 4.3 Umbrella GraphQL (api.skypicker.com, IN SCOPE) — potential authz surface, NOT demonstrated
**Verified evidence:**
- GraphQL introspection **enabled anonymously**: 372 types, RootQuery 25 fields, 20 mutations.
- User-sensitive queries present: `userWishlists(userEmail, wishlistIds, ...)`, `userWishlistNames(userEmail)`,
  `userData(...)`, `papayaConversationsHistory(userID, visitorID)`.
- All tested auth-aware fields return `AppError "No authorization token"` without a **user** auth token.
  A booking `kw-simple-token` is **rejected** (only passes query shape-validation).
- WishlistIds must be RFC-4122 UUIDs (non-enumerable by format).
**Assessment:** architecture exposes *email-argumented* user queries → classic **cross-user authorization surface**.
Cannot be confirmed without a logged-in Kiwi account (login OTP requires an inbox, which the tester cannot access).
**Highest-value unverified lead.**

### 4.4 Duplicate-account verification → FALSE POSITIVE resolved (umbrella wishlists IDOR)
**Hypothesis tested with two real accounts** (attacker `mohitsikarwar123@gmail.com`, victim `pinkee391989@gmail.com`):
- Initial observation: `createUserWishlist(userEmail:"victim@...")` + `userWishlistNames(userEmail:"victim@...")`
  returned attacker-visible data → looked like cross-user write+read.
- **Resolution with 2 accounts found `userEmail` is decorative:** each access-token (JWT `sub`) reads/writes only its
  OWN namespace, regardless of the `userEmail` argument passed. Victim token + attacker-email → victim data (and
  vice-versa). `kw-simple-token`/user-JWT is strictly owner-bound.
- REST twin `umbrella/wishlist/bucket_names` also token-bound (attacker→empty, victim→own bucket).
- **Verdict: NOT an IDOR.** Documented so a future tester doesn't re-chase it. (Also validates the program's
  multi-account testing guidance: single-account checks produced a convincing but wrong conclusion here.)

### 4.5 Business-logic / payment-flow probing (2 real sandbox bookings) — NOT exploitable
Rationale for "anyone can book" not being a finding: guest checkout is intended functionality.
Tested attacker-value angles that make guest-booking a *risk*:
- **Payment bypass / confirm-without-pay:** booking ID only issued on the `/thank-you/` page after the card
  iframe payment succeeds; `activeStep` gating is server-controlled; no confirm endpoint responds without an
  authorized simple-token + paid state.
- **Amount tampering (pay ₹0/₹1):** flight/passenger price lives in an encrypted prebooking `token=` blob
  (1089-byte ciphertext, high-entropy, server-signed — not plaintext base64, not modifiable). Ancillary
  (seating ₹1947/segment, fare options) prices are server-computed; post-booking `seating`,
  `guarantee`?currency=, `fare_conditions` endpoints all return availability/gating states — no client-price echo
  beyond display.
- **Cross-account booking tamper:** MMB sub-resources require the booking-bound `kw-simple-token`; another
  account's valid user-JWT → 401 (§4.4/MMB audit).
- **Result:** business-logic attacks against the booking/payment flow not demonstrated. Guest bookability alone is
  not a vulnerability under program policy.

### 4.6 CLean / Not vulnerable (verified)
| Check | Result |
|---|---|
| Anonymous SSR `/en/trips/<bookingId>/` | SPA shell only — **no PII embedded** (verified zero occurrence of "TEST"/token in HTML) |
| Fresh incognito context → `/en/trips/<bookingId>/` | **Redirected to `/en/user/login/?redirectUrl=...`** (authorization enforced) |
| MMB API with no token | 401 |
| MMB API with wrong booking's token | 401 (token **strictly booking-bound**) |
| MMB sub-resource audit (22 paths: live_boarding_pass, itinerary, passengers, contact, email, invoice, receipts, refunds, options, payment-method, signing_wizard, insurance, change-quote, etc.) | All 401/404 no-token & wrong-token |
| `/token`, `/simple_tokens` endpoints | 404 — no token-generation/idor route |
| `simple_token-<bid>` cookie flags | non-HttpOnly + Secure + default SameSite Lax → matches policy exclusion (cookie flags) |
| CSRF | Auth via custom header + Lax cookies → not in play |
| Open redirects (`login?redirectUrl=`, `booking?backToSearchUrl=`) | No Location redirect triggered |
| `www.kiwi.com/_next/image` SSRF probe (127.0.0.1 / 169.254.169.254 / api hosts) | Returns SPA HTML only — image optimizer not exposed |
| Subdomain takeover | No claimable dangling records |

### 4.7 [MEDIUM / CONFIRMED] Unauthenticated data leak via shared-CDN cache on `umbrella/wishlist/bucket_names`

**Reproduction (verified twice, sustained > 9 minutes):**

1. Authenticated victim request (any logged-in Kiwi user whose wishlist widget fires):
   ```
   GET https://api.skypicker.com/umbrella/wishlist/bucket_names
   Authorization: Bearer <victim JWT>
   ```
   Response: victim's private wishlist names + wishlistIds
   (`{"data":{"buckets":[{"wishlistId":"7814245b-...","name":"CROSS-EMAIL-TEST-9393",...},{"wishlistId":"7089cc36-...","name":"MY-SECRET-TRIP-PLAN",...}]},"status":"SUCCESS"}`)
   Headers: `age: 531`, `x-cache: MISS, HIT`.

2. **Unauthenticated attacker poll of the exact same URL (no cookie, no auth header):**
   ```
   GET https://api.skypicker.com/umbrella/wishlist/bucket_names
   ```
   Response: **HTTP 200 with the victim's cached wishlist data** (`age` kept growing 544+, `x-cache: HIT`,
   zero `Set-Cookie`, no 401 interleave across 6+ consecutive polls).

**Root cause:** the edge cache (Varnish/CDN in front of uvicorn; `x-served-by: cache-qas-...`) keys this
user-specific endpoint **only on URL** (`Vary: Accept-Encoding`). The `Authorization` header is **not part of the
cache key**, and the origin emits no `Cache-Control: private/no-store`. First caller of the URL populates the
shared cache; every subsequent caller (any user — or **no user at all**) receives the last writer's private data.

**Impact:** unauthenticated disclosure of arbitrary logged-in Kiwi users' wishlist contents (names + wishlist IDs —
privacy-sensitive trip plans). An attacker polling this single public URL repetitively harvests the wishlists of
whatever Kiwi user happened to load their wishlist most recently. Cache TTL sustained >9 minutes in testing.

**Severity rationale:** [MEDIUM] — cross-user, unauthenticated, reproducible exposure of private user data through a
shared-cache keying flaw on an authenticated endpoint. No manipulation of victims needed beyond normal platform use.

**Scope check:** `api.skypicker.com` = `*.skypicker.com` → **in scope**.

---

## 5. Raw Evidence Index (files in /tmp/opencode)
| File | Contents |
|---|---|
| `lbp_hdr.json` | Live boarding pass API response (booking 1, via kw-simple-token header) |
| `booking_root.json` | `/bookings/836540056` root — booking_details + passenger (TEST TEST, id 129710516) |
| `inv.json`, `inv2.json` | Invoice-list API responses (token-gated) |
| `inv.pdf`, `inv2.pdf` | Invoice PDFs (public download) + `inv_ext.txt` extracted text |
| `trips_page.html` | Anonymous SSR of trips page (PII-free shell) |
| `kiwi_subs.txt` (2120), `kiwi_alive.txt` (59) | Recon lists |
| `cookies.json` (2456 cookies) | Browser cookie dump |
| `hdr.txt` | CORS response headers evidence |
| `bucket_names_leak*.json/.h` | **4.7 cache-leak evidence** (authed seed + unauthed HIT + `age` growth, poll bodies) |
| `access.jwt`, `access_victim.jwt`, `umbrella.tok`, `cap.json` | Two-account auth token evidence (attacker + victim) |

---

## 6. Conclusion & Next Steps

**Current verdict: ONE CONFIRMED, SUBMITTABLE VULNERABILITY — §4.7 (shared-CDN unkeyed-auth cache leak,
`api.skypicker.com/umbrella/wishlist/bucket_names`, unauthenticated cross-user data exposure, [MEDIUM]).**

Updated status after the §4.7 discovery:
1. **§4.7 cache leak — CONFIRMED [MEDIUM], submission-ready.** Reproduced twice with fresh tokens on the exact
   real frontend URL; unauthenticated attacker gets logged-in users' wishlist data with no auth header; cache
   maintained >9 min. Direct, in-scope, no chain required.
2. **CORS reflection (4.1)** — Low/Informational; secondary — could be rolled in as supporting evidence only.
3. **Umbrella `userWishlists`/`userData` (4.3/4.4)** — RESOLVED NEGATIVE for IDOR (token-bound).
4. **Invoice (4.2)** — unguessable capability-URL; N/A.
5. **MMB (all sub-resources)** — booking-bound token mandatory; 401 cross-account.
6. **Business-logic/payment (4.5)** — not exploitable.

**Recommended action:** write and submit the H1 report for §4.7. Supporting material:
- EXACT URL + unauthed-vs-authed request pairs (curl commands).
- Response-body evidence showing victim wishlist data served with `x-cache: HIT`, `age` growth, zero auth.
- Root-cause note: `Authorization` not in cache key + no `Cache-Control: private`.
- Attach: `curl` PoC in `#proof-of-concept`; evidence files listed in §5.

Everything else remains closed with no submission.

---

*Report compiled 2026-08-31 by mohit on the Kiwi.com HackerOne program.*