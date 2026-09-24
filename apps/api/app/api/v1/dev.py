"""Service endpoints protected by X-Service-Key: e2e smoke tests and the demo "plan B"."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DbSession, Storage, service_key
from app.db.models import Parcel, Signal
from app.domain.enums import PhotoSource
from app.schemas.common import ERROR_RESPONSES
from app.schemas.misc import DemoResetResponse
from app.schemas.signals import SimulateSignalRequest, SimulateSignalResponse
from app.seed import loader
from app.services import signals as signal_service
from app.services.placeholders import placeholder_photo

router = APIRouter(
    prefix="/dev", tags=["dev"], dependencies=[Depends(service_key)], responses=ERROR_RESPONSES
)


@router.post(
    "/simulate-signal",
    response_model=SimulateSignalResponse,
    summary="Create a signal exactly as the bot would (for e2e tests and demo fallback)",
)
async def simulate_signal(
    body: SimulateSignalRequest, session: DbSession, storage: Storage
) -> SimulateSignalResponse:
    signal = await signal_service.create_signal(
        session,
        lat=body.lat,
        lon=body.lon,
        category=body.category,
        description=body.description,
        reporter_chat_id=body.chat_id,
        reporter_lang=body.lang,
        actor="service:simulate",
        enforce_rate_limit=False,
    )
    photos = [placeholder_photo(f"{signal.tracking_code}:{i}", body.category) for i in range(body.photos)]
    await signal_service.attach_photos(
        session, storage, signal.id, photos, "service:simulate", PhotoSource.CITIZEN
    )
    [summary] = await signal_service.summaries(session, storage, select(Signal).where(Signal.id == signal.id))
    parcel_status = (
        await session.scalar(select(Parcel.status).where(Parcel.id == signal.parcel_id))
        if signal.parcel_id
        else None
    )
    return SimulateSignalResponse(
        signal=summary, parcel_status=parcel_status.value if parcel_status else None
    )


@router.post("/demo-reset", response_model=DemoResetResponse, summary="Wipe domain data and re-seed the demo")
async def demo_reset(session: DbSession, storage: Storage) -> DemoResetResponse:
    return await loader.reset(session, storage)
