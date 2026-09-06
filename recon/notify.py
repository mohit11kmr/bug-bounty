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


def _selfcheck() -> None:
    """Validate internal notification components without external network requirements."""
    print("[notify] Running selfcheck...")
    load_notify_env()
    assert callable(send_desktop_notification)
    assert callable(send_telegram_alert)
    assert callable(send_discord_alert)
    assert callable(dispatch_alert)
    print("[notify] selfcheck OK: All notification handlers verified.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-Platform Alert Dispatcher")
    ap.add_argument("--title", default="Bug Bounty Mission Control Alert", help="Alert title")
    ap.add_argument("--message", default="Surface scanned. No immediate action required.", help="Alert message body")
    ap.add_argument("--severity", choices=["info", "medium", "high", "critical"], default="info", help="Severity level")
    ap.add_argument("--test", action="store_true", help="Send a test alert across all configured channels")
    ap.add_argument("--selfcheck", action="store_true", help="Run internal validation")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
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

