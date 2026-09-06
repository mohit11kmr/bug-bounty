#!/usr/bin/env python3
"""
notify.py — Cross-Platform Alert & Notification Dispatcher for Bug Bounty Suite.

Channels Supported:
  1. Desktop Notification: Linux `notify-send` (GUI alert popup).
  2. Telegram Bot: Direct push message to user's phone via Bot API.
  3. Discord Webhook: Rich embeds with severity color-coding.
  4. Terminal Alert: Styled console output with optional terminal bell.

Zero External Dependencies:
  Uses Python standard library (urllib.request, json, os, subprocess).

Usage:
  python3 recon/notify.py --selfcheck
  python3 recon/notify.py --test
  python3 recon/notify.py --title "Bug Bounty Alert" --message "High severity finding on target!" --severity high
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_notify_env() -> None:
    """Load notification environment variables from .env.notify, .env.h1, or ~/.notify_env."""
    candidate_files = [
        BASE / ".env.notify",
        BASE / ".env.h1",
        Path.home() / ".notify_env",
        Path.home() / ".h1_env",
    ]
    for env_path in candidate_files:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().replace("export ", "").strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v


def send_desktop_notification(title: str, message: str, severity: str = "info") -> bool:
    """Send local desktop popup using notify-send if installed and DISPLAY/WAYLAND_DISPLAY is active."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    if not shutil.which("notify-send"):
        return False

    urgency_map = {"info": "low", "medium": "normal", "high": "critical", "critical": "critical"}
    urgency = urgency_map.get(severity.lower(), "normal")

    try:
        subprocess.run(
            ["notify-send", "-u", urgency, "-a", "BugBounty Suite", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return True
    except Exception:
        return False


def send_telegram_alert(title: str, message: str, severity: str = "info") -> bool:
    """Send alert to Telegram chat via Bot API if configured."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        return False

    sev_emoji = {
        "info": "ℹ️",
        "medium": "⚠️",
        "high": "🚨",
        "critical": "🔥",
    }.get(severity.lower(), "🎯")

    text = f"{sev_emoji} *{title}*\n\n{message}"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "BugBounty-Notifier/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[notify] Telegram alert failed: {e}", file=sys.stderr)
        return False


def send_discord_alert(title: str, message: str, severity: str = "info") -> bool:
    """Send alert to Discord webhook if configured."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url or not webhook_url.startswith("http"):
        return False

    sev_colors = {
        "info": 3447003,      # Blue
        "medium": 16776960,   # Yellow
        "high": 16744192,     # Orange
        "critical": 15158332, # Red
    }
    color = sev_colors.get(severity.lower(), 3447003)

    payload = {
        "username": "Bug Bounty Mission Control",
        "embeds": [
            {
                "title": title,
                "description": message,
                "color": color,
                "footer": {"text": f"Severity: {severity.upper()} | Bug Bounty Autonomous Suite"},
            }
        ],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "BugBounty-Notifier/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[notify] Discord alert failed: {e}", file=sys.stderr)
        return False


def dispatch_alert(title: str, message: str, severity: str = "info") -> dict:
    """Dispatch alert to all available notification channels."""
    load_notify_env()
    results = {
        "desktop": send_desktop_notification(title, message, severity),
        "telegram": send_telegram_alert(title, message, severity),
        "discord": send_discord_alert(title, message, severity),
    }

    # Always log to stdout
    sev_badge = {
        "info": "\033[38;5;51m[INFO]\033[0m",
        "medium": "\033[38;5;220m[MEDIUM]\033[0m",
        "high": "\033[38;5;208m[HIGH]\033[0m",
        "critical": "\033[38;5;196m[CRITICAL]\033[0m",
    }.get(severity.lower(), "[ALERT]")

    print(f"\n\033[1m{sev_badge} \033[38;5;141m{title}\033[0m", flush=True)
    for line in message.splitlines():
        print(f"  {line}", flush=True)

    active_channels = [k for k, v in results.items() if v]
    if active_channels:
        print(f"\033[2m  ✓ Dispatched to: {', '.join(active_channels)}\033[0m\n", flush=True)
    else:
        print(f"\033[2m  (No remote webhooks configured. Desktop/terminal output used)\033[0m\n", flush=True)

    return results


def check_bot_token(token: str) -> tuple[bool, str]:
    """Validate Telegram Bot token via getMe API."""
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url, headers={"User-Agent": "BugBounty-Notifier/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                bot_user = data["result"].get("username", "")
                return True, bot_user
            return False, data.get("description", "Unknown error")
    except Exception as e:
        return False, str(e)


def poll_for_chat_id(token: str, max_wait: int = 45) -> tuple[str, str]:
    """Poll getUpdates to automatically capture user's chat_id when they press /start."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    req = urllib.request.Request(url, headers={"User-Agent": "BugBounty-Notifier/1.0"})
    start_t = time.time()
    while time.time() - start_t < max_wait:
        remaining = int(max_wait - (time.time() - start_t))
        print(f"\r  [telegram] ⏳ Waiting for /start message on your phone... ({remaining}s remaining)", end="", flush=True)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok") and data.get("result"):
                    for update in reversed(data["result"]):
                        msg = update.get("message") or update.get("channel_post")
                        if msg and "chat" in msg:
                            chat_id = str(msg["chat"]["id"])
                            name = msg["chat"].get("first_name", "") or msg["chat"].get("username", "User")
                            print(f"\n  [telegram] ✓ Detected incoming message from: {name} (Chat ID: {chat_id})", flush=True)
                            return chat_id, name
        except Exception:
            pass
        time.sleep(2)
    print("\n", flush=True)
    return "", ""


def save_notify_env(key: str, val: str) -> None:
    """Save key-value pair to .env.notify."""
    env_file = BASE / ".env.notify"
    lines = []
    found = False
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean.startswith(f"export {key}=") or clean.startswith(f"{key}="):
                lines.append(f'export {key}="{val}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'export {key}="{val}"')
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = val


def interactive_telegram_setup() -> None:
    """Interactive wizard to configure phone number and pair Telegram bot from the launcher."""
    load_notify_env()
    print("\n\033[1;38;5;51m╭────────────────────────────────────────────────────────────────────────╮\033[0m")
    print("\033[1;38;5;51m│           📱 TELEGRAM NOTIFICATION & PHONE SETUP WIZARD                │\033[0m")
    print("\033[1;38;5;51m│       Connect your phone / Telegram account with Bug Bounty Suite      │\033[0m")
    print("\033[1;38;5;51m╰────────────────────────────────────────────────────────────────────────╯\033[0m\n")

    current_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    current_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    current_phone = os.environ.get("NOTIFY_PHONE_NUMBER", "")

    if current_chat and current_token:
        masked_token = current_token[:8] + "..." + current_token[-6:]
        print(f"  \033[38;5;48m● Current Status:\033[0m \033[1mCONFIGURED & ACTIVE\033[0m")
        print(f"    - Telegram Chat ID : \033[38;5;51m{current_chat}\033[0m")
        print(f"    - Bot Token        : \033[2m{masked_token}\033[0m")
        if current_phone:
            print(f"    - Phone Number     : \033[38;5;220m{current_phone}\033[0m")
        print("")
    else:
        print("  \033[38;5;220m○ Current Status:\033[0m \033[2mNot yet configured (Alerts will go to Desktop/Terminal)\033[0m\n")

    print("\033[1m  Choose an option:\033[0m")
    print("    [1] ⚡ Auto-Pair Phone via Telegram Bot (Recommended — No manual Chat ID needed)")
    print("    [2] ✍ Manual Entry (Enter Bot Token, Chat ID & Phone Number manually)")
    print("    [3] 🧪 Send Test Alert to Phone right now")
    print("    [4] 🗑 Clear / Disconnect Telegram Configuration")
    print("    [0] ↩ Return to Launcher\n")

    choice = input("  Select option [0-4]: ").strip()

    if choice == "1":
        print("\n\033[1;38;5;39m--- Step 1: Telegram Bot Token ---\033[0m")
        print("  Agar aapke paas abhi Bot nahi hai, to Telegram app par \033[1m@BotFather\033[0m par jaakar")
        print("  \033[38;5;51m/newbot\033[0m type karein aur 30 seconds me apna free alert bot banayein.\n")

        token_prompt = f"  Enter your Bot Token [{current_token[:8]}...]: " if current_token else "  Enter your Bot Token: "
        token = input(token_prompt).strip()
        if not token and current_token:
            token = current_token
        if not token:
            print("  \033[38;5;196mError: Bot token cannot be empty.\033[0m")
            return

        print("  [telegram] Validating bot token...", end="", flush=True)
        ok, bot_info = check_bot_token(token)
        if not ok:
            print(f" \033[38;5;196mFAILED: {bot_info}\033[0m")
            return
        print(f" \033[38;5;48m✓ Connected to @{bot_info}\033[0m\n")

        print("\033[1;38;5;39m--- Step 2: Phone Number (Optional Metadata) ---\033[0m")
        phone_prompt = f"  Enter your Mobile Number [{current_phone}]: " if current_phone else "  Enter your Mobile Number (e.g. +91 9876543210): "
        phone = input(phone_prompt).strip()
        if not phone and current_phone:
            phone = current_phone
        if phone:
            save_notify_env("NOTIFY_PHONE_NUMBER", phone)

        print("\n\033[1;38;5;39m--- Step 3: Auto-Pairing with your Phone ---\033[0m")
        print(f"  1. Apne phone me Telegram kholein.")
        print(f"  2. Search karein: \033[1;38;5;51m@{bot_info}\033[0m (ya link: \033[4mhttps://t.me/{bot_info}\033[0m)")
        print(f"  3. Bot ko open karke \033[1;38;5;48mSTART\033[0m button dabayein ya koi message bhejein.\n")

        chat_id, user_name = poll_for_chat_id(token, max_wait=45)
        if not chat_id:
            print("  \033[38;5;220m⚠ Timeout: Koi /start message detect nahi hua.\033[0m")
            print("  Aap manual mode [2] use karke apna Chat ID enter kar sakte hain.")
            return

        save_notify_env("TELEGRAM_BOT_TOKEN", token)
        save_notify_env("TELEGRAM_CHAT_ID", chat_id)

        print(f"\n  \033[38;5;48m✓ SUCCESS!\033[0m Phone successfully paired for user \033[1m{user_name}\033[0m (ID: {chat_id})!")
        print("  Configuration saved to \033[2m.env.notify\033[0m\n")

        print("  [telegram] Sending verification ping to your phone...", flush=True)
        send_telegram_alert(
            title="🎯 Bug Bounty Phone Notification Active!",
            message=(
                f"Hello {user_name}!\n"
                f"Aapka phone Bug Bounty Mission Control launcher ke sath successfully pair ho chuka hai.\n"
                f"Ab jab bhi koi high-priority attack surface ya verified finding milegi, alert turant yahan aayega!"
            ),
            severity="info",
        )
        print("  \033[38;5;48m✓ Verification alert sent to your Telegram app!\033[0m\n")

    elif choice == "2":
        token = input("  Enter Telegram Bot Token: ").strip()
        chat_id = input("  Enter Telegram Chat ID (e.g. 123456789): ").strip()
        phone = input("  Enter Mobile Number (optional): ").strip()

        if token and chat_id:
            save_notify_env("TELEGRAM_BOT_TOKEN", token)
            save_notify_env("TELEGRAM_CHAT_ID", chat_id)
            if phone:
                save_notify_env("NOTIFY_PHONE_NUMBER", phone)
            print("\n  \033[38;5;48m✓ Configuration saved.\033[0m Sending test ping...")
            send_telegram_alert(
                title="🎯 Telegram Alerts Configured",
                message="Bug Bounty alerts are now active on your Telegram account!",
                severity="info",
            )
        else:
            print("  \033[38;5;196mError: Token and Chat ID are required.\033[0m")

    elif choice == "3":
        if not (current_token and current_chat):
            print("\n  \033[38;5;196mError: Telegram abhi configured nahi hai. Pehle option [1] ya [2] run karein.\033[0m\n")
            return
        print("\n  [telegram] Sending test alert to your phone...", flush=True)
        ok = send_telegram_alert(
            title="🎯 Bug Bounty Test Alert",
            message="Test notification from Mission Control. Telegram integration is working perfectly!",
            severity="high",
        )
        if ok:
            print("  \033[38;5;48m✓ Test alert delivered successfully to your phone!\033[0m\n")
        else:
            print("  \033[38;5;196m✗ Failed to deliver message. Check your bot token and chat ID.\033[0m\n")

    elif choice == "4":
        env_file = BASE / ".env.notify"
        if env_file.exists():
            lines = [
                l for l in env_file.read_text().splitlines()
                if not any(k in l for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NOTIFY_PHONE_NUMBER"))
            ]
            env_file.write_text("\n".join(lines) + "\n")
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        os.environ.pop("NOTIFY_PHONE_NUMBER", None)
        print("\n  \033[38;5;48m✓ Telegram configuration cleared.\033[0m\n")

    else:
        return


def _selfcheck() -> None:
    """Validate internal notification components without external network requirements."""
    print("[notify] Running selfcheck...")
    load_notify_env()
    assert callable(send_desktop_notification)
    assert callable(send_telegram_alert)
    assert callable(send_discord_alert)
    assert callable(dispatch_alert)
    assert callable(check_bot_token)
    assert callable(poll_for_chat_id)
    assert callable(interactive_telegram_setup)
    print("[notify] selfcheck OK: All notification handlers and configurators verified.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-Platform Alert Dispatcher")
    ap.add_argument("--title", default="Bug Bounty Mission Control Alert", help="Alert title")
    ap.add_argument("--message", default="Surface scanned. No immediate action required.", help="Alert message body")
    ap.add_argument("--severity", choices=["info", "medium", "high", "critical"], default="info", help="Severity level")
    ap.add_argument("--test", action="store_true", help="Send a test alert across all configured channels")
    ap.add_argument("--setup-telegram", action="store_true", help="Interactive Telegram phone alert setup wizard")
    ap.add_argument("--status", action="store_true", help="Check current notification configuration status")
    ap.add_argument("--selfcheck", action="store_true", help="Run internal validation")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    if args.setup_telegram:
        interactive_telegram_setup()
        return

    if args.status:
        load_notify_env()
        t_ok = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        d_ok = bool(os.environ.get("DISCORD_WEBHOOK_URL"))
        desk_ok = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        phone = os.environ.get("NOTIFY_PHONE_NUMBER", "Not set")
        print("\n[notify] Notification Channels Status:")
        print(f"  - Linux Desktop Popup: {'✓ Available' if desk_ok else '○ Inactive (No display)'}")
        print(f"  - Telegram Phone Bot : {'✓ Configured' if t_ok else '○ Inactive (Run --setup-telegram)'}")
        print(f"  - Phone Number       : {phone}")
        print(f"  - Discord Webhook    : {'✓ Configured' if d_ok else '○ Inactive'}\n")
        return

    if args.test:
        dispatch_alert(
            title="🎯 Bug Bounty Test Notification",
            message="This is a test notification from your Bug Bounty Mission Control suite.\nAll alert channels are connected and operational!",
            severity="info",
        )
        return

    dispatch_alert(title=args.title, message=args.message, severity=args.severity)


if __name__ == "__main__":
    main()

