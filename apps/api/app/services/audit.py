"""Audit log (status_transitions, hash-chained) and domain events (events → realtime)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models import Event, StatusTransition
from app.domain.audit_chain import GENESIS_HASH, transition_hash
from app.domain.enums import EntityType, EventType
from app.schemas.common import TransitionOut

CHAIN_LOCK_ID = 724003
_HEAD_KEY = "audit_chain_head"


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
@event.listens_for(Session, "after_soft_rollback")
def _forget_head(session: Session, *args: Any) -> None:
    # The cached chain head is only valid inside the transaction that holds the chain lock.
    session.info.pop(_HEAD_KEY, None)


async def _chain_head(session: AsyncSession) -> str:
    head = session.sync_session.info.get(_HEAD_KEY)
    if head is None:
        # Serialize writers: the chain must be strictly linear across concurrent transactions.
        await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": CHAIN_LOCK_ID})
        head = await session.scalar(
            select(StatusTransition.hash)
            .where(StatusTransition.hash.is_not(None))
            .order_by(StatusTransition.id.desc())
            .limit(1)
        )
    return str(head or GENESIS_HASH)


async def link_to_chain(session: AsyncSession, row: StatusTransition) -> StatusTransition:
    """Fill ``prev_hash``/``hash`` of a new audit row and add it to the session."""
    if row.created_at is None:
        row.created_at = datetime.now(UTC)
    if row.meta is None:
        row.meta = {}
    prev = await _chain_head(session)
    row.prev_hash = prev
    row.hash = transition_hash(
        prev,
        entity_type=row.entity_type.value,
        entity_id=str(row.entity_id),
        from_status=row.from_status,
        to_status=row.to_status,
        actor=row.actor,
        comment=row.comment,
        meta=row.meta,
        created_at=row.created_at,
    )
    session.sync_session.info[_HEAD_KEY] = row.hash
    session.add(row)
    return row


@dataclass(frozen=True, slots=True)
class ChainStatus:
    intact: bool
    length: int
    head: str
    broken_at_id: int | None = None


async def verify_chain(session: AsyncSession, up_to_length: int | None = None) -> ChainStatus:
    """Recompute every link; the first mismatch means the log was altered after the fact."""
    prev = GENESIS_HASH
    length = 0
    query = select(StatusTransition).order_by(StatusTransition.id)
    if up_to_length is not None:
        query = query.limit(up_to_length)
    result = await session.stream_scalars(query.execution_options(yield_per=500))
    async for row in result:
        expected = transition_hash(
            prev,
            entity_type=row.entity_type.value,
            entity_id=str(row.entity_id),
            from_status=row.from_status,
            to_status=row.to_status,
            actor=row.actor,
            comment=row.comment,
            meta=row.meta,
            created_at=row.created_at,
        )
        if row.prev_hash != prev or row.hash != expected:
            return ChainStatus(intact=False, length=length, head=prev, broken_at_id=row.id)
        prev = expected
        length += 1
    return ChainStatus(intact=True, length=length, head=prev)


async def chain_state(session: AsyncSession) -> tuple[str, int]:
    """Current head hash and length (for stamping acts)."""
    head = await session.scalar(
        select(StatusTransition.hash)
        .where(StatusTransition.hash.is_not(None))
        .order_by(StatusTransition.id.desc())
        .limit(1)
    )
    length = await session.scalar(select(func.count(StatusTransition.id)))
    return str(head or GENESIS_HASH), int(length or 0)


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
    return await link_to_chain(session, row)


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
