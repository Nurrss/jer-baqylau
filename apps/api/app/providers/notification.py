"""Outbound notification channels for citizens.

Telegram is the working channel. ``SmsNotificationProvider`` / eGov mobile are
documented extension points: they share the protocol, so the notifier does not
change when a new channel is connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationButton:
    text: str
    callback_data: str | None = None
    url: str | None = None
    web_app_url: str | None = None  # opens a Telegram Mini App (HTTPS only)


@dataclass(frozen=True, slots=True)
class Notification:
    chat_id: int
    text: str
    buttons: tuple[NotificationButton, ...] = ()


class NotificationProvider(Protocol):
    name: str

    async def send(self, notification: Notification) -> bool: ...


class LogNotificationProvider:
    """Used when the bot is disabled (local dev, tests): just logs messages."""

    name = "log"

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        log.info("notification_logged", chat_id=notification.chat_id, text=notification.text[:120])
        return True


class TelegramNotificationProvider:
    name = "telegram"

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send(self, notification: Notification) -> bool:
        from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

        markup = None
        if notification.buttons:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=b.text,
                            callback_data=b.callback_data,
                            url=b.url,
                            web_app=WebAppInfo(url=b.web_app_url) if b.web_app_url else None,
                        )
                    ]
                    for b in notification.buttons
                ]
            )
        try:
            await self.bot.send_message(notification.chat_id, notification.text, reply_markup=markup)
            return True
        except TelegramForbiddenError:
            log.info("notification_blocked_by_user", chat_id=notification.chat_id)
        except TelegramAPIError as exc:
            log.warning("notification_failed", chat_id=notification.chat_id, error=str(exc))
        return False


class SmsNotificationProvider:
    """Extension point: SMS gateway / eGov mobile push. Not connected in the MVP."""

    name = "sms"

    async def send(self, notification: Notification) -> bool:
        log.info("sms_channel_not_configured", chat_id=notification.chat_id)
        return False


_provider: NotificationProvider = LogNotificationProvider()


def set_notification_provider(provider: NotificationProvider) -> None:
    global _provider
    _provider = provider


def get_notification_provider() -> NotificationProvider:
    return _provider
