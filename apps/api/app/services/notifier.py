"""Builds localized citizen notifications and sends them after commit."""

from __future__ import annotations

import html
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models import Application, InspectionRequest, Parcel, Signal, Subscription, TelegramUser
from app.domain.enums import Lang, SignalStatus, SubscriptionTarget
from app.providers.notification import Notification, NotificationButton, get_notification_provider
from app.services.outbox import after_commit

log = get_logger(__name__)


async def _langs(session: AsyncSession, chat_ids: set[int]) -> dict[int, Lang]:
    if not chat_ids:
        return {}
    rows = await session.execute(
        select(TelegramUser.chat_id, TelegramUser.lang).where(TelegramUser.chat_id.in_(chat_ids))
    )
    return {chat_id: lang for chat_id, lang in rows if lang is not None}


async def _subscribers(session: AsyncSession, target: SubscriptionTarget, target_id: uuid.UUID) -> set[int]:
    rows = await session.scalars(
        select(Subscription.chat_id).where(
            Subscription.target_type == target, Subscription.target_id == target_id
        )
    )
    return set(rows)


def _dispatch(session: AsyncSession, notifications: list[Notification]) -> None:
    if not notifications:
        return

    async def _send() -> None:
        provider = get_notification_provider()
        for notification in notifications:
            await provider.send(notification)
        log.info("notifications_sent", count=len(notifications), provider=provider.name)

    after_commit(session, _send)


async def signal_status_changed(
    session: AsyncSession, signal: Signal, new_status: SignalStatus, comment: str | None
) -> None:
    recipients: dict[int, Lang] = {}
    if signal.reporter_chat_id:
        recipients[signal.reporter_chat_id] = signal.reporter_lang
    for chat_id in await _subscribers(session, SubscriptionTarget.SIGNAL, signal.id):
        recipients.setdefault(chat_id, Lang.RU)
    recipients.update(await _langs(session, set(recipients)))

    notifications = []
    for chat_id, lang in recipients.items():
        text = t(
            lang,
            "notify-signal-status",
            code=signal.tracking_code,
            status=t(lang, f"signal-status-{new_status.value}"),
        )
        if new_status is SignalStatus.REJECTED and comment:
            text += "\n\n" + t(lang, "notify-reason", reason=html.escape(comment))
        elif new_status is SignalStatus.CONFIRMED:
            text += "\n\n" + t(lang, "notify-signal-confirmed-hint")
        notifications.append(Notification(chat_id=chat_id, text=text))
    _dispatch(session, notifications)


async def parcel_status_changed(session: AsyncSession, parcel: Parcel) -> None:
    """Tell citizens who reported problems on this parcel how the case progresses."""
    rows = await session.execute(
        select(Signal.reporter_chat_id, Signal.reporter_lang, Signal.tracking_code).where(
            Signal.parcel_id == parcel.id,
            Signal.reporter_chat_id.is_not(None),
            Signal.status != SignalStatus.REJECTED,
        )
    )
    recipients: dict[int, tuple[Lang, str]] = {}
    for chat_id, lang, code in rows:
        recipients.setdefault(chat_id, (lang, code))
    langs = await _langs(session, set(recipients))

    notifications = []
    for chat_id, (reporter_lang, code) in recipients.items():
        lang = langs.get(chat_id, reporter_lang)
        text = t(
            lang,
            "notify-parcel-status",
            code=code,
            cadastral=parcel.cadastral_number,
            status=t(lang, f"parcel-status-{parcel.status.value}"),
        )
        notifications.append(Notification(chat_id=chat_id, text=text))
    _dispatch(session, notifications)


async def application_status_changed(session: AsyncSession, application: Application) -> None:
    chat_ids = await _subscribers(session, SubscriptionTarget.APPLICATION, application.id)
    langs = await _langs(session, chat_ids)
    notifications = []
    for chat_id in chat_ids:
        lang = langs.get(chat_id, Lang.RU)
        comment = application.status_comment_kk if lang is Lang.KK else application.status_comment_ru
        text = t(
            lang,
            "notify-application-status",
            number=application.tracking_number,
            status=t(lang, f"application-status-{application.status.value}"),
        )
        if comment:
            text += "\n\n" + html.escape(comment)
        if application.inspection_date:
            text += "\n" + t(lang, "application-inspection-date", date=application.inspection_date)
        notifications.append(
            Notification(
                chat_id=chat_id,
                text=text,
                buttons=(
                    NotificationButton(
                        text=t(lang, "btn-show-application"), callback_data=f"app:show:{application.id}"
                    ),
                ),
            )
        )
    _dispatch(session, notifications)


def web_app_url(path: str) -> str | None:
    """Mini App URL for a button, or None when the panel is not served over HTTPS (Telegram requires it)."""
    base = get_settings().public_web_url.rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


async def _lang_of(session: AsyncSession, chat_id: int, default: Lang = Lang.RU) -> Lang:
    return (await _langs(session, {chat_id})).get(chat_id, default)


async def land_application_draft(
    session: AsyncSession, application: Application, parcels: list[Parcel]
) -> None:
    """Ask the citizen to confirm the application formed in the Mini App."""
    chat_id = application.applicant_chat_id
    if chat_id is None:
        return
    lang = await _lang_of(session, chat_id)
    lines = [
        t(lang, "land-draft-title", number=application.tracking_number),
        t(lang, f"app-type-{application.type.value}"),
        "",
    ]
    for i, parcel in enumerate(parcels, start=1):
        address = parcel.address_kk if lang is Lang.KK else parcel.address_ru
        lines.append(
            t(
                lang,
                "land-draft-parcel",
                n=i,
                cadastral=parcel.cadastral_number,
                area=f"{float(parcel.area_ha):.2f}",
                address=html.escape(address),
            )
        )
    lines += [
        "",
        t(
            lang,
            "land-draft-applicant",
            name=html.escape(application.applicant_name),
            iin=application.applicant_iin_masked or "—",
            phone=application.applicant_phone_masked or "—",
        ),
    ]
    if len(parcels) > 1:
        lines.append(t(lang, "land-draft-priority"))
    lines += ["", t(lang, "land-draft-confirm-hint")]
    _dispatch(
        session,
        [
            Notification(
                chat_id=chat_id,
                text="\n".join(lines),
                buttons=(
                    NotificationButton(
                        text=t(lang, "btn-land-confirm"), callback_data=f"land:confirm:{application.id}"
                    ),
                    NotificationButton(
                        text=t(lang, "btn-land-cancel"), callback_data=f"land:cancel:{application.id}"
                    ),
                ),
            )
        ],
    )


async def inspection_requested(
    session: AsyncSession, request: InspectionRequest, parcel: Parcel, link: str
) -> bool:
    """Send the remote-inspection link straight to the right holder's Telegram. False if unknown."""
    chat_id = parcel.owner_chat_id
    if chat_id is None:
        return False
    lang = await _lang_of(session, chat_id)
    text = t(
        lang,
        "inspection-request",
        cadastral=parcel.cadastral_number,
        code=request.code,
        due=f"{request.due_at:%d.%m.%Y %H:%M}",
    )
    if request.note:
        text += "\n\n" + t(lang, "inspection-request-note", note=html.escape(request.note))
    text += "\n\n" + t(lang, "inspection-request-hint")
    app_url = web_app_url(f"/inspect/{request.token}?lang={lang.value}")
    buttons = (
        [NotificationButton(text=t(lang, "btn-inspection-open"), web_app_url=app_url)] if app_url else []
    )
    buttons.append(NotificationButton(text=t(lang, "btn-inspection-browser"), url=link))
    _dispatch(session, [Notification(chat_id=chat_id, text=text, buttons=tuple(buttons))])
    return True


async def inspection_reviewed(session: AsyncSession, request: InspectionRequest, parcel: Parcel) -> None:
    chat_id = parcel.owner_chat_id
    if chat_id is None:
        return
    lang = await _lang_of(session, chat_id)
    text = t(
        lang,
        "inspection-reviewed",
        code=request.code,
        cadastral=parcel.cadastral_number,
        status=t(lang, f"inspection-status-{request.status.value}"),
    )
    if request.review_comment:
        text += "\n\n" + t(lang, "notify-reason", reason=html.escape(request.review_comment))
    _dispatch(session, [Notification(chat_id=chat_id, text=text)])
