from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.domain.enums import (
    DeclaredUse,
    InspectionReason,
    InspectionStatus,
    InspectionVerdict,
    ParcelPurpose,
    ParcelStatus,
)
from app.schemas.common import ApiModel, LngLat, PhotoOut


class CheckOut(ApiModel):
    code: str
    status: Literal["pass", "warn", "fail", "skip"]
    params: dict[str, Any]


class InspectionOut(ApiModel):
    id: str
    code: str
    parcel_id: str
    cadastral_number: str
    status: InspectionStatus
    reason: InspectionReason
    verdict: InspectionVerdict | None
    note: str | None
    requested_by: str
    due_at: datetime
    created_at: datetime
    submitted_at: datetime | None
    declared_use: DeclaredUse | None
    owner_comment: str | None
    device: LngLat | None
    accuracy_m: float | None
    checks: list[CheckOut]
    reviewed_by: str | None
    review_comment: str | None
    reviewed_at: datetime | None
    link: str | None = Field(description="Owner link; only while the request is open")
    photos: list[PhotoOut]


class InspectionList(ApiModel):
    items: list[InspectionOut]
    total: int


class InspectionCreate(ApiModel):
    due_hours: int = Field(default=48, ge=1, le=336)
    note: str | None = Field(default=None, max_length=500)


class InspectionReview(ApiModel):
    decision: Literal["ACCEPTED", "REJECTED"]
    comment: str = Field(min_length=3, max_length=2000)


class RiskFactorOut(ApiModel):
    code: str
    points: int
    params: dict[str, Any]


class RiskItem(ApiModel):
    parcel_id: str
    cadastral_number: str
    status: ParcelStatus
    score: int
    factors: list[RiskFactorOut]
    centroid: LngLat


class PlanRequest(ApiModel):
    size: int = Field(default=5, ge=1, le=20)
    random_share: float = Field(default=0.2, ge=0, le=1)


class PlanOut(ApiModel):
    seed: str = Field(description="Reproducible seed of the random control sample")
    created: list[InspectionOut]


class InspectionPublic(ApiModel):
    """What the owner sees on the one-time link (no personal data of anyone)."""

    code: str
    status: InspectionStatus
    cadastral_number: str
    address_ru: str
    address_kk: str
    purpose: ParcelPurpose
    due_at: datetime
    note: str | None
    centroid: LngLat
    parcel: dict[str, Any] = Field(description="Parcel boundary (GeoJSON) to show where to stand")


class InspectionSubmitted(ApiModel):
    code: str
    status: InspectionStatus
    photos: int
