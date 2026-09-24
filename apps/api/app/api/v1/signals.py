from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentInspector, DbSession, Storage
from app.domain.enums import SignalStatus
from app.schemas.common import ERROR_RESPONSES, TRANSITION_RESPONSES
from app.schemas.signals import SignalDetail, SignalList, SignalTransitionRequest
from app.services import signals as service

router = APIRouter(prefix="/signals", tags=["signals"], responses=ERROR_RESPONSES)


@router.get("", response_model=SignalList, summary="Signals queue (open first, newest on top)")
async def list_signals(
    session: DbSession,
    storage: Storage,
    _: CurrentInspector,
    status_: Annotated[list[SignalStatus], Query(alias="status")] = [],  # noqa: B006
    include_duplicates: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SignalList:
    return await service.list_signals(
        session, storage, statuses=status_, include_duplicates=include_duplicates, limit=limit, offset=offset
    )


@router.get("/{signal_id}", response_model=SignalDetail)
async def get_signal(
    signal_id: uuid.UUID, session: DbSession, storage: Storage, _: CurrentInspector
) -> SignalDetail:
    return await service.get_detail(session, storage, signal_id)


@router.post(
    "/{signal_id}/transitions",
    response_model=SignalDetail,
    responses=TRANSITION_RESPONSES,
    summary="Take into work / confirm (parcel → VIOLATION) / reject; the citizen is notified",
)
async def transition_signal(
    signal_id: uuid.UUID,
    body: SignalTransitionRequest,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
) -> SignalDetail:
    await service.transition(session, signal_id, body, inspector.actor)
    return await service.get_detail(session, storage, signal_id)
