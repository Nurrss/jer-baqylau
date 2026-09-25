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


async def histories(
    session: AsyncSession, entity_type: EntityType, entity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[TransitionOut]]:
    """Histories of many entities in one query (newest first)."""
    result: dict[uuid.UUID, list[TransitionOut]] = {entity_id: [] for entity_id in entity_ids}
    if not entity_ids:
        return result
    rows = await session.scalars(
        select(StatusTransition)
        .where(StatusTransition.entity_type == entity_type, StatusTransition.entity_id.in_(entity_ids))
        .order_by(StatusTransition.created_at.desc(), StatusTransition.id.desc())
    )
    for row in rows:
        result[row.entity_id].append(TransitionOut.model_validate(row))
    return result
