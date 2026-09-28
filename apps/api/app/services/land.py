"""State land fund: free parcels, Mini App applications confirmed in Telegram, allocation.

Flow: the citizen picks one or more free parcels in the Mini App → a DRAFT application is created
and the bot asks to confirm it → on confirmation the parcels are RESERVED and the application goes
to the akimat panel (UNDER_REVIEW) → the inspector approves (the chosen parcels are ALLOCATED to the
citizen, linked to their Telegram) or rejects (the parcels return to the fund).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.core.telegram_webapp import WebAppUser
from app.db.models import Application, ApplicationParcel, Parcel, TelegramUser
from app.domain import person
from app.domain.enums import (
    AllocationStatus,
    ApplicationStatus,
    ApplicationType,
    EntityType,
    EventType,
    Lang,
    OwnerType,
    ParcelPurpose,
    ParcelStatus,
    SubscriptionTarget,
)
from app.domain.state_machine import ensure_transition
from app.schemas.land import (
    ApplicationParcelOut,
    LandApplicationCreate,
    LandFund,
    MiniAppApplication,
)
from app.services import applications as application_service
from app.services import audit, notifier

MAX_ACTIVE_PER_CITIZEN = 3
AGRO_LEASE_YEARS = 10
ACTIVE = (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INSPECTION_SCHEDULED)

# What a citizen can apply for, by the purpose of the fund parcel.
TYPE_BY_PURPOSE: dict[ParcelPurpose, ApplicationType] = {
    ParcelPurpose.IZHS: ApplicationType.IZHS_ALLOCATION,
    ParcelPurpose.LPH: ApplicationType.IZHS_ALLOCATION,
    ParcelPurpose.AGRICULTURE: ApplicationType.AGRO_LEASE,
}


def _citizen(chat_id: int) -> str:
    return f"citizen:{chat_id}"


# ── Fund on the map ─────────────────────────────────────────────────────────


async def fund(session: AsyncSession) -> LandFund:
    rows = (
        await session.execute(
            select(
                Parcel.id,
                Parcel.cadastral_number,
                Parcel.area_ha,
                Parcel.purpose,
                Parcel.address_ru,
                Parcel.address_kk,
                Parcel.district,
                Parcel.allocation_status,
                func.ST_AsGeoJSON(Parcel.geometry, 7),
                func.ST_X(Parcel.centroid),
                func.ST_Y(Parcel.centroid),
            )
            .where(Parcel.allocation_status.in_([AllocationStatus.OFFERED, AllocationStatus.RESERVED]))
            .order_by(Parcel.cadastral_number)
        )
    ).all()
    features = [
        {
            "type": "Feature",
            "id": str(pid),
            "geometry": json.loads(geojson),
            "properties": {
                "id": str(pid),
                "cadastral_number": number,
                "area_ha": float(area),
                "purpose": purpose.value,
                "application_type": TYPE_BY_PURPOSE[purpose].value if purpose in TYPE_BY_PURPOSE else None,
                "address_ru": address_ru,
                "address_kk": address_kk,
                "district": district,
                "allocation_status": allocation.value,
                "lon": lon,
                "lat": lat,
            },
        }
        for pid, number, area, purpose, address_ru, address_kk, district, allocation, geojson, lon, lat in rows
    ]
    offered = sum(1 for f in features if f["properties"]["allocation_status"] == AllocationStatus.OFFERED)
    return LandFund(features=features, offered=offered, reserved=len(features) - offered)


async def offer(session: AsyncSession, parcel_id: uuid.UUID, actor: str, *, offered: bool) -> Parcel:
    """Put a state-owned parcel into the fund (or take it back)."""
    parcel = await session.scalar(select(Parcel).where(Parcel.id == parcel_id).with_for_update())
    if parcel is None:
        raise NotFoundError("Parcel not found", details={"parcel_id": str(parcel_id)})
    if offered:
        if parcel.owner_type is not OwnerType.STATE or parcel.allocation_status is not AllocationStatus.NONE:
            raise ConflictError("Only free state land can be offered", code="PARCEL_NOT_STATE_OWNED")
        if parcel.purpose not in TYPE_BY_PURPOSE:
            raise ConflictError("This land use cannot be offered to citizens", code="PURPOSE_NOT_OFFERABLE")
        parcel.allocation_status = AllocationStatus.OFFERED
    else:
        if parcel.allocation_status is not AllocationStatus.OFFERED:
            raise ConflictError("Only an offered parcel can be withdrawn", code="PARCEL_NOT_OFFERED")
        parcel.allocation_status = AllocationStatus.NONE
    parcel.updated_at = datetime.now(UTC)
    await audit.emit_event(
        session,
        EventType.PARCEL_UPDATED,
        {"parcel_id": str(parcel.id), "allocation_status": parcel.allocation_status.value, "actor": actor},
    )
    await session.flush()
    return parcel


# ── Mini App: draft → confirmation in Telegram ──────────────────────────────


async def create_draft(
    session: AsyncSession, user: WebAppUser, body: LandApplicationCreate, lang: Lang
) -> tuple[Application, list[Parcel]]:
    if not person.iin_is_valid(body.iin):
        raise ValidationFailedError("IIN is invalid", code="IIN_INVALID")
    phone = person.normalize_phone(body.phone)
    if phone is None:
        raise ValidationFailedError("Phone must be a Kazakhstan mobile number", code="PHONE_INVALID")

    by_id = {p.id: p for p in await session.scalars(select(Parcel).where(Parcel.id.in_(body.parcel_ids)))}
    parcels = [by_id[pid] for pid in body.parcel_ids if pid in by_id]
    if len(parcels) != len(body.parcel_ids):
        raise NotFoundError("Parcel not found", code="PARCEL_NOT_FOUND")
    taken = [p.cadastral_number for p in parcels if p.allocation_status is not AllocationStatus.OFFERED]
    if taken:
        raise ConflictError(
            "Some parcels are no longer free", code="PARCEL_TAKEN", details={"parcels": taken}
        )
    types = {TYPE_BY_PURPOSE.get(p.purpose) for p in parcels}
    if len(types) != 1 or None in types:
        raise ValidationFailedError(
            "Choose parcels of one kind: housing or agricultural", code="PARCELS_MIXED_PURPOSE"
        )
    active = await session.scalar(
        select(func.count(Application.id)).where(
            Application.applicant_chat_id == user.id, Application.status.in_(ACTIVE)
        )
    )
    if (active or 0) >= MAX_ACTIVE_PER_CITIZEN:
        raise ConflictError("Too many applications under review", code="TOO_MANY_APPLICATIONS")

    # A new draft replaces an unconfirmed previous one.
    await session.execute(
        update(Application)
        .where(Application.applicant_chat_id == user.id, Application.status == ApplicationStatus.DRAFT)
        .values(status=ApplicationStatus.CANCELLED, updated_at=datetime.now(UTC))
    )
    await session.execute(
        insert(TelegramUser)
        .values(chat_id=user.id, lang=lang)
        .on_conflict_do_update(index_elements=[TelegramUser.chat_id], set_={"lang": lang})
    )
    now = datetime.now(UTC)
    seq = int(await session.scalar(select(func.nextval("application_number_seq"))) or 0)
    application = Application(
        id=uuid.uuid4(),
        tracking_number=f"KZ-{now:%Y}-{seq:03d}",
        applicant_name=person.mask_name(body.full_name),
        type=types.pop(),
        status=ApplicationStatus.DRAFT,
        parcel_id=parcels[0].id,
        submitted_at=now,
        source="miniapp",
        applicant_chat_id=user.id,
        applicant_iin_masked=person.mask_iin(body.iin),
        applicant_phone_masked=person.mask_phone(phone),
        applicant_comment=(body.comment or "").strip() or None,
    )
    session.add(application)
    await session.flush()
    session.add_all(
        ApplicationParcel(application_id=application.id, parcel_id=p.id, priority=i)
        for i, p in enumerate(parcels, start=1)
    )
    await audit.record_transition(
        session,
        entity_type=EntityType.APPLICATION,
        entity_id=application.id,
        from_status=None,
        to_status=ApplicationStatus.DRAFT,
        actor=_citizen(user.id),
        comment=None,
        meta={"source": "miniapp", "parcels": [p.cadastral_number for p in parcels]},
    )
    await session.flush()
    await notifier.land_application_draft(session, application, parcels)
    return application, parcels


async def _own_draft(session: AsyncSession, application_id: uuid.UUID, chat_id: int) -> Application:
    application = await session.scalar(
        select(Application).where(Application.id == application_id).with_for_update()
    )
    if application is None:
        raise NotFoundError("Application not found")
    if application.applicant_chat_id != chat_id:
        raise ForbiddenError("Not your application")
    return application


async def _chosen(session: AsyncSession, application_id: uuid.UUID, *, lock: bool = False) -> list[Parcel]:
    query = (
        select(Parcel)
        .join(ApplicationParcel, ApplicationParcel.parcel_id == Parcel.id)
        .where(ApplicationParcel.application_id == application_id)
        .order_by(ApplicationParcel.priority)
    )
    if lock:
        query = query.with_for_update(of=Parcel)
    return list(await session.scalars(query))


async def confirm(session: AsyncSession, application_id: uuid.UUID, chat_id: int, lang: Lang) -> Application:
    """The citizen confirmed in Telegram: reserve the parcels and send the application to the akimat."""
    application = await _own_draft(session, application_id, chat_id)
    if application.status is not ApplicationStatus.DRAFT:
        return application  # repeated tap on the button
    parcels = await _chosen(session, application.id, lock=True)
    taken = [p.cadastral_number for p in parcels if p.allocation_status is not AllocationStatus.OFFERED]
    if taken:
        raise ConflictError(
            "Some parcels are no longer free", code="PARCEL_TAKEN", details={"parcels": taken}
        )
    ensure_transition(EntityType.APPLICATION, application.status, ApplicationStatus.UNDER_REVIEW)
    now = datetime.now(UTC)
    for parcel in parcels:
        parcel.allocation_status = AllocationStatus.RESERVED
        parcel.updated_at = now
    application.status = ApplicationStatus.UNDER_REVIEW
    application.submitted_at = now
    application.updated_at = now
    await audit.record_transition(
        session,
        entity_type=EntityType.APPLICATION,
        entity_id=application.id,
        from_status=ApplicationStatus.DRAFT,
        to_status=ApplicationStatus.UNDER_REVIEW,
        actor=_citizen(chat_id),
        comment=None,
        meta={"confirmed_in": "telegram"},
    )
    await application_service.subscribe(
        session, chat_id, lang, SubscriptionTarget.APPLICATION, application.id
    )
    await audit.emit_event(
        session,
        EventType.APPLICATION_SUBMITTED,
        {
            "application_id": str(application.id),
            "tracking_number": application.tracking_number,
            "type": application.type.value,
            "parcels": [p.cadastral_number for p in parcels],
            "applicant": application.applicant_name,
        },
    )
    for parcel in parcels:
        await audit.emit_event(
            session,
            EventType.PARCEL_UPDATED,
            {"parcel_id": str(parcel.id), "allocation_status": parcel.allocation_status.value},
        )
    await session.flush()
    return application


async def cancel(session: AsyncSession, application_id: uuid.UUID, chat_id: int) -> Application:
    application = await _own_draft(session, application_id, chat_id)
    if application.status is not ApplicationStatus.DRAFT:
        return application
    application.status = ApplicationStatus.CANCELLED
    application.updated_at = datetime.now(UTC)
    await audit.record_transition(
        session,
        entity_type=EntityType.APPLICATION,
        entity_id=application.id,
        from_status=ApplicationStatus.DRAFT,
        to_status=ApplicationStatus.CANCELLED,
        actor=_citizen(chat_id),
        comment=None,
    )
    await session.flush()
    return application


async def my_applications(session: AsyncSession, chat_id: int) -> list[MiniAppApplication]:
    apps = list(
        await session.scalars(
            select(Application)
            .where(
                Application.applicant_chat_id == chat_id, Application.status != ApplicationStatus.CANCELLED
            )
            .order_by(Application.created_at.desc())
            .limit(20)
        )
    )
    parcels = await parcels_of(session, [a.id for a in apps])
    return [
        MiniAppApplication(
            tracking_number=a.tracking_number, status=a.status, type=a.type, parcels=parcels.get(a.id, [])
        )
        for a in apps
    ]


async def parcels_of(
    session: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ApplicationParcelOut]]:
    if not application_ids:
        return {}
    rows = await session.execute(
        select(ApplicationParcel, Parcel)
        .join(Parcel, Parcel.id == ApplicationParcel.parcel_id)
        .where(ApplicationParcel.application_id.in_(application_ids))
        .order_by(ApplicationParcel.application_id, ApplicationParcel.priority)
    )
    result: dict[uuid.UUID, list[ApplicationParcelOut]] = {}
    for link, parcel in rows.tuples():
        result.setdefault(link.application_id, []).append(
            ApplicationParcelOut(
                id=str(parcel.id),
                cadastral_number=parcel.cadastral_number,
                area_ha=float(parcel.area_ha),
                purpose=parcel.purpose,
                priority=link.priority,
                granted=link.granted,
                allocation_status=parcel.allocation_status,
            )
        )
    return result


# ── Decision in the panel ───────────────────────────────────────────────────


async def apply_decision(
    session: AsyncSession, application: Application, grant_ids: list[uuid.UUID] | None, actor: str
) -> None:
    """Called from the application transition: allocate or release the fund parcels."""
    links = list(
        await session.scalars(
            select(ApplicationParcel)
            .where(ApplicationParcel.application_id == application.id)
            .order_by(ApplicationParcel.priority)
        )
    )
    if not links:
        return
    parcels = {p.id: p for p in await _chosen(session, application.id, lock=True)}
    now = datetime.now(UTC)
    if application.status is ApplicationStatus.APPROVED:
        if grant_ids is None:
            # Housing: one parcel per citizen (the first choice); agricultural lease: all fields.
            grant_ids = (
                [links[0].parcel_id]
                if application.type is ApplicationType.IZHS_ALLOCATION
                else [link.parcel_id for link in links]
            )
        chosen = set(grant_ids)
        if not chosen or not chosen <= set(parcels):
            raise ValidationFailedError("Choose parcels from the application", code="GRANT_PARCELS_INVALID")
    elif application.status is ApplicationStatus.REJECTED:
        chosen = set()
    else:
        return
    for link in links:
        parcel = parcels[link.parcel_id]
        if link.parcel_id in chosen:
            link.granted = True
            parcel.allocation_status = AllocationStatus.ALLOCATED
            parcel.owner_chat_id = application.applicant_chat_id
            if application.type is ApplicationType.AGRO_LEASE:
                parcel.owner_type = OwnerType.LEASE
                parcel.lease_until = date(now.year + AGRO_LEASE_YEARS, now.month, 1) - timedelta(days=1)
            else:
                parcel.owner_type = OwnerType.PRIVATE
            if parcel.status is ParcelStatus.RETURNED_TO_STATE:
                # Re-allocation is the one exit from "returned to state"; it is not an inspector action,
                # so it is not in the state machine, but it is logged in the hash chain like any change.
                parcel.status = ParcelStatus.OK
                parcel.violation_type = None
                parcel.deadline_at = None
                await audit.record_transition(
                    session,
                    entity_type=EntityType.PARCEL,
                    entity_id=parcel.id,
                    from_status=ParcelStatus.RETURNED_TO_STATE,
                    to_status=ParcelStatus.OK,
                    actor=actor,
                    comment=application.tracking_number,
                    meta={"reason": "allocated", "application_id": str(application.id)},
                )
        elif parcel.allocation_status is AllocationStatus.RESERVED:
            parcel.allocation_status = AllocationStatus.OFFERED
        parcel.updated_at = now
        await audit.emit_event(
            session,
            EventType.PARCEL_UPDATED,
            {"parcel_id": str(parcel.id), "allocation_status": parcel.allocation_status.value},
        )
