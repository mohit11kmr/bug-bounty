# TriagePilot — Privacy Policy

**Version:** 1.0.0
**Last updated:** <DATE — fill in when you publish>

---

## 1. Kya data collect hota hai

| Data | Kaha store hota hai | Kyu chahiye |
|---|---|---|
| Email | TriagePilot ke account-server par (hashed password ke saath) | Login/account identify karne ke liye |
| Password | **Kabhi plaintext nahi** — PBKDF2-HMAC-SHA256 (100,000 iterations) + per-user random salt se hash, sirf hash+salt store hota hai | Security |
| Scan-usage-count (kitne scans, kis din) | Account-server par | Daily-limit/trial enforce karne ke liye |
| HackerOne credentials (username, API-token) | **Sirf tumhari apni machine par** (`.env.h1` file), **kabhi TriagePilot ke server par nahi jaata** | Ye tumhara apna, bring-your-own-key hai |
| Scan-results/findings (URLs, vulnerabilities) | **Sirf tumhari apni machine par** (local `recon.db`), **kabhi cloud par nahi jaata** (jab tak future mein opt-in cloud-sync feature na add ho, jo iss policy ko update karke clearly bataya jayega) | Recon-data tumhara apna kaam hai |

## 2. Data Kaise Secure Hai

- Passwords kabhi plaintext store/log nahi hote.
- Har login-session ka token 30 din baad automatically expire ho jaata hai.
- Brute-force protection: baar-baar galat password try karne par temporary
  lockout (5 attempts / 5 minute).
- Account-server tumhari apni instance ho sakta hai ya operator-hosted — dono
  case mein same security-practices lagu hoti hain.

## 3. Data Kisi Aur Ko Nahi Diya Jaata

TriagePilot tumhara data kisi third-party ko **bechta nahi, share nahi
karta**. Sirf operator (jo service chalata hai) ke paas account/usage-data
hota hai, sirf service chalane ke liye.

## 4. Tumhare Rights

- **Account delete karne ka request** kabhi bhi kar sakte ho — sabhi data
  (email, password-hash, usage-history) permanently delete kar diya jaayega.
- **Apna data dekhne ka request** kar sakte ho (kya stored hai).

## 5. Cookies/Tracking

TriagePilot ek CLI-tool hai, koi web-tracking/cookies/analytics nahi hai is
version mein.

## 6. Changes to This Policy

Badi change (jaise cloud-data-sync feature add hona) hone par ye document
update hoga aur existing users ko inform kiya jayega.

## 7. Contact

Privacy se related kisi bhi sawaal ke liye: **mohitsikarwar123@gmail.com**
