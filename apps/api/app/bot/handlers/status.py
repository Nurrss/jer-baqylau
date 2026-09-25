"""📄 Application status: tolerant number input, status card, subscribe toggle."""

from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.common import AppCb, StatusFlow, Tr, both, cancel_keyboard, main_menu, menu_texts
from app.db.models import Application
from app.db.session import session_scope
from app.domain.enums import ApplicationStatus, Lang, SubscriptionTarget
from app.domain.tracking import normalize_application_number
from app.services import applications as service

router = Router(name="status")

STATUS_EMOJI = {
    ApplicationStatus.UNDER_REVIEW: "⏳",
    ApplicationStatus.INSPECTION_SCHEDULED: "🚗",
    ApplicationStatus.APPROVED: "✅",
    ApplicationStatus.REJECTED: "❌",
}


def progress_line(status: ApplicationStatus, tr: Tr) -> str:
    """✅ Подано → ✅ Рассмотрение → ⏳ Выезд инспектора → ▫️ Решение"""
    marks = {
        ApplicationStatus.UNDER_REVIEW: ("✅", "⏳", "▫️", "▫️"),
        ApplicationStatus.INSPECTION_SCHEDULED: ("✅", "✅", "⏳", "▫️"),
        ApplicationStatus.APPROVED: ("✅", "✅", "✅", "✅"),
        ApplicationStatus.REJECTED: ("✅", "✅", "✅", "❌"),
    }[status]
    steps = ("step-submitted", "step-review", "step-inspection", "step-decision")
    return " → ".join(f"{mark} {tr(step)}" for mark, step in zip(marks, steps, strict=True))


def render_card(application: Application, tr: Tr, lang: Lang) -> str:
    comment = application.status_comment_kk if lang is Lang.KK else application.status_comment_ru
    lines = [
        tr("status-card-title", emoji=STATUS_EMOJI[application.status], number=application.tracking_number),
        tr("status-type", type=tr(f"app-type-{application.type.value}")),
        tr("status-status", status=tr(f"application-status-{application.status.value}")),
        tr("status-updated", date=application.updated_at),
        "",
        progress_line(application.status, tr),
    ]
    if comment:
        lines += ["", f"💬 {html.escape(comment)}"]
    if application.inspection_date and application.status is ApplicationStatus.INSPECTION_SCHEDULED:
        lines.append(tr("application-inspection-date", date=application.inspection_date))
    lines += ["", tr("status-next", text=tr(f"next-{application.status.value}"))]
    return "\n".join(lines)


def card_keyboard(application: Application, subscribed: bool, tr: Tr) -> InlineKeyboardMarkup:
    action, label = ("unsub", "btn-unsubscribe") if subscribed else ("sub", "btn-subscribe")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(label), callback_data=AppCb(action=action, id=str(application.id)).pack()
                )
            ]
        ]
    )


@router.message(F.text.in_(both("menu-status")))
async def ask_number(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.set_state(StatusFlow.number)
    await message.answer(tr("status-ask"), reply_markup=cancel_keyboard(tr))


@router.message(StatusFlow.number, F.text, ~F.text.in_(menu_texts()))
async def show_status(message: Message, state: FSMContext, tr: Tr) -> None:
    assert message.text is not None
    assert message.from_user is not None
    number = normalize_application_number(message.text, default_year=datetime.now(UTC).year)
    if number is None:
        await message.answer(tr("status-bad-format"))
        return
    async with session_scope() as session:
        application = await service.get_by_number(session, number)
        subscribed = application is not None and await service.is_subscribed(
            session, message.from_user.id, application.id
        )
    if application is None:
        await message.answer(tr("status-not-found", number=number))
        return
    await state.clear()
    await message.answer(
        render_card(application, tr, tr.lang), reply_markup=card_keyboard(application, subscribed, tr)
    )
    await message.answer(tr("main-menu-hint"), reply_markup=main_menu(tr))


@router.message(StatusFlow.number, ~F.text.in_(menu_texts()))
async def status_not_text(message: Message, tr: Tr) -> None:
    await message.answer(tr("status-bad-format"))


@router.callback_query(AppCb.filter())
async def application_action(callback: CallbackQuery, callback_data: AppCb, tr: Tr) -> None:
    chat_id = callback.from_user.id
    try:
        application_id = uuid.UUID(callback_data.id)
    except ValueError:
        await callback.answer()
        return
    async with session_scope() as session:
        application = await session.get(Application, application_id)
        if application is None:
            await callback.answer()
            return
        if callback_data.action == "sub":
            await service.subscribe(session, chat_id, tr.lang, SubscriptionTarget.APPLICATION, application.id)
        elif callback_data.action == "unsub":
            await service.unsubscribe(session, chat_id, SubscriptionTarget.APPLICATION, application.id)
        subscribed = await service.is_subscribed(session, chat_id, application.id)

    if callback_data.action == "show":
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(
                render_card(application, tr, tr.lang), reply_markup=card_keyboard(application, subscribed, tr)
            )
        return
    notice = "subscribed" if callback_data.action == "sub" else "unsubscribed"
    await callback.answer(tr(notice, number=application.tracking_number))
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=card_keyboard(application, subscribed, tr))  # type: ignore[union-attr]
