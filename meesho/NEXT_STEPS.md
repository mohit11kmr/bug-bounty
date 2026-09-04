# MEESHO — NEXT STEPS (Handoff for opencode agent)

> Ye file `meesho/` folder ke opencode session ke liye hai. Agent: ISKO PEHLE PADHO,
> phir neeche diye "IMMEDIATE TASKS" ko priority order mein karo.

---

## CONTEXT (abhi kya hai)

1. **Real device root BLOCKED** — `meesho_root_report.md` padho (Realme C11, 3 blockers: DeepTest unsupported, MTKClient BROM-HID fail, fastboot flaky). Device stock & safe, par `/tmp` artifacts ab delete ho chuke (reboot). Real-device root se aage nahi badhna abhi.

2. **ROOTED EMULATOR RUNNING** — `EMULATOR_ROOT.md` padho. AVD `root_test` (Android 11, x86_64) root access de raha hai:
   - `adb root` → `uid=0(root)` ✅
   - `/data/data/` readable ✅
   - Emulator running: `emulator-5554`
   - Host PC light hai (emulator 1.5GB RAM / 2 cores, swiftshader)

3. **HackerOne program confirmed** — `meesho_bbp` handle ✅
   - 10 in-scope assets (critical: www.meesho.com, com.meesho.supply, supplier, admin, affiliate, API, Valmo, Grocery)
   - Test creds available: Supplier Panel (`suppliertest-1/2@meeshoai.com` pw `Hackerone@123$`), Consumer mobiles (`6666666661/62` OTP `999999`)

4. **BLOCKER — Meesho APK source:** No APK found in `/tmp`, `/home`, or workspace. Emulator is running but cannot test without the app installed.

5. **Goal (original bounty):** Meesho `Xo` auth token + session files extract karo, phir 17 confirmed prod2 IDOR routes + `download-invoice` test karo (order/address/products). Full detail `meesho_root_report.md` section: 1 (why root) + 10 (next course).

---

## IMMEDIATE TASKS (priority order)

### ✅ 1. Emulator alive check — DONE
Emulator `emulator-5554` running with root access (`uid=0(root)`).

### ✅ 2. HackerOne program confirmed — DONE
Handle: `meesho_bbp`. Scope confirmed. Weaknesses list available.

### 🚨 3. BLOCKER: Meesho APK source
- Agar APK available hai (device ka extract, Play Store download via mirror, ya `app-meesho-supply...apk`) → `adb -s emulator-5554 install -r <apk>`
- **USER: Please provide the Meesho APK file path or download source**
- Agar APK nahi hai → isko **BLOCKER** mark karo, aage mat badho.

### 4. APK install hone par — app launch + sign-in attempt
- Meesho app emulator par install + open karo
- Login (OTP) ho to sign-in karo; ya direct launcher + token check
- `adb -s emulator-5554 shell dumpsys package com.meesho.supply` → confirm installed

### 5. Token extraction (root)
- Jaise hi app sign-in/session active ho:
```bash
adb -s emulator-5554 root
adb -s emulator-5554 pull /data/data/com.meesho.supply/shared_prefs/ /tmp/meesho_prefs/
adb -s emulator-5554 pull /data/data/com.meesho.supply/databases/ /tmp/meesho_db/
```
- `Xo` token (auth) shared_prefs/databases/meesho ke kisi member files mein hoga. Pakdo → save `/tmp/meesho_prefs/` mein.
- **Security:** token ko report/notes mein plaintext mat likho — reference file/encrypted hi.

### 6. Burp intercept setup (IDOR routes ke liye)
```bash
adb -s emulator-5554 shell settings put global http_proxy 10.0.2.2:8080
```
- Burp at 8082 hai to `reverse` vibhag: `adb reverse tcp:8080 tcp:8082` + proxy 10.0.2.2:8080
- 17 prod2 routes (order/address/products/download-invoice) ke requests capture + tamper karke test karo

### 7. IDOR testing (awaiting token)
- Token milne par, har route par: apni resource ki ka **aapke ID** se khule, fir **dusre user/random ID** daal ke access check.
- Har route ka result `meesho/NOTES.md` session log mein add karo.

### 8. Report drafting (ho jaye finding)
- Finding clear ho to `hackerone_*` MCP se submit (if-in-scope + no duplicate + impact). Second opinion chaho to `claude-reviewer` task ko bhejo pehle.

---

## RULES (ye area meesho program hai)
- SIRF in-scope Meesho assets — `SCOPE.md` padho
- Token/credentials kisi log/chat mein plaintext nahi
- Emulator par jo karo authorized testing ke liye hi
- `sqlmap`/destructive never; manual/proxy se hi

---

## BLOCKERS
- ❌ **Meesho APK source not found** — User ko confirm karna hai kahan se milega
- ⚠️ Emulator crash (RAM tight) — retry light flags
- ⚠️ Login OTP SMS — emulator mein SMS nahi aayega (Google services nahi) → alternate auth ya confirm

Ye hi ab tak ka context. Aage isi se kaam chalao. Final status `meesho/NOTES.md` mein daalna.
