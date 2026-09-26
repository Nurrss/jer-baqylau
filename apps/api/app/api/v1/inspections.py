"""Remote inspections, risk ranking and the inspection plan (inspector side)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentInspector, DbSession, Storage
from app.db.models import InspectionRequest, Parcel
from app.domain.enums import InspectionReason, InspectionStatus, PhotoOwnerType
from app.providers.storage import StorageProvider
from app.schemas.common import ERROR_RESPONSES, TRANSITION_RESPONSES, LngLat
from app.schemas.inspections import (
    CheckOut,
    InspectionCreate,
    InspectionList,
    InspectionOut,
    InspectionReview,
    PlanOut,
    PlanRequest,
    RiskFactorOut,
    RiskItem,
)
from app.services import inspections as service
from app.services import risk as risk_service
from app.services.crosscheck import CrossCheck, crosscheck
from app.services.evidence import ResolutionEvidence, resolution_evidence
from app.services.photos import photos_for

router = APIRouter(tags=["inspections"], responses=ERROR_RESPONSES)


async def to_out(
    session: AsyncSession, storage: StorageProvider, requests: list[InspectionRequest]
) -> list[InspectionOut]:
    if not requests:
        return []
    ids = [r.id for r in requests]
    cadastral = dict(
        (
            await session.execute(
                select(Parcel.id, Parcel.cadastral_number).where(
                    Parcel.id.in_({r.parcel_id for r in requests})
                )
            )
        )
        .tuples()
        .all()
    )
    device = {
        rid: (x, y)
        for rid, x, y in await session.execute(
            select(
                InspectionRequest.id,
                func.ST_X(InspectionRequest.device_location),
                func.ST_Y(InspectionRequest.device_location),
            ).where(InspectionRequest.id.in_(ids), InspectionRequest.device_location.is_not(None))
        )
    }
    photos = await photos_for(session, storage, PhotoOwnerType.INSPECTION, ids)
    return [
        InspectionOut(
            id=str(r.id),
            code=r.code,
            parcel_id=str(r.parcel_id),
            cadastral_number=cadastral.get(r.parcel_id, ""),
            status=r.status,
            reason=r.reason,
            verdict=r.verdict,
            note=r.note,
            requested_by=r.requested_by,
            due_at=r.due_at,
            created_at=r.created_at,
            submitted_at=r.submitted_at,
            declared_use=r.declared_use,
            owner_comment=r.owner_comment,
            device=LngLat(lon=device[r.id][0], lat=device[r.id][1]) if r.id in device else None,
            accuracy_m=r.accuracy_m,
            checks=[CheckOut.model_validate(c) for c in r.checks],
            reviewed_by=r.reviewed_by,
            review_comment=r.review_comment,
            reviewed_at=r.reviewed_at,
            link=service.public_link(r) if r.status is InspectionStatus.REQUESTED else None,
            photos=photos.get(r.id, []),
        )
        for r in requests
    ]


@router.post(
    "/parcels/{parcel_id}/inspection-requests",
    response_model=InspectionOut,
    status_code=201,
    summary="Ask the owner for a photo report (returns the one-time link)",
)
async def request_inspection(
    parcel_id: uuid.UUID,
    body: InspectionCreate,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
) -> InspectionOut:
    request = await service.create_request(
        session,
        parcel_id,
        reason=InspectionReason.MANUAL,
        actor=inspector.actor,
        due_hours=body.due_hours,
        note=body.note,
    )
    [out] = await to_out(session, storage, [request])
    return out


@router.get("/inspection-requests", response_model=InspectionList)
async def list_inspections(
    session: DbSession,
    storage: Storage,
    _: CurrentInspector,
    status_: Annotated[list[InspectionStatus], Query(alias="status")] = [],  # noqa: B006
    parcel_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> InspectionList:
    query = select(InspectionRequest)
    if status_:
        query = query.where(InspectionRequest.status.in_(status_))
    if parcel_id:
        query = query.where(InspectionRequest.parcel_id == parcel_id)
    rows = list(await session.scalars(query.order_by(InspectionRequest.created_at.desc()).limit(limit)))
    for row in rows:
        await service.expire_if_due(session, row)
    return InspectionList(items=await to_out(session, storage, rows), total=len(rows))


@router.get("/inspection-requests/{request_id}", response_model=InspectionOut)
async def get_inspection(
    request_id: uuid.UUID, session: DbSession, storage: Storage, _: CurrentInspector
) -> InspectionOut:
    [out] = await to_out(session, storage, [await service.get_request(session, request_id)])
    return out


@router.post(
    "/inspection-requests/{request_id}/review",
    response_model=InspectionOut,
    responses=TRANSITION_RESPONSES,
    summary="Accept or reject an owner photo report (a FAILED report cannot be accepted)",
)
async def review_inspection(
    request_id: uuid.UUID,
    body: InspectionReview,
    session: DbSession,
    storage: Storage,
    inspector: CurrentInspector,
) -> InspectionOut:
    request = await service.review(
        session,
        request_id,
        decision=InspectionStatus(body.decision),
        comment=body.comment,
        actor=inspector.actor,
    )
    [out] = await to_out(session, storage, [request])
    return out


@router.get("/risk", response_model=list[RiskItem], summary="Parcels ranked by risk, with reasons")
async def risk_ranking(
    session: DbSession, _: CurrentInspector, limit: Annotated[int, Query(ge=1, le=200)] = 30
) -> list[RiskItem]:
    risks = await risk_service.compute_risks(session)
    return [
        RiskItem(
            parcel_id=str(r.parcel_id),
            cadastral_number=r.cadastral_number,
            status=r.status,
            score=r.score,
            factors=[RiskFactorOut(code=f.code, points=f.points, params=f.params) for f in r.factors],
            centroid=LngLat(lon=r.lon, lat=r.lat),
        )
        for r in risks[:limit]
    ]


@router.post(
    "/inspection-plan",
    response_model=PlanOut,
    status_code=201,
    summary="Create owner photo-report requests: top risk + reproducible random control sample",
)
async def inspection_plan(
    body: PlanRequest, session: DbSession, storage: Storage, inspector: CurrentInspector
) -> PlanOut:
    plan = await risk_service.create_plan(
        session, size=body.size, random_share=body.random_share, actor=inspector.actor
    )
    return PlanOut(seed=plan.seed, created=await to_out(session, storage, plan.requests))


@router.get(
    "/parcels/{parcel_id}/evidence",
    response_model=ResolutionEvidence,
    summary="What evidence exists to close the violation as resolved",
)
async def parcel_evidence(
    parcel_id: uuid.UUID, session: DbSession, _: CurrentInspector
) -> ResolutionEvidence:
    from app.services.parcels import get_parcel

    return await resolution_evidence(session, await get_parcel(session, parcel_id))


@router.get(
    "/parcels/{parcel_id}/crosscheck",
    response_model=CrossCheck,
    summary="Cross-check with state data: cadastre registry, declared sowing (subsidies) vs satellite",
)
async def parcel_crosscheck(parcel_id: uuid.UUID, session: DbSession, _: CurrentInspector) -> CrossCheck:
    from app.services.parcels import get_parcel

    return await crosscheck(session, await get_parcel(session, parcel_id))
