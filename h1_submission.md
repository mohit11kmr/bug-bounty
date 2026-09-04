# Title

Unauthenticated cross-user data leak via shared CDN cache on `api.skypicker.com/umbrella/wishlist/bucket_names` (Authorization not part of cache key)

---

# Weakness

CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor) / cache-keying bug on an authenticated endpoint (unkeyed Authorization; effectively a shared-cache leak of another user's private data).

# Program / Scope

- Program: Kiwi.com (HackerOne)
- Asset: `api.skypicker.com` (covered by in-scope `*.skypicker.com`) — endpoint `GET /umbrella/wishlist/bucket_names`

# Summary

`GET https://api.skypicker.com/umbrella/wishlist/bucket_names` returns the **authenticated user's private wishlists** (wishlist names + internal wishlist IDs). The response passes through a shared edge cache (Varnish in front of the uvicorn origin; `via: 1.1 varnish`, `x-served-by: cache-qas-*`) that keys responses **only on the URL** (`Vary: Accept-Encoding`) and ignores the `Authorization` header. There is no `Cache-Control: private/no-store` from the origin.

Consequence: as soon as any logged-in Kiwi user's wishlist UI calls this URL, their private wishlist data lands in the shared cache and is served **to any client — including fully unauthenticated attackers** — until the cached entry ages out (in testing the age counter kept growing past 640 seconds, i.e. >10 minutes, while serving victim data to unauthenticated polls).

# Steps to Reproduce

1. **Victim (authenticated) request** — any logged-in Kiwi user (wishlist widget fires this automatically):

   ```
   GET https://api.skypicker.com/umbrella/wishlist/bucket_names
   Authorization: Bearer <victim JWT>
   ```

   Response (privacy-sensitive, user-specific):

   ```json
   {"data":{"buckets":[
     {"wishlistId":"7814245b-48e0-49ce-85fa-74c441771f4f","name":"CROSS-EMAIL-TEST-9393","destinationLocationId":null,"itineraryCount":0},
     {"wishlistId":"7089cc36-c36f-45fd-905c-e14f11693c30","name":"MY-SECRET-TRIP-PLAN","destinationLocationId":null,"itineraryCount":0}
   ]},"status":"SUCCESS"}
   ```

   Response headers (note the shared-cache indicators):
   ```
   age: 646
   x-cache: MISS, HIT
   x-served-by: cache-qas-viag4720030-QAS
   via: 1.1 google, 1.1 varnish
   vary: Accept-Encoding
   ```

2. **Attacker (unauthenticated) request** — no cookie, no Authorization header, plain curl:

   ```
   GET https://api.skypicker.com/umbrella/wishlist/bucket_names
   ```

   Result: **HTTP 200** returning the **victim's wishlist data from the shared cache** (byte-identical body):

   ```
   HTTP/2 200
   age: 646
   x-cache: MISS, HIT
   ```

3. **Control (proves the authentication is otherwise real):** the same URL with a fresh cache-busting query parameter, unauthenticated, returns **401**:

   ```
   GET https://api.skypicker.com/umbrella/wishlist/bucket_names?nq=<random>
   -> HTTP/2 401  {"error":"Unauthorized"}
   ```

   So the endpoint *does* enforce auth — the leak is purely the shared-cache keying flaw (Authorization header not part of the cache key; no private cache-control).

4. Repeat unauthenticated polling: each poll returned 200 + victim data with increasing `age` (30s-, 60s-, 90s+ measurements; >640s sustained), zero `Set-Cookie`, no 401 interleave over consecutive polls.

# Attack Scenario

- An attacker runs a simple loop polling `https://api.skypicker.com/umbrella/wishlist/bucket_names`.
- Every time any active Kiwi user loads their wishlist (bucket names are fetched by the standard wishlist UI), that user's private wishlist names + IDs are served to the attacker from the shared cache.
- Impact: unauthenticated harvesting of arbitrary logged-in users' private saved-trip wishlists. No victim action beyond normal usage.

# Impact

Unauthenticated exposure of any active Kiwi user's private wishlist data (trip names e.g. `MY-SECRET-TRIP-PLAN`, wishlist UUIDs) via a shared-cache keying flaw on an authenticated endpoint. Reproducible, cross-user, and exploitable by an unauthenticated attacker with no chaining required.

# Remediation (suggestion)

- Emit `Cache-Control: private, no-store` (or `no-cache`) on all authenticated, user-specific umbrella endpoints.
- Include the `Authorization` (identity) value in the cache key at the edge, or bypass the cache for these endpoints.
- Ideally: do not cache user-specific responses in shared/edge caches at all.

# Evidence

Files captured during testing (epoch 1788151603+, 2026-08-31):
- `final_authed.h`  — victim seed request headers (200, `x-cache: MISS, HIT`)
- `final_authed.json`/`final_unauthed.json` — byte-identical victim body served unauthenticated
- `final_unauthed.h` — unauthenticated poll headers (200, `x-cache: MISS, HIT`, age 646)
- `ctrl_fresh.h/.json` — cache-busted unauthenticated control → 401