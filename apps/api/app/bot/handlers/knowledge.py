"""📚 Knowledge base: procedure list, step-by-step paging, documents/terms, "ask a question"."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.common import KbCb, KnowledgeFlow, Tr, both, cancel_keyboard, main_menu, menu_texts
from app.db.session import session_scope
from app.services import knowledge

router = Router(name="knowledge")


def _btn(text: str, cb: KbCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def list_view(tr: Tr) -> tuple[str, InlineKeyboardMarkup]:
    rows = [[_btn(f"{a.emoji} {a.title}", KbCb(action="open", id=a.id))] for a in knowledge.articles(tr.lang)]
    rows.append([_btn(tr("btn-ask"), KbCb(action="ask"))])
    return tr("kb-list"), InlineKeyboardMarkup(inline_keyboard=rows)


def article_view(tr: Tr, article_id: str) -> tuple[str, InlineKeyboardMarkup] | None:
    article = knowledge.article(tr.lang, article_id)
    if article is None:
        return None
    text = f"{article.emoji} <b>{html.escape(article.title)}</b>\n\n{html.escape(article.summary)}"
    if article.note:
        text += f"\n\n⚠️ {html.escape(article.note)}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(tr("btn-steps"), KbCb(action="step", id=article.id, n=1))],
            [_btn(tr("btn-docs"), KbCb(action="docs", id=article.id))],
            [_btn(tr("btn-ask"), KbCb(action="ask", id=article.id))],
            [_btn(tr("btn-to-list"), KbCb(action="list"))],
        ]
    )
    return text, keyboard


def step_view(tr: Tr, article_id: str, n: int) -> tuple[str, InlineKeyboardMarkup] | None:
    article = knowledge.article(tr.lang, article_id)
    if article is None or not article.steps:
        return None
    total = len(article.steps)
    n = min(max(n, 1), total)
    text = (
        f"{article.emoji} <b>{html.escape(article.title)}</b>\n\n"
        f"{tr('kb-step', n=n, total=total)}\n{html.escape(article.steps[n - 1])}"
    )
    nav = []
    if n > 1:
        nav.append(_btn(tr("btn-back"), KbCb(action="step", id=article.id, n=n - 1)))
    if n < total:
        nav.append(_btn(tr("btn-next"), KbCb(action="step", id=article.id, n=n + 1)))
    rows = [nav] if nav else []
    rows += [
        [_btn(tr("btn-docs"), KbCb(action="docs", id=article.id))],
        [_btn(tr("btn-to-list"), KbCb(action="list"))],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def docs_view(tr: Tr, article_id: str) -> tuple[str, InlineKeyboardMarkup] | None:
    article = knowledge.article(tr.lang, article_id)
    if article is None:
        return None
    lines = [f"{article.emoji} <b>{html.escape(article.title)}</b>", "", tr("kb-docs")]
    lines += [f"• {html.escape(doc)}" for doc in article.documents]
    lines += [
        "",
        tr("kb-terms", text=html.escape(article.terms)),
        tr("kb-fee", text=html.escape(article.fee)),
        tr("kb-where", text=html.escape(article.where)),
        "",
        tr("kb-links"),
    ]
    lines += [f'• <a href="{link.url}">{html.escape(link.title)}</a>' for link in article.links]
    lines += ["", tr("kb-disclaimer")]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(tr("btn-steps"), KbCb(action="step", id=article.id, n=1))],
            [_btn(tr("btn-ask"), KbCb(action="ask", id=article.id))],
            [_btn(tr("btn-to-list"), KbCb(action="list"))],
        ]
    )
    return "\n".join(lines), keyboard


@router.message(F.text.in_(both("menu-knowledge")))
async def open_list(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    text, keyboard = list_view(tr)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(KbCb.filter(F.action == "ask"))
async def ask_question(callback: CallbackQuery, callback_data: KbCb, state: FSMContext, tr: Tr) -> None:
    await callback.answer()
    await state.set_state(KnowledgeFlow.question)
    await state.update_data(topic=callback_data.id or None)
    if callback.message is not None:
        await callback.message.answer(tr("kb-ask"), reply_markup=cancel_keyboard(tr))


@router.callback_query(KbCb.filter())
async def navigate(callback: CallbackQuery, callback_data: KbCb, tr: Tr) -> None:
    views = {
        "list": lambda: list_view(tr),
        "open": lambda: article_view(tr, callback_data.id),
        "step": lambda: step_view(tr, callback_data.id, callback_data.n),
        "docs": lambda: docs_view(tr, callback_data.id),
    }
    view = views.get(callback_data.action, lambda: None)()
    await callback.answer()
    if view is None or callback.message is None:
        return
    text, keyboard = view
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)  # type: ignore[union-attr]
    except TelegramBadRequest:
        # "message is not modified" or the message is too old to edit — send a new one.
        await callback.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


@router.message(KnowledgeFlow.question, F.text, ~F.text.in_(menu_texts()))
async def save_question(message: Message, state: FSMContext, tr: Tr) -> None:
    assert message.text is not None
    data = await state.get_data()
    async with session_scope() as session:
        await knowledge.save_question(session, message.chat.id, tr.lang, data.get("topic"), message.text)
    await state.clear()
    await message.answer(tr("kb-question-saved"), reply_markup=main_menu(tr))
