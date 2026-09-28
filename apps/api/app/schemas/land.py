"""State land fund and Mini App applications."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field, field_validator

from app.domain.enums import AllocationStatus, ApplicationStatus, ApplicationType, ParcelPurpose
from app.schemas.common import ApiModel


class LandFund(ApiModel):
    """GeoJSON FeatureCollection of free (OFFERED) and pending (RESERVED) fund parcels."""

    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    offered: int
    reserved: int


class LandApplicationCreate(ApiModel):
    parcel_ids: list[uuid.UUID] = Field(min_length=1, max_length=5, description="In order of priority")
    full_name: str = Field(min_length=3, max_length=120, description="Фамилия Имя Отчество")
    iin: str = Field(min_length=12, max_length=12)
    phone: str = Field(min_length=10, max_length=20)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("parcel_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("parcels must be unique")
        return value


class LandApplicationDraft(ApiModel):
    id: str
    tracking_number: str
    status: ApplicationStatus
    type: ApplicationType
    parcels: int


class ApplicationParcelOut(ApiModel):
    id: str
    cadastral_number: str
    area_ha: float
    purpose: ParcelPurpose
    priority: int
    granted: bool
    allocation_status: AllocationStatus


class MiniAppApplication(ApiModel):
    tracking_number: str
    status: ApplicationStatus
    type: ApplicationType
    parcels: list[ApplicationParcelOut]
