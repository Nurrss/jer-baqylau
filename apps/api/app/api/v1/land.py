"""State land fund: the citizens' Telegram Mini App and the inspector's offer/withdraw actions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query

from app.api.deps import CurrentInspector, DbSession
from app.core.telegram_webapp import WebAppUser, validate_init_data
from app.domain.enums import AllocationStatus, Lang
from app.schemas.common import ERROR_RESPONSES, ApiModel
from app.schemas.land import LandApplicationCreate, LandApplicationDraft, LandFund, MiniAppApplication
from app.services import land as service

router = APIRouter(tags=["land fund"], responses=ERROR_RESPONSES)

InitData = Annotated[
    str | None,
    Header(alias="X-Telegram-Init-Data", description="Telegram.WebApp.initData of the Mini App"),
]


class OfferOut(ApiModel):
    parcel_id: str
    allocation_status: AllocationStatus


def _user(init_data: str | None) -> WebAppUser:
    return validate_init_data(init_data)


@router.get("/land/fund", response_model=LandFund, summary="Free state land on the map (public)")
async def land_fund(session: DbSession) -> LandFund:
    return await service.fund(session)


@router.post(
    "/miniapp/applications",
    response_model=LandApplicationDraft,
    status_code=201,
    summary="Form an application in the Mini App; the bot then asks to confirm it in Telegram",
)
async def create_application(
    body: LandApplicationCreate,
    session: DbSession,
    init_data: InitData = None,
    lang: Annotated[Lang | None, Query()] = None,
) -> LandApplicationDraft:
    user = _user(init_data)
    application, parcels = await service.create_draft(session, user, body, lang or user.lang)
    return LandApplicationDraft(
        id=str(application.id),
        tracking_number=application.tracking_number,
        status=application.status,
        type=application.type,
        parcels=len(parcels),
    )


@router.get(
    "/miniapp/applications",
    response_model=list[MiniAppApplication],
    summary="The citizen's own land applications (Mini App)",
)
async def my_applications(session: DbSession, init_data: InitData = None) -> list[MiniAppApplication]:
    return await service.my_applications(session, _user(init_data).id)


@router.post(
    "/parcels/{parcel_id}/offer",
    response_model=OfferOut,
    summary="Offer a state-owned parcel to citizens (it appears in the Mini App)",
)
async def offer_parcel(parcel_id: uuid.UUID, session: DbSession, inspector: CurrentInspector) -> OfferOut:
    parcel = await service.offer(session, parcel_id, inspector.actor, offered=True)
    return OfferOut(parcel_id=str(parcel.id), allocation_status=parcel.allocation_status)


@router.delete(
    "/parcels/{parcel_id}/offer",
    response_model=OfferOut,
    summary="Withdraw a parcel from the land fund",
)
async def withdraw_parcel(parcel_id: uuid.UUID, session: DbSession, inspector: CurrentInspector) -> OfferOut:
    parcel = await service.offer(session, parcel_id, inspector.actor, offered=False)
    return OfferOut(parcel_id=str(parcel.id), allocation_status=parcel.allocation_status)
