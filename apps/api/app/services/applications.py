"""Land applications (заявления): lookup by tracking number and status lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidTransitionError, NotFoundError
from app.db.models import Application, Parcel, Subscription, TelegramUser
from app.domain.enums import ApplicationStatus, EntityType, EventType, Lang, SubscriptionTarget
from app.domain.state_machine import allowed_transitions, ensure_transition
from app.schemas.misc import ApplicationList, ApplicationOut, ApplicationTransitionRequest
from app.services import audit, notifier

CITIZEN_ONLY = (ApplicationStatus.DRAFT, ApplicationStatus.CANCELLED)


async def get_application(
    session: AsyncSession, application_id: uuid.UUID, *, for_update: bool = False
) -> Application:
    query = select(Application).where(Application.id == application_id)
    if for_update:
        query = query.with_for_update()
    application = await session.scalar(query)
    if application is None:
        raise NotFoundError("Application not found", details={"application_id": str(application_id)})
    return application


async def get_by_number(session: AsyncSession, tracking_number: str) -> Application | None:
    return await session.scalar(select(Application).where(Application.tracking_number == tracking_number))


async def to_out_many(session: AsyncSession, applications: list[Application]) -> list[ApplicationOut]:
    """Serialize applications with a constant number of queries (no N+1: the DB may be far away)."""
    if not applications:
        return []
    ids = [a.id for a in applications]
    parcel_ids = {a.parcel_id for a in applications if a.parcel_id}
    cadastral: dict[uuid.UUID, str] = (
        dict(
            (
                await session.execute(
                    select(Parcel.id, Parcel.cadastral_number).where(Parcel.id.in_(parcel_ids))
                )
            )
            .tuples()
            .all()
        )
        if parcel_ids
        else {}
    )
    subscribers: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(Subscription.target_id, func.count(Subscription.id))
                .where(
                    Subscription.target_type == SubscriptionTarget.APPLICATION,
                    Subscription.target_id.in_(ids),
                )
                .group_by(Subscription.target_id)
            )
        )
        .tuples()
        .all()
    )
    history = await audit.histories(session, EntityType.APPLICATION, ids)
    from app.services.land import parcels_of  # land imports this module

    chosen = await parcels_of(session, ids)
    return [
        ApplicationOut(
            id=str(a.id),
            tracking_number=a.tracking_number,
            applicant_name=a.applicant_name,
            type=a.type,
            status=a.status,
            status_comment_ru=a.status_comment_ru,
            status_comment_kk=a.status_comment_kk,
            inspection_date=a.inspection_date,
            parcel_id=str(a.parcel_id) if a.parcel_id else None,
            parcel_cadastral_number=cadastral.get(a.parcel_id) if a.parcel_id else None,
            submitted_at=a.submitted_at,
            updated_at=a.updated_at,
            subscribers_count=int(subscribers.get(a.id, 0)),
            allowed_transitions=allowed_transitions(EntityType.APPLICATION, a.status),
            history=history[a.id],
            source=a.source,
            applicant_iin_masked=a.applicant_iin_masked,
            applicant_phone_masked=a.applicant_phone_masked,
            applicant_comment=a.applicant_comment,
            parcels=chosen.get(a.id, []),
        )
        for a in applications
    ]


async def to_out(session: AsyncSession, application: Application) -> ApplicationOut:
    [out] = await to_out_many(session, [application])
    return out


async def list_applications(
    session: AsyncSession, *, statuses: list[ApplicationStatus], q: str | None
) -> ApplicationList:
    query = select(Application)
    if statuses:
        query = query.where(Application.status.in_(statuses))
    else:
        # Unconfirmed Mini App drafts are the citizen's business, not the akimat's.
        query = query.where(Application.status.not_in(CITIZEN_ONLY))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(Application.tracking_number.ilike(like) | Application.applicant_name.ilike(like))
    rows = list(await session.scalars(query.order_by(Application.submitted_at.desc())))
    return ApplicationList(items=await to_out_many(session, rows), total=len(rows))


async def transition(
    session: AsyncSession, application_id: uuid.UUID, request: ApplicationTransitionRequest, actor: str
) -> Application:
    application = await get_application(session, application_id, for_update=True)
    if application.status in CITIZEN_ONLY or request.to in (*CITIZEN_ONLY, ApplicationStatus.UNDER_REVIEW):
        # Drafts are confirmed or cancelled only by the citizen in Telegram.
        raise InvalidTransitionError(
            "Only the citizen can confirm or cancel a draft",
            details={"from": application.status.value, "to": request.to.value},
        )
    ensure_transition(EntityType.APPLICATION, application.status, request.to)
    previous = application.status
    application.status = request.to
    application.status_comment_ru = request.comment_ru
    application.status_comment_kk = request.comment_kk
    if request.inspection_date is not None:
        application.inspection_date = request.inspection_date
    application.updated_at = datetime.now(UTC)
    from app.services.land import apply_decision

    await apply_decision(session, application, request.grant_parcel_ids, actor)
    await audit.record_transition(
        session,
        entity_type=EntityType.APPLICATION,
        entity_id=application.id,
        from_status=previous,
        to_status=request.to,
        actor=actor,
        comment=request.comment_ru,
        meta={
            "comment_kk": request.comment_kk,
            **({"inspection_date": request.inspection_date.isoformat()} if request.inspection_date else {}),
        },
    )
    await audit.emit_event(
        session,
        EventType.APPLICATION_STATUS_CHANGED,
        {
            "application_id": str(application.id),
            "tracking_number": application.tracking_number,
            "from": previous.value,
            "to": request.to.value,
        },
    )
    await session.flush()
    await notifier.application_status_changed(session, application)
    return application


async def subscribe(
    session: AsyncSession, chat_id: int, lang: Lang, target: SubscriptionTarget, target_id: uuid.UUID
) -> bool:
    """Subscribe a chat to status updates. Returns False if it was already subscribed."""
    await session.execute(insert(TelegramUser).values(chat_id=chat_id, lang=lang).on_conflict_do_nothing())
    result = await session.execute(
        insert(Subscription)
        .values(chat_id=chat_id, target_type=target, target_id=target_id)
        .on_conflict_do_nothing(constraint="uq_subscriptions_target")
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def unsubscribe(
    session: AsyncSession, chat_id: int, target: SubscriptionTarget, target_id: uuid.UUID
) -> None:
    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.chat_id == chat_id,
            Subscription.target_type == target,
            Subscription.target_id == target_id,
        )
    )
    if subscription is not None:
        await session.delete(subscription)


async def subscribed_applications(session: AsyncSession, chat_id: int) -> list[Application]:
    return list(
        await session.scalars(
            select(Application)
            .join(
                Subscription,
                (Subscription.target_id == Application.id)
                & (Subscription.target_type == SubscriptionTarget.APPLICATION),
            )
            .where(Subscription.chat_id == chat_id)
            .order_by(Application.updated_at.desc())
        )
    )


async def is_subscribed(session: AsyncSession, chat_id: int, target_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.chat_id == chat_id, Subscription.target_id == target_id
            )
        )
    )
