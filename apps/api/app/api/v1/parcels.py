from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import CurrentInspector, DbSession, Storage
from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.enums import (
    EventType,
    Lang,
    ParcelPurpose,
    ParcelStatus,
    PhotoOwnerType,
    PhotoSource,
    ViolationType,
)
from app.providers.cadastre import get_cadastre_provider
from app.schemas.common import ERROR_RESPONSES, TRANSITION_RESPONSES
from app.schemas.parcels import (
    CadastreRecord,
    ParcelDetail,
    ParcelFeatureCollection,
    ParcelSearchResult,
    ParcelTransitionRequest,
    ParcelUpdateRequest,
)
from app.services import audit
from app.services import parcels as service
from app.services.act import build_act
from app.services.photos import PhotoSpec, save_photos

router = APIRouter(prefix="/parcels", tags=["parcels"], responses=ERROR_RESPONSES)

MAX_PHOTOS_PER_UPLOAD = 10


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    try:
        values = tuple(float(v) for v in raw.split(","))
    except ValueError as exc:
        raise ValidationFailedError("bbox must be 'minLon,minLat,maxLon,maxLat'") from exc
    if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
        raise ValidationFailedError("bbox must be 'minLon,minLat,maxLon,maxLat'")
    return values


@router.get("", response_model=ParcelFeatureCollection, summary="Parcels as GeoJSON FeatureCollection")
async def list_parcels(
    session: DbSession,
    _: CurrentInspector,
    bbox: Annotated[str | None, Query(description="minLon,minLat,maxLon,maxLat")] = None,
    status_: Annotated[list[ParcelStatus], Query(alias="status")] = [],  # noqa: B006
    violation_type: Annotated[list[ViolationType], Query()] = [],  # noqa: B006
    purpose: Annotated[list[ParcelPurpose], Query()] = [],  # noqa: B006
    overdue: bool | None = None,
) -> ParcelFeatureCollection:
    filters = service.ParcelFilters(
        bbox=parse_bbox(bbox),
        statuses=status_,
        violation_types=violation_type,
        purposes=purpose,
        overdue=overdue,
    )
    return await service.list_geojson(session, filters)


@router.get(
    "/search", response_model=list[ParcelSearchResult], summary="Search by cadastral number or address"
)
async def search_parcels(
    session: DbSession,
    _: CurrentInspector,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[ParcelSearchResult]:
    return await service.search(session, q)


@router.get("/{parcel_id}", response_model=ParcelDetail)
async def get_parcel(
    parcel_id: uuid.UUID, session: DbSession, storage: Storage, _: CurrentInspector
) -> ParcelDetail:
    return await service.get_detail(session, storage, parcel_id)


@router.patch("/{parcel_id}", response_model=ParcelDetail, summary="Update deadline / assigned inspector")
async def update_parcel(
    parcel_id: uuid.UUID,
    body: ParcelUpdateRequest,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
) -> ParcelDetail:
    await service.update(session, parcel_id, body, inspector.actor)
    return await service.get_detail(session, storage, parcel_id)


@router.post(
    "/{parcel_id}/transitions",
    response_model=ParcelDetail,
    responses=TRANSITION_RESPONSES,
    summary="Change parcel status (state machine)",
)
async def transition_parcel(
    parcel_id: uuid.UUID,
    body: ParcelTransitionRequest,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
) -> ParcelDetail:
    await service.transition(session, parcel_id, body, inspector.actor)
    return await service.get_detail(session, storage, parcel_id)


@router.post(
    "/{parcel_id}/photos",
    response_model=ParcelDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload inspector photos (multipart, up to 10 files)",
)
async def upload_parcel_photos(
    parcel_id: uuid.UUID,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
    files: Annotated[list[UploadFile], File(description="JPEG/PNG/WebP images")],
) -> ParcelDetail:
    parcel = await service.get_parcel(session, parcel_id)
    if not files:
        raise ValidationFailedError("At least one file is required")
    if len(files) > MAX_PHOTOS_PER_UPLOAD:
        raise ValidationFailedError(f"At most {MAX_PHOTOS_PER_UPLOAD} files per upload")
    specs = [
        PhotoSpec(
            PhotoOwnerType.PARCEL, parcel.id, await upload.read(), PhotoSource.INSPECTOR, inspector.actor
        )
        for upload in files
    ]
    await save_photos(session, storage, specs)
    await audit.emit_event(
        session,
        EventType.PHOTO_ADDED,
        {"owner_type": "PARCEL", "owner_id": str(parcel.id), "count": len(files)},
    )
    return await service.get_detail(session, storage, parcel_id)


@router.get(
    "/{parcel_id}/cadastre",
    response_model=CadastreRecord,
    summary="Reconcile with the state cadastre registry (ГБД ЗКС adapter, demo)",
)
async def cadastre_record(parcel_id: uuid.UUID, session: DbSession, _: CurrentInspector) -> CadastreRecord:
    parcel = await service.get_parcel(session, parcel_id)
    provider = get_cadastre_provider()
    record = await provider.get(session, parcel.cadastral_number)
    if record is None:
        raise NotFoundError("Registry record not found")
    return CadastreRecord.model_validate(record, from_attributes=True)


@router.get(
    "/{parcel_id}/act.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Inspection act (PDF) in the interface language",
)
async def inspection_act(
    parcel_id: uuid.UUID,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
    lang: Lang = Lang.RU,
) -> Response:
    filename, pdf = await build_act(session, storage, parcel_id, lang, inspector.name)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
