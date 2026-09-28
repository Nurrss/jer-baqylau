"""🗺 Free state land: confirmation of applications formed in the Telegram Mini App."""

from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.common import LandCb, Tr, both, lands_app_url, main_menu
from app.core.errors import DomainError
from app.db.session import session_scope
from app.domain.enums import ApplicationStatus
from app.services import land as service

router = Router(name="land")


@router.message(F.text.in_(both("menu-lands")))
async def lands(message: Message, tr: Tr) -> None:
    """Fallback for clients that send the button text instead of opening the Mini App."""
    url = lands_app_url(tr.lang)
    if url is None:
        await message.answer(tr("lands-unavailable"), reply_markup=main_menu(tr))
        return
    await message.answer(
        tr("lands-intro"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=tr("btn-lands-open"), web_app=WebAppInfo(url=url))]]
        ),
    )


@router.callback_query(LandCb.filter())
async def decide(callback: CallbackQuery, callback_data: LandCb, tr: Tr) -> None:
    assert callback.from_user is not None
    application_id = uuid.UUID(callback_data.id)
    try:
        async with session_scope() as session:
            if callback_data.action == "confirm":
                application = await service.confirm(session, application_id, callback.from_user.id, tr.lang)
            else:
                application = await service.cancel(session, application_id, callback.from_user.id)
            number, status = application.tracking_number, application.status
    except DomainError as exc:
        key = "land-taken" if exc.code == "PARCEL_TAKEN" else "land-failed"
        await callback.answer(tr(key), show_alert=True)
        if exc.code == "PARCEL_TAKEN" and isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)
        return
    text = {
        ApplicationStatus.CANCELLED: tr("land-cancelled", number=number),
        ApplicationStatus.DRAFT: tr("land-failed"),
    }.get(status, tr("land-confirmed", number=number))
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(text, reply_markup=main_menu(tr))
