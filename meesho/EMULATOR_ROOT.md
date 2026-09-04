# Rooted Android Emulator — Setup & Usage (Real Device Root ka Alternative)

**Date:** 2026-09-02
**Purpose:** Realme C11 (RMX2185) real root BLOCKED tha (DeepTest unsupported / MTKClient BROM-HID / fastboot flaky). Emulator iska **working alternative** hai — root access milta hai, `/data/data` readable, aur PC par chalta hai.

---

## ✅ STATUS: ROOTED EMULATOR WORKING

| Item | Value |
|---|---|
| AVD name | `root_test` |
| System image | `system-images;android-30;default;x86_64` (Android 11) |
| Emulator | `~/Android/Sdk/emulator/emulator` |
| Root access | **YES** — `adb root` → `uid=0(root)` |
| `/data/data` | **READABLE** ✅ (locked device par impossible) |
| Config | 1.5GB RAM / 2 cores / 720x1280 / swiftshader (light — PC slow nahi) |

---

## LAUNCH (emulator boot)

```bash
export ANDROID_HOME=~/Android/Sdk
export PATH="$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH"

# KVM ke saath headless launch (no window, light)
sg kvm -c 'nohup $ANDROID_HOME/emulator/emulator -avd root_test \
  -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect \
  > /tmp/emu_boot.log 2>&1 &'
```

Boot ~30-60s (KVM). Confirm:
```bash
adb wait-for-device
adb shell getprop sys.boot_completed   # jab '1' aaye, ready
```

## ROOT ACCESS (working)

```bash
adb root                    # root shell
adb wait-for-device
adb shell id                # → uid=0(root) ✅
adb shell ls /data/data/    # app data readable
```

## REAL DEVICE vs EMULATOR — comparing

| Aap ka Realme C11 target | Emulator equivalent |
|---|---|
| Root via Magisk | `adb root` (built-in, no Magisk needed) |
| `/data/data/com.meesho.supply` read | **Same — emulator par readable** |
| Meesho APK install | `adb install app.apk` |
| Token extraction | `adb pull /data/data/<pkg>/...` |
| Traffic intercept | `adb reverse tcp:8082 tcp:8082` + proxy |

---

## OLD REAL-DEVICE STATE (backup — abhi safest)

Real device vivaad kabhi revived karna ho to `meesho_root_report.md` section 10 ke 3 paths follow karo. But **/tmp artifacts reed wipe ho gaye** (reboot) — naya stock backup dubaara dump karna padega. Emulator behtar hai is samay.

---

## Commands quick-ref

```bash
# install apk
adb install -r /path/app.apk

# pull app data (root wala proof)
adb shell su root ls /data/data/com.meesho.supply/
adb pull /data/data/com.meesho.supply/shared_prefs/ /tmp/meesho_prefs/

# traffic via burp
adb shell settings put global http_proxy 10.0.2.2:8080
# (burp listener 8080; 10.0.2.2 = host loopback)
```

## Note
- `su -c` emulator mein kaam nahi karta → hamesha `adb root`/`adb shell su root <cmd>` use karo
- Host RAM: emulator ~1.5GB leta hai → baaki ~3GB host ke liye (PC slow nahi)
- AVD khali image hai (Google services nahi) → Meesho app login agar OTP SMS ho to whitelist/GApps nai hai, test sirf signed-in session/intercept pe depend karega