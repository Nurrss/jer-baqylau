"""Audit log (status_transitions) and domain events (events → realtime)."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, StatusTransition
from app.domain.enums import EntityType, EventType
from app.schemas.common import TransitionOut


async def record_transition(
    session: AsyncSession,
    *,
    entity_type: EntityType,
    entity_id: uuid.UUID,
    from_status: StrEnum | None,
    to_status: StrEnum,
    actor: str,
    comment: str | None,
    meta: dict[str, Any] | None = None,
) -> StatusTransition:
    row = StatusTransition(
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        actor=actor,
        comment=comment,
        meta=meta or {},
    )
    session.add(row)
    return row


async def emit_event(session: AsyncSession, event_type: EventType, payload: dict[str, Any]) -> Event:
    row = Event(type=event_type.value, payload=payload)
    session.add(row)
    return row


async def history(
    session: AsyncSession, entity_type: EntityType, entity_id: uuid.UUID
) -> list[TransitionOut]:
    rows = await session.scalars(
        select(StatusTransition)
        .where(StatusTransition.entity_type == entity_type, StatusTransition.entity_id == entity_id)
        .order_by(StatusTransition.created_at.desc(), StatusTransition.id.desc())
    )
    return [TransitionOut.model_validate(row) for row in rows]
