"""Shared bot helpers: per-user language, localized button matching, FSM states, keyboards."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.i18n import t
from app.db.models import TelegramUser
from app.db.session import session_scope
from app.domain.enums import Lang, SignalCategory

# ── Language ────────────────────────────────────────────────────────────────

_lang_cache: dict[int, Lang] = {}


async def get_user_lang(chat_id: int) -> Lang | None:
    if chat_id in _lang_cache:
        return _lang_cache[chat_id]
    async with session_scope() as session:
        lang = await session.scalar(select(TelegramUser.lang).where(TelegramUser.chat_id == chat_id))
    if lang is not None:
        _lang_cache[chat_id] = lang
    return lang


async def set_user_lang(chat_id: int, lang: Lang) -> None:
    async with session_scope() as session:
        await session.execute(
            insert(TelegramUser)
            .values(chat_id=chat_id, lang=lang)
            .on_conflict_do_update(index_elements=[TelegramUser.chat_id], set_={"lang": lang})
        )
    _lang_cache[chat_id] = lang


def clear_lang_cache() -> None:
    _lang_cache.clear()


def both(key: str) -> set[str]:
    """A button label in every language — used to match reply-keyboard presses."""
    return {t(lang, key) for lang in Lang}


MENU_KEYS = ("menu-status", "menu-knowledge", "menu-report", "menu-my", "menu-help", "btn-cancel")


def menu_texts() -> set[str]:
    """Every main-menu label: free-text states must not swallow menu presses."""
    return set().union(*(both(key) for key in MENU_KEYS))


class Tr:
    """Translator bound to the user's language, injected into handlers as ``tr``."""

    def __init__(self, lang: Lang):
        self.lang = lang

    def __call__(self, key: str, **kwargs: Any) -> str:
        return t(self.lang, key, **kwargs)


class LanguageMiddleware(BaseMiddleware):
    """Injects ``lang`` (possibly None for a brand-new user) and ``tr`` (falls back to Russian)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = data.get("event_chat")
        lang = await get_user_lang(chat.id) if chat else None
        data["lang"] = lang
        data["tr"] = Tr(lang or Lang.RU)
        return await handler(event, data)


class FsmTimeoutMiddleware(BaseMiddleware):
    """Expires abandoned dialogs: state older than FSM_TIMEOUT_MINUTES is cleared."""

    KEY = "_touched_at"

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        if state is None:
            return await handler(event, data)
        timeout = get_settings().fsm_timeout_minutes * 60
        if await state.get_state() is not None:
            touched = (await state.get_data()).get(self.KEY, 0)
            if time.time() - touched > timeout:
                await state.clear()
                tr: Tr = data["tr"]
                if isinstance(event, Message):
                    await event.answer(tr("fsm-expired"), reply_markup=main_menu(tr))
                elif isinstance(event, CallbackQuery):
                    await event.answer(tr("fsm-expired"), show_alert=True)
                return None
        result = await handler(event, data)
        if await state.get_state() is not None:
            await state.update_data({self.KEY: time.time()})
        return result


# ── States ──────────────────────────────────────────────────────────────────


class StatusFlow(StatesGroup):
    number = State()


class KnowledgeFlow(StatesGroup):
    question = State()


class ReportFlow(StatesGroup):
    category = State()
    location = State()
    photos = State()
    description = State()
    confirm = State()


# ── Callback data ───────────────────────────────────────────────────────────


class LangCb(CallbackData, prefix="lang"):
    code: str


class AppCb(CallbackData, prefix="app"):
    action: str  # show | sub | unsub
    id: str


class KbCb(CallbackData, prefix="kb"):
    action: str  # list | open | step | docs | ask
    id: str = ""
    n: int = 0


class ReportCb(CallbackData, prefix="rep"):
    action: str  # cat | submit | edit | editstep | cancel
    value: str = ""


# ── Keyboards ───────────────────────────────────────────────────────────────


def main_menu(tr: Tr) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tr("menu-status")), KeyboardButton(text=tr("menu-knowledge"))],
            [KeyboardButton(text=tr("menu-report"))],
            [KeyboardButton(text=tr("menu-my")), KeyboardButton(text=tr("menu-help"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def cancel_keyboard(tr: Tr) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=tr("btn-cancel"))]], resize_keyboard=True)


def location_keyboard(tr: Tr) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tr("btn-send-location"), request_location=True)],
            [KeyboardButton(text=tr("btn-cancel"))],
        ],
        resize_keyboard=True,
    )


def photos_keyboard(tr: Tr) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=tr("btn-done"))], [KeyboardButton(text=tr("btn-cancel"))]],
        resize_keyboard=True,
    )


def description_keyboard(tr: Tr) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=tr("btn-skip"))], [KeyboardButton(text=tr("btn-cancel"))]],
        resize_keyboard=True,
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(Lang.KK, "btn-lang-kk"), callback_data=LangCb(code="kk").pack()),
                InlineKeyboardButton(text=t(Lang.RU, "btn-lang-ru"), callback_data=LangCb(code="ru").pack()),
            ]
        ]
    )


def category_keyboard(tr: Tr) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(f"cat-{c.value}"), callback_data=ReportCb(action="cat", value=c.value).pack()
                )
            ]
            for c in SignalCategory
        ]
        + [[InlineKeyboardButton(text=tr("btn-cancel"), callback_data=ReportCb(action="cancel").pack())]]
    )


def confirm_keyboard(tr: Tr) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr("btn-submit"), callback_data=ReportCb(action="submit").pack())],
            [
                InlineKeyboardButton(text=tr("btn-edit"), callback_data=ReportCb(action="edit").pack()),
                InlineKeyboardButton(text=tr("btn-cancel"), callback_data=ReportCb(action="cancel").pack()),
            ],
        ]
    )


def edit_keyboard(tr: Tr) -> InlineKeyboardMarkup:
    steps = ("category", "location", "photos", "description")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(f"btn-edit-{s}"), callback_data=ReportCb(action="editstep", value=s).pack()
                )
                for s in steps[:2]
            ],
            [
                InlineKeyboardButton(
                    text=tr(f"btn-edit-{s}"), callback_data=ReportCb(action="editstep", value=s).pack()
                )
                for s in steps[2:]
            ],
            [InlineKeyboardButton(text=tr("btn-back"), callback_data=ReportCb(action="back").pack())],
        ]
    )
