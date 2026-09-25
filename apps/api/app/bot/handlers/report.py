"""📍 «Народный контроль»: category → location → 1–5 photos → description → confirm → signal.

The signal is created (and shown on the inspector map) right after "Send"; photos are
downloaded from Telegram and attached in the background so the update is acked fast.
"""

from __future__ import annotations

import asyncio
import html
import io
import time
import uuid
from collections import defaultdict
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.common import (
    ReportCb,
    ReportFlow,
    Tr,
    both,
    category_keyboard,
    confirm_keyboard,
    description_keyboard,
    edit_keyboard,
    location_keyboard,
    main_menu,
    menu_texts,
    photos_keyboard,
)
from app.core.errors import RateLimitedError, ValidationFailedError
from app.core.logging import get_logger
from app.db.session import session_scope
from app.domain.enums import PhotoSource, SignalCategory
from app.providers.storage import get_storage
from app.services import geocoding
from app.services import signals as signal_service

log = get_logger(__name__)
router = Router(name="report")

MAX_PHOTOS = 5
MAX_DESCRIPTION = 500
PHOTO_ACK_DELAY = 1.2  # seconds: one reply per album instead of one per photo

_chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_last_photo_at: dict[int, float] = {}
_background: set[asyncio.Task[Any]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ── Step prompts (also used when editing a step from the confirmation) ─────


async def ask_category(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.set_state(ReportFlow.category)
    await message.answer(tr("report-category"), reply_markup=category_keyboard(tr))


async def ask_location(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.set_state(ReportFlow.location)
    await message.answer(tr("report-location"), reply_markup=location_keyboard(tr))


async def ask_photos(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.set_state(ReportFlow.photos)
    await state.update_data(photos=[])
    await message.answer(tr("report-photos"), reply_markup=photos_keyboard(tr))


async def ask_description(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.set_state(ReportFlow.description)
    await message.answer(tr("report-description"), reply_markup=description_keyboard(tr))


async def show_summary(message: Message, state: FSMContext, tr: Tr) -> None:
    data = await state.get_data()
    await state.set_state(ReportFlow.confirm)
    await state.update_data(editing=False)
    description = data.get("description")
    text = tr(
        "report-summary",
        category=tr(f"cat-{data['category']}"),
        address=html.escape(data["address"]),
        count=len(data.get("photos", [])),
        description=html.escape(description) if description else tr("report-no-description"),
    )
    await message.answer(tr("report-almost"), reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=confirm_keyboard(tr))


async def _next_or_summary(message: Message, state: FSMContext, tr: Tr, next_step: Any) -> None:
    """After a step: continue the chain, or return to the summary when editing."""
    if (await state.get_data()).get("editing"):
        await show_summary(message, state, tr)
    else:
        await next_step(message, state, tr)


# ── Entry ───────────────────────────────────────────────────────────────────


@router.message(F.text.in_(both("menu-report")))
async def start_report(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.clear()
    async with session_scope() as session:
        try:
            await signal_service.check_rate_limit(session, message.chat.id)
        except RateLimitedError:
            await message.answer(tr("report-rate-limited"), reply_markup=main_menu(tr))
            return
    await ask_category(message, state, tr)


@router.callback_query(ReportFlow.category, ReportCb.filter(F.action == "cat"))
async def choose_category(
    callback: CallbackQuery, callback_data: ReportCb, state: FSMContext, tr: Tr
) -> None:
    await callback.answer()
    await state.update_data(category=SignalCategory(callback_data.value).value)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"{tr('report-category')}\n\n✅ {tr(f'cat-{callback_data.value}')}")
        await _next_or_summary(callback.message, state, tr, ask_location)


@router.message(ReportFlow.category)
async def category_expected(message: Message, tr: Tr) -> None:
    await message.answer(tr("report-category"), reply_markup=category_keyboard(tr))


# ── Location ────────────────────────────────────────────────────────────────


@router.message(ReportFlow.location, F.location | F.venue)
async def receive_location(message: Message, state: FSMContext, tr: Tr) -> None:
    location = message.venue.location if message.venue else message.location
    assert location is not None
    lat, lon = location.latitude, location.longitude
    if not signal_service.in_region(lat, lon):
        await message.answer(tr("report-out-of-region"), reply_markup=location_keyboard(tr))
        return
    async with session_scope() as session:
        address = await geocoding.reverse(session, lat, lon, tr.lang)
    await state.update_data(lat=lat, lon=lon, address=address)
    await _next_or_summary(message, state, tr, ask_photos)


@router.message(ReportFlow.location)
async def location_expected(message: Message, tr: Tr) -> None:
    await message.answer(tr("report-location-invalid"), reply_markup=location_keyboard(tr))


# ── Photos ──────────────────────────────────────────────────────────────────


async def _ack_photos(message: Message, state: FSMContext, tr: Tr, stamp: float) -> None:
    await asyncio.sleep(PHOTO_ACK_DELAY)
    if _last_photo_at.get(message.chat.id) != stamp:
        return  # a newer photo of the same album will answer
    count = len((await state.get_data()).get("photos", []))
    await message.answer(tr("report-photo-received", count=count), reply_markup=photos_keyboard(tr))


async def _add_photo(message: Message, state: FSMContext, tr: Tr, file_id: str) -> None:
    async with _chat_locks[message.chat.id]:
        photos: list[str] = list((await state.get_data()).get("photos", []))
        if len(photos) >= MAX_PHOTOS:
            # Warn once per album, not for every extra photo in it.
            warned = (await state.get_data()).get("limit_warned")
            if not message.media_group_id or warned != message.media_group_id:
                await state.update_data(limit_warned=message.media_group_id or "single")
                await message.answer(tr("report-photo-limit"))
            return
        photos.append(file_id)
        await state.update_data(photos=photos)
        stamp = time.monotonic()
        _last_photo_at[message.chat.id] = stamp
    _spawn(_ack_photos(message, state, tr, stamp))


@router.message(ReportFlow.photos, F.photo)
async def receive_photo(message: Message, state: FSMContext, tr: Tr) -> None:
    assert message.photo
    await _add_photo(message, state, tr, message.photo[-1].file_id)  # largest size


@router.message(ReportFlow.photos, F.document)
async def receive_photo_file(message: Message, state: FSMContext, tr: Tr) -> None:
    document = message.document
    assert document is not None
    if not (document.mime_type or "").startswith("image/"):
        await message.answer(tr("report-photo-not-image"))
        return
    await _add_photo(message, state, tr, document.file_id)


@router.message(ReportFlow.photos, F.text.in_(both("btn-done")))
async def photos_done(message: Message, state: FSMContext, tr: Tr) -> None:
    if not (await state.get_data()).get("photos"):
        await message.answer(tr("report-photo-required"), reply_markup=photos_keyboard(tr))
        return
    await _next_or_summary(message, state, tr, ask_description)


@router.message(ReportFlow.photos)
async def photo_expected(message: Message, tr: Tr) -> None:
    await message.answer(tr("report-photos"), reply_markup=photos_keyboard(tr))


# ── Description ─────────────────────────────────────────────────────────────


@router.message(ReportFlow.description, F.text.in_(both("btn-skip")))
async def skip_description(message: Message, state: FSMContext, tr: Tr) -> None:
    await state.update_data(description=None)
    await show_summary(message, state, tr)


@router.message(ReportFlow.description, F.text, ~F.text.in_(menu_texts()))
async def receive_description(message: Message, state: FSMContext, tr: Tr) -> None:
    text = (message.text or "").strip()
    if len(text) > MAX_DESCRIPTION:
        await message.answer(tr("report-description-too-long", length=len(text)))
        return
    await state.update_data(description=text or None)
    await show_summary(message, state, tr)


@router.message(ReportFlow.description)
async def description_expected(message: Message, tr: Tr) -> None:
    await message.answer(tr("report-description"), reply_markup=description_keyboard(tr))


# ── Confirmation ────────────────────────────────────────────────────────────


@router.callback_query(ReportFlow.confirm, ReportCb.filter(F.action == "edit"))
async def edit(callback: CallbackQuery, tr: Tr) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=edit_keyboard(tr))


@router.callback_query(ReportFlow.confirm, ReportCb.filter(F.action == "back"))
async def edit_back(callback: CallbackQuery, tr: Tr) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=confirm_keyboard(tr))


@router.callback_query(ReportFlow.confirm, ReportCb.filter(F.action == "editstep"))
async def edit_step(callback: CallbackQuery, callback_data: ReportCb, state: FSMContext, tr: Tr) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(editing=True)
    prompts = {
        "category": ask_category,
        "location": ask_location,
        "photos": ask_photos,
        "description": ask_description,
    }
    await prompts[callback_data.value](callback.message, state, tr)


@router.callback_query(ReportFlow.confirm, ReportCb.filter(F.action == "submit"))
async def submit(callback: CallbackQuery, state: FSMContext, tr: Tr, bot: Bot) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    message = callback.message
    data = await state.get_data()
    chat_id = callback.from_user.id
    await message.edit_reply_markup(reply_markup=None)
    try:
        async with session_scope() as session:
            signal = await signal_service.create_signal(
                session,
                lat=data["lat"],
                lon=data["lon"],
                category=SignalCategory(data["category"]),
                description=data.get("description"),
                reporter_chat_id=chat_id,
                reporter_lang=tr.lang,
                address=data.get("address"),
            )
            code, signal_id, duplicate = signal.tracking_code, signal.id, signal.duplicate_of is not None
    except RateLimitedError:
        await state.clear()
        await message.answer(tr("report-rate-limited"), reply_markup=main_menu(tr))
        return
    except ValidationFailedError:
        await state.clear()
        await message.answer(tr("report-out-of-region"), reply_markup=main_menu(tr))
        return
    except Exception:
        log.exception("signal_create_failed", chat_id=chat_id)
        await message.answer(tr("report-failed"), reply_markup=confirm_keyboard(tr))
        return

    await state.clear()
    text = tr("report-accepted", code=code)
    if duplicate:
        text += "\n\n" + tr("report-accepted-duplicate")
    await message.answer(text, reply_markup=main_menu(tr))
    log.info("signal_created_via_bot", code=code, chat_id=chat_id, photos=len(data.get("photos", [])))
    _spawn(attach_telegram_photos(bot, signal_id, list(data.get("photos", [])), chat_id))


async def attach_telegram_photos(bot: Bot, signal_id: uuid.UUID, file_ids: list[str], chat_id: int) -> None:
    """Download photos from Telegram and store them (background task)."""
    blobs: list[bytes] = []
    for file_id in file_ids:
        try:
            buffer = io.BytesIO()
            await bot.download(file_id, destination=buffer)
            blobs.append(buffer.getvalue())
        except Exception:
            log.warning("telegram_photo_download_failed", signal_id=str(signal_id), file_id=file_id)
    if not blobs:
        return
    try:
        async with session_scope() as session:
            saved = await signal_service.attach_photos(
                session, get_storage(), signal_id, blobs, f"citizen:{chat_id}", PhotoSource.CITIZEN
            )
        log.info("signal_photos_attached", signal_id=str(signal_id), count=saved)
    except Exception:
        log.exception("signal_photos_attach_failed", signal_id=str(signal_id))
