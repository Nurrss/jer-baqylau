"""Public endpoints (no login): act authenticity checks. Only non-personal data is exposed."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import func, select

from app.api.deps import DbSession, Storage
from app.core.errors import NotFoundError, ValidationFailedError
from app.db.models import Act, Parcel
from app.domain.enums import DeclaredUse
from app.schemas.common import ERROR_RESPONSES, LngLat
from app.schemas.inspections import InspectionPublic, InspectionSubmitted
from app.schemas.misc import ActPublic, ChainCheck
from app.services import audit
from app.services import inspections as inspection_service

router = APIRouter(prefix="/public", tags=["public"], responses=ERROR_RESPONSES)


@router.get("/acts/{act_id}", response_model=ActPublic, summary="Verify a printed act by its QR code")
async def verify_act(act_id: uuid.UUID, session: DbSession) -> ActPublic:
    act = await session.get(Act, act_id)
    if act is None:
        raise NotFoundError("Act is not registered", code="ACT_NOT_FOUND")
    chain = await audit.verify_chain(session, up_to_length=act.chain_length)
    return ActPublic(
        number=act.number,
        issued_at=act.created_at,
        cadastral_number=act.cadastral_number,
        parcel_status=act.parcel_status,
        lang=act.lang.value,
        issued_by=act.issued_by,
        pdf_sha256=act.pdf_sha256,
        photo_count=len(act.photo_hashes),
        chain_at_issue=ChainCheck(
            intact=chain.intact and chain.length == act.chain_length and chain.head == act.chain_head,
            length=chain.length,
            head=chain.head,
            broken_at_id=chain.broken_at_id,
        ),
    )


@router.get(
    "/inspections/{token}", response_model=InspectionPublic, summary="Owner: open a photo-report request"
)
async def open_inspection(token: str, session: DbSession) -> InspectionPublic:
    request = await inspection_service.get_by_token(session, token)
    row = (
        await session.execute(
            select(
                Parcel,
                func.ST_AsGeoJSON(Parcel.geometry, 6),
                func.ST_X(Parcel.centroid),
                func.ST_Y(Parcel.centroid),
            ).where(Parcel.id == request.parcel_id)
        )
    ).one()
    parcel, geojson, lon, lat = row
    return InspectionPublic(
        code=request.code,
        status=request.status,
        cadastral_number=parcel.cadastral_number,
        address_ru=parcel.address_ru,
        address_kk=parcel.address_kk,
        purpose=parcel.purpose,
        due_at=request.due_at,
        note=None if request.reason.value != "MANUAL" else request.note,
        centroid=LngLat(lon=lon, lat=lat),
        parcel=json.loads(geojson),
    )


@router.post(
    "/inspections/{token}",
    response_model=InspectionSubmitted,
    summary="Owner: submit live camera photos with the device position (anti-fraud checks run server-side)",
)
async def submit_inspection(
    token: str,
    session: DbSession,
    storage: Storage,
    files: Annotated[list[UploadFile], File(description="1–5 JPEG photos captured by the camera")],
    captured_at: Annotated[list[str], Form(description="ISO time of each capture, same order as files")],
    lat: Annotated[float, Form()],
    lon: Annotated[float, Form()],
    accuracy: Annotated[float, Form(description="GPS accuracy, metres")],
    declared_use: Annotated[DeclaredUse, Form()],
    comment: Annotated[str | None, Form(max_length=1000)] = None,
) -> InspectionSubmitted:
    try:
        times = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in captured_at]
    except ValueError as exc:
        raise ValidationFailedError("captured_at must be ISO datetimes") from exc
    request = await inspection_service.submit(
        session,
        storage,
        token,
        files=[await f.read() for f in files],
        captured_at=times,
        lat=lat,
        lon=lon,
        accuracy=accuracy,
        declared_use=declared_use,
        comment=comment,
    )
    # The verdict is for the inspector only — revealing it would teach how to game the checks.
    return InspectionSubmitted(code=request.code, status=request.status, photos=len(files))
