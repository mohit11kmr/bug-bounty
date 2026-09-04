# MEESHO BUG BOUNTY — Realme RMX2185 ROOT ATTEMPT REPORT

**Date:** 2026-08-31
**Operator:** mohit11kmr
**Device:** Realme C11 (RMX2185), Android 10, MediaTek Helio P35 (MT6765)
**Objective:** Root phone → extract valid Meesho `Xo` auth token → run authenticated IDOR tests on 17 prod2 routes + `download-invoice` → submit bounty-eligible report (50-50 split)

---

## 1. WHY ROOT IS NEEDED (CONTEXT)

- Meesho BBP in-scope. Rewards: Low $100-500, Medium $500-1000, High $1000-2500, Critical $2500-3500.
- Grocery/shopping web auth reads `?xo=<token>` + `?app-user-id=<id>` from URL → headers `Xo` + `APP-USER-ID`.
- **Goal = extract valid `Xo` session token from `/data/data/com.meesho.supply`** (databases/ + shared_prefs/).
- This requires **root** (unprivileged ADB cannot read another app's private `/data/data` dir on a locked bootloader device).
- Device selected: **Realme RMX2185 (C11)** — MTK Helio P35, **no Knox**, root-safe (unlike Samsung A04e which has Knox = permanent 0x1 + warranty void).

---

## 2. DEVICE VERIFICATION (DONE ✅)

| Property | Value |
|---|---|
| Model | RMX2185 (Realme C11) |
| Android | 10 (Realme UI 1.0) |
| SoC | MT6765 (Helio P35) |
| FW | RMX2185_11_A.109 |
| Bootloader | Locked |
| `sys.oem_unlock_allowed` | **1** ✅ (OEM unlock permitted) |
| `ro.oem_unlock_supported` | **1** ✅ |
| `com.realme.securitycheck` | present |
| Battery at last check | 65% |

---

## 3. TOOLS INSTALLED & VERIFIED (DONE ✅)

| Tool | Path | Status |
|---|---|---|
| platform-tools (adb/fastboot) | `/tmp/platform-tools/` (fastboot 37.0.1) | ✅ |
| Magisk v30.7 | `/tmp/Magisk-v30.7.apk` | ✅ |
| magiskboot | `/tmp/magiskboot` | ✅ |
| MTKClient v2.1.4 | `/tmp/mtkvenv/bin/mtk` (cloned `/tmp/mtkclient`) | ✅ MT6765 supported (`dacode=0x6765`, oppo6765 preloader) |
| udev rules | `/etc/udev/rules.d/70-android.rules` (`22d9`+`0e8d` → MODE 0666 GROUP plugdev) | ✅ |

---

## 4. STEP 1 — STOCK BACKUP (DONE ✅)

`mtk r boot,vbmeta` while device in **DA mode (`0e8d:0003`)**:
- ✅ `/tmp/stock_boot.img` (33,554,432 bytes / 33.5MB, valid Android bootimg) — **STOCK BACKUP (safe restore point)**
- ✅ `/tmp/stock_vbmeta.img` (12,582,912 bytes / 12.5MB)
- Worked because device enumerate as `0e8d:0003` (DA). VERIFIED non-destructive read.

---

## 5. STEP 3 — MAGISK PATCH (DONE ✅)

- Magisk v30.7 installed on phone (`com.topjohnwu.magisk`).
- User patched stock boot via Magisk app → `/sdcard/Download/magisk_patched-30700_gk9RJ.img`.
- Pulled to `/tmp/boot.patched` (33,554,432 bytes, **valid bootimg** — patched boot ready).
- `/tmp/vbmeta.empty` created (zeroed 12.5MB, AVB/verity disabled) — ready.

**➡ At this point: patched boot + empty vbmeta are FLASH-READY, but never flashed.**

---

## 6. STEP 4 — BOOTLOADER UNLOCK (IN PROGRESS → BLOCKED)

### 6A. MTKClient BROM unlock — FAILED
- Device reliably reaches BROM (`0e8d:20ff`) / preloader (`0e8d:2001`).
- `mtk da seccfg unlock`, `mtk printgpt` → **loop "Port - Hint"** forever (both as user and `sudo`).
- **Root cause found:** `0e8d:20ff` BROM enumerates as a **USB HID device (`hidraw0`)**, NOT a serial/COM port. mtkclient keeps searching for a serial port (`/dev/ttyACM*`, none present).
- Force via `--vid 0e8d --pid 0x20ff --mode brom` → still serial-search loop.
- pyusb **CAN see** `0xe8d 0x20ff realme` (device visible), libusb present — but mtkclient's BROM→DA bootstrap handshake does not complete in this HID state.
- Kernel: `usb 2-2: device descriptor read/64, error -71` (-71 EPROTO) / `-110` (ETIMEDOUT) during attempts.
- **Verdict:** MTKClient BROM path unreliable on this PC/device combination.

### 6B. Fastboot unlock approach — NOT REACHABLE
- `sys.oem_unlock_allowed=1` verified via adb.
- `adb reboot bootloader` → device drops off USB, fastboot **never enumerates** (`18d1:d001` never appears). Device returns to OS/neutral (`22d9:2046` / `22d9:2765`).
- Fastboot detection flaky on this device/build.

### 6C. DeepTest official unlock — BLOCKED BY REALME (❌ CLOSED)
- Downloaded official `DeepTest_realmeC11.apk` from `download.c.realme.com` (official link from realme Community post 1365228796868915200).
- **APK VERIFIED LEGIT ⭐:**
  - Package: `com.coloros.deeptesting` (ColorOS Deep Test — official realme/OPPO unlock app)
  - Signing cert: `realme AndroidTeam, realme.com` (Owner/Issuer confirm realme) — official, not a scam
  - SHA256: `b18a315113d48cda4c1e98e74f81146b7294ecdc5259cdd5719e282982804557`
- Installed on device successfully (sideload, after `settings put global package_verifier_enable 0` + user consent — note: `adb install --no-verify` and `-g` were rejected by this Android-10/Oppo `pm` build).
- **RESULT:** App launched → **"this phone model does not support in depth test"**.
- **Verdict:** Official DeepTest path is **blocked/not supported for RMX2185** on realme servers (consistent with XDA reports that DeepTest no longer unlocks for this model).

---

## 7. CURRENT DEVICE STATE (VERIFIED SAFE ✅)

- **NOT BRICKED.** Only non-destructive READ operations were done (stock boot dump for backup).
- **Nothing was ever flashed** — boot/vbmeta remain 100% stock & untouched on device.
- Device currently: **OS + ADB connected** (`22d9:2765`, serial `QCO7MNR8LF4LFABU`), battery ~65%.
- Data on phone not wiped (DeepTest never got far enough to wipe).

---

## 8. ARTIFACTS (ALL PRESERVED IN /tmp)

| Artifact | Path | Size | Purpose |
|---|---|---|---|
| Stock boot backup | `/tmp/stock_boot.img` | 33.5MB | Safe restore / TM magisk patch source |
| Stock vbmeta backup | `/tmp/stock_vbmeta.img` | 12.5MB | Safe restore |
| Magisk-patched boot | `/tmp/boot.patched` | 33.5MB | Root boot (FLASH-READY) |
| Empty vbmeta | `/tmp/vbmeta.empty` | 12.5MB | Disable AVB/verity (FLASH-READY) |
| DeepTest APK | `/tmp/DeepTest_realmeC11.apk` | 3.1MB | Official (blocked on this model) |
| Magisk APK | `/tmp/Magisk-v30.7.apk` | 11.6MB | Root manager |
| MTKClient | `/tmp/mtkvenv/bin/mtk` | — | MTK unlock tool |
| platform-tools | `/tmp/platform-tools/` | — | adb/fastboot 37 |
| Root runbook | `/tmp/meesho_root_runbook.md` | — | A-to-Z verified procedure |
| LESSONS knowledge base | `~/.config/opencode/skills/bug-bounty/LESSONS.md` | 138 lines | Improvement-policy lessons |

---

## 9. BLOCKERS SUMMARY

1. **Official DeepTest:** blocked for RMX2185 (model not supported).
2. **MTKClient BROM:** `0e8d:20ff` BROM enumerates as USB-HID, not serial → mtkclient "Port - Hint" handshake never completes.
3. **Fastboot:** `adb reboot bootloader` does not produce a reachable fastboot interface; device returns to OS.

---

## 10. NEXT COURSE OF ACTION (FOR CONTINUATION VIA CLAUDE/OTHER AGENT)

Device is **stock & safe** — any continuation can resume from here.

### Recommended paths (priority order):
1. **Physical fastboot entry:** Power OFF → **Vol-Down + Vol-Up + Power** (or Vol-Down + Power) → connect USB at Realme logo. This may enter **recovery** — choose **"Reboot to bootloader"**. Watch for fastboot PID `18d1:d001`. Once present: `fastboot flashing unlock` → confirm Vol-Up → then:
   ```
   fastboot flash boot /tmp/boot.patched
   fastboot flash vbmeta /tmp/vbmeta.empty
   fastboot reboot
   ```
   Then verify root with `adb shell su -c id` (expect uid=0).

2. **MTKClient deeper BROM fix:** resolve `0e8d:20ff` HID→serial: install proper `kamakiri`/BROM-tools stack, provide the exact `preloader_oppo6765` loader, get the BROM into a serial-enumerating "green state" (e.g. via `mtk payload` recovery of the DA-boot path that worked at `0e8d:0003`). Re-establish the DA mode (`0e8d:0003`) that previously connected successfully, then unlock+flash in that state.

3. **Alternate unlock**: research current (2026) working unlock for RMX2185 — DeepTest may be fully EOL; check XDA/4PDA for bootloader-unlock services or firmware-based unlock, or consider whether a different root-safe device is more tractable.

### Once root achieved:
Extract Meesho token from `/data/data/com.meesho.supply` (databases/ + shared_prefs/) → feed `Xo`/session into `order`, `address`, `products`, and `download-invoice` IDOR tests on the 17 confirmed prod2 routes.

---

## 11. HONEST ASSESSMENT

- A large portion of this session was consumed by **USB mode churn** (BROM `20ff` / DA `0003` / preloader `2001` / neutral `2046` / ADB `2765` / fastboot `18d1:d001`) and **tool flakiness** rather than forward progress on the actual unlock.
- The **official root route for RMX2185 is blocked** (DeepTest unsupported). MTKClient and fastboot are both in a degraded state on this PC/device combo.
- **No part of the Meesho bounty hunt (token extraction / IDOR) was completed.**
- Device remains safe and fully restorable from the stock backups.

---

*Report generated 2026-08-31 by mohit11kmr hunting session. Artifacts preserved in /tmp for continuation.*
