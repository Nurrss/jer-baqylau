from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentInspector, DbSession
from app.domain.enums import ApplicationStatus
from app.schemas.common import ERROR_RESPONSES, TRANSITION_RESPONSES
from app.schemas.misc import ApplicationList, ApplicationOut, ApplicationTransitionRequest
from app.services import applications as service

router = APIRouter(prefix="/applications", tags=["applications"], responses=ERROR_RESPONSES)


@router.get("", response_model=ApplicationList)
async def list_applications(
    session: DbSession,
    _: CurrentInspector,
    status_: Annotated[list[ApplicationStatus], Query(alias="status")] = [],  # noqa: B006
    q: Annotated[str | None, Query(max_length=64)] = None,
) -> ApplicationList:
    return await service.list_applications(session, statuses=status_, q=q)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID, session: DbSession, _: CurrentInspector
) -> ApplicationOut:
    return await service.to_out(session, await service.get_application(session, application_id))


@router.post(
    "/{application_id}/transitions",
    response_model=ApplicationOut,
    responses=TRANSITION_RESPONSES,
    summary="Change application status with RU/KZ explanation; subscribers get a Telegram push",
)
async def transition_application(
    application_id: uuid.UUID,
    body: ApplicationTransitionRequest,
    session: DbSession,
    inspector: CurrentInspector,
) -> ApplicationOut:
    application = await service.transition(session, application_id, body, inspector.actor)
    return await service.to_out(session, application)
