"""Manage the Telegram webhook (the API also sets it on start in BOT_MODE=webhook).

    uv run --project apps/api python scripts/set_webhook.py --url https://<api-host>
    uv run --project apps/api python scripts/set_webhook.py --info
    uv run --project apps/api python scripts/set_webhook.py --delete     # before local polling
Uses TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from .env.
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401
import httpx


def main() -> int:
    from app.core.config import get_settings

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Public base URL of the API (https)")
    group.add_argument("--info", action="store_true")
    group.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set")
        return 1
    api = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=20) as http:
        if args.info:
            resp = http.get(f"{api}/getWebhookInfo")
        elif args.delete:
            resp = http.post(f"{api}/deleteWebhook")
        else:
            secret = settings.telegram_webhook_secret.get_secret_value()
            if not secret:
                print("TELEGRAM_WEBHOOK_SECRET is not set")
                return 1
            if not args.url.startswith("https://"):
                print("Telegram requires an https URL")
                return 1
            resp = http.post(
                f"{api}/setWebhook",
                json={
                    "url": f"{args.url.rstrip('/')}/tg/webhook",
                    "secret_token": secret,
                    "allowed_updates": ["message", "callback_query"],
                },
            )
    body = resp.json()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if body.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
