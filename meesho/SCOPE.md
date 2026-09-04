# Meesho — SCOPE

> In program ka target, in/out-of-scope, aur rules. Har hunting session se pehle ye padho.
> Ye file meesho/ k file-specific scope track karti hai. HackerOne platform scope ke liye
> `hackerone_get_program` + `hackerone_get_program_scope` + `hackerone_get_program_scope_exclusions` use karo.

## Program handle
- HackerOne: `meesho_bbp` ✅ confirmed

## Assets (IN-SCOPE — bounty eligible)

| Asset | Type | Max Severity | Scope ID |
|---|---|---|---|
| www.meesho.com | URL | critical | 876367 |
| com.meesho.supply | Android APK | critical | 876369 |
| 1457958492 | iOS App | critical | 876370 |
| admin.meeshosupply.com | URL | critical | 876371 |
| supplier.meesho.com | URL | critical | 876372 |
| affiliate.meesho.com | URL | critical | 943910 |
| prod.meeshoapi.com | API | critical | 944090 |
| www.valmo.in | URL (logistics) | critical | 948052 |
| com.valmo.valmo | Android (Valmo) | critical | 948053 |
| superstoreapp.meesho.com | URL (grocery) | high | 990609 |

## Assets (OUT-OF-SCOPE — NEVER test)

| Asset | Type |
|---|---|
| grocery-supplier.meesho.com | URL |
| farmiso.meeshosupply.com | URL |
| affiliate-c.meesho.com | URL |
| warehouse.meesho.com | URL |
| agency.meesho.com | URL |
| atlas.valmo.in | URL |
| *.meeshogcp.in | WILDCARD |
| *.meeshoaiservices.ai | WILDCARD |
| *.meeshosupply.com | WILDCARD (barring admin.meeshosupply.com) |
| *.meeshoapi.com | WILDCARD (barring prod.meeshoapi.com) |
| admin.meesho.io | URL |
| Rider app | App |
| com.valmo.ops | App |

## Test Credentials (from policy)
- **Supplier Panel:** `suppliertest-1@meeshoai.com` / `suppliertest-2@meeshoai.com`, pw `Hackerone@123$`
- **Consumer mobiles:** `6666666661`, `6666666662` — OTP: `999999`

## Rules / notes
- Grocery/Superstore: update PIN code to Nagpur (440002) to see section
- Cancel Superstore/Grocery orders within 30 min (account lock risk)
- Phone numbers: use Indian numbers only (for OTP)

---
_Last updated: 2026-09-02_
