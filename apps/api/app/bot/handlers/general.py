"""/start, language choice, help, cancel and the fallback handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.common import LangCb, ReportCb, Tr, both, language_keyboard, main_menu, set_user_lang
from app.domain.enums import Lang

router = Router(name="general")
fallback_router = Router(name="fallback")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, lang: Lang | None, tr: Tr) -> None:
    await state.clear()
    if lang is None:
        await message.answer(tr("choose-lang"), reply_markup=language_keyboard())
        return
    await message.answer(tr("welcome"), reply_markup=main_menu(tr))


@router.callback_query(LangCb.filter())
async def choose_language(callback: CallbackQuery, callback_data: LangCb, lang: Lang | None) -> None:
    new_lang = Lang(callback_data.code)
    await set_user_lang(callback.from_user.id, new_lang)
    tr = Tr(new_lang)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        text = tr("welcome") if lang is None else tr("lang-changed")
        await callback.message.answer(text, reply_markup=main_menu(tr))


@router.message(F.text.in_(both("menu-help")))
async def help_(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=tr("btn-change-lang"), callback_data="lang:menu")]]
    )
    await message.answer(tr("help"), reply_markup=keyboard)


@router.callback_query(F.data == "lang:menu")
async def language_menu(callback: CallbackQuery, tr: Tr) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(tr("choose-lang"), reply_markup=language_keyboard())


@router.message(StateFilter("*"), F.text.in_(both("btn-cancel")))
async def cancel(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    await message.answer(tr("cancelled"), reply_markup=main_menu(tr))


@router.callback_query(StateFilter("*"), ReportCb.filter(F.action == "cancel"))
async def cancel_inline(callback: CallbackQuery, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        await callback.message.answer(tr("cancelled"), reply_markup=main_menu(tr))


@fallback_router.message()
async def fallback(message: Message, lang: Lang | None, tr: Tr) -> None:
    if lang is None:
        await message.answer(tr("choose-lang"), reply_markup=language_keyboard())
        return
    await message.answer(tr("unknown"), reply_markup=main_menu(tr))


@fallback_router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    # Buttons from old messages (e.g. after a restart) — just stop the spinner.
    await callback.answer()
