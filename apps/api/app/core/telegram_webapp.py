"""Telegram Mini App authentication: validation of ``initData``.

The Mini App runs inside Telegram, which signs the launch parameters with the bot token
(https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
A valid signature proves who the citizen is without any login or password.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.core.config import get_settings
from app.core.errors import AuthError
from app.domain.enums import Lang

MAX_AGE_SECONDS = 24 * 3600


@dataclass(frozen=True, slots=True)
class WebAppUser:
    id: int  # equals the private chat id with the bot
    first_name: str
    last_name: str | None
    language_code: str | None

    @property
    def lang(self) -> Lang:
        return Lang.KK if (self.language_code or "").lower().startswith("kk") else Lang.RU


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Build a signed initData string (used by tests and local tooling)."""
    from urllib.parse import urlencode

    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def validate_init_data(init_data: str | None, *, now: float | None = None) -> WebAppUser:
    token = get_settings().telegram_bot_token.get_secret_value()
    if not init_data or not token:
        raise AuthError("Open the app from the Telegram bot", code="TELEGRAM_AUTH_REQUIRED")
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received = fields.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("Telegram signature is invalid", code="TELEGRAM_AUTH_INVALID")
    auth_date = int(fields.get("auth_date", "0") or 0)
    if (now or time.time()) - auth_date > MAX_AGE_SECONDS:
        raise AuthError("Telegram session expired, reopen the app", code="TELEGRAM_AUTH_EXPIRED")
    try:
        user = json.loads(fields["user"])
        return WebAppUser(
            id=int(user["id"]),
            first_name=str(user.get("first_name", "")),
            last_name=user.get("last_name"),
            language_code=user.get("language_code"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("Telegram user is missing", code="TELEGRAM_AUTH_INVALID") from exc
