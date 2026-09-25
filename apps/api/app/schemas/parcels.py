from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.enums import OwnerType, ParcelPurpose, ParcelStatus, ViolationType
from app.schemas.common import ApiModel, LngLat, PhotoOut, TransitionOut
from app.schemas.signals import SignalSummary


class ParcelProperties(ApiModel):
    id: str
    cadastral_number: str
    status: ParcelStatus
    violation_type: ViolationType | None
    purpose: ParcelPurpose
    owner_type: OwnerType
    area_ha: float
    address_ru: str
    address_kk: str
    district: str
    deadline_at: datetime | None
    is_overdue: bool
    ndvi: float | None
    ndvi_flagged: bool
    open_signals_count: int


class ParcelFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: ParcelProperties


class ParcelFeatureCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ParcelFeature]


class ParcelSearchResult(ApiModel):
    id: str
    cadastral_number: str
    address_ru: str
    address_kk: str
    status: ParcelStatus
    centroid: LngLat
    bbox: list[float] = Field(min_length=4, max_length=4, description="minLon, minLat, maxLon, maxLat")


class ParcelDetail(ParcelProperties):
    geometry: dict[str, Any]
    centroid: LngLat
    bbox: list[float] = Field(min_length=4, max_length=4, description="minLon, minLat, maxLon, maxLat")
    lease_until: date | None
    inspector_id: str | None
    ndvi_scanned_at: datetime | None
    ndvi_observed_at: datetime | None
    ndvi_scene_id: str | None
    updated_at: datetime
    allowed_transitions: list[ParcelStatus]
    photos: list[PhotoOut]
    signals: list[SignalSummary]
    history: list[TransitionOut]


class ParcelTransitionRequest(ApiModel):
    to: ParcelStatus
    comment: str = Field(min_length=3, max_length=2000)
    violation_type: ViolationType | None = None
    deadline_at: datetime | None = None


class ParcelUpdateRequest(ApiModel):
    deadline_at: datetime | None = None
    inspector_id: str | None = Field(default=None, max_length=64)
    clear_deadline: bool = False

    @model_validator(mode="after")
    def _one_deadline_action(self) -> ParcelUpdateRequest:
        if self.clear_deadline and self.deadline_at is not None:
            raise ValueError("Use either deadline_at or clear_deadline, not both")
        return self


class CadastreRecord(ApiModel):
    """Record as returned by an external cadastre registry (ГБД ЗКС) adapter."""

    provider: str
    cadastral_number: str
    purpose: str
    area_ha: float
    right_type: str
    right_holder: str
    registered_at: date | None
    encumbrances: list[str]
    matches_local: bool
    discrepancies: list[str]
