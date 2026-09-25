"""🗂 My requests: the citizen's signals and tracked applications."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.common import AppCb, Tr, both, main_menu
from app.db.session import session_scope
from app.services import applications as application_service
from app.services import signals as signal_service

router = Router(name="my")


@router.message(F.text.in_(both("menu-my")))
async def my_requests(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    async with session_scope() as session:
        signals = await signal_service.signals_for_chat(session, message.chat.id)
        applications = await application_service.subscribed_applications(session, message.chat.id)

    if not signals and not applications:
        await message.answer(tr("my-empty"), reply_markup=main_menu(tr))
        return

    lines = [tr("my-title")]
    if signals:
        lines += ["", tr("my-signals")]
        lines += [
            tr(
                "my-signal-line",
                code=s.tracking_code,
                category=tr(f"category-{s.category.value}"),
                status=tr(f"signal-status-{s.status.value}"),
                date=s.created_at.date(),
            )
            for s in signals
        ]
    if applications:
        lines += ["", tr("my-apps")]
        lines += [
            tr("my-app-line", number=a.tracking_number, status=tr(f"application-status-{a.status.value}"))
            for a in applications
        ]
    keyboard = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"📄 {a.tracking_number}",
                        callback_data=AppCb(action="show", id=str(a.id)).pack(),
                    )
                ]
                for a in applications
            ]
        )
        if applications
        else None
    )
    await message.answer("\n".join(lines), reply_markup=keyboard or main_menu(tr))
