from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.enums import ApplicationStatus, ApplicationType, ParcelStatus, ViolationType
from app.schemas.common import ApiModel, TransitionOut

# ── Applications ────────────────────────────────────────────────────────────


class ApplicationOut(ApiModel):
    id: str
    tracking_number: str
    applicant_name: str
    type: ApplicationType
    status: ApplicationStatus
    status_comment_ru: str | None
    status_comment_kk: str | None
    inspection_date: date | None
    parcel_id: str | None
    parcel_cadastral_number: str | None
    submitted_at: datetime
    updated_at: datetime
    subscribers_count: int
    allowed_transitions: list[ApplicationStatus]
    history: list[TransitionOut]


class ApplicationList(ApiModel):
    items: list[ApplicationOut]
    total: int


class ApplicationTransitionRequest(ApiModel):
    to: ApplicationStatus
    comment_ru: str = Field(min_length=3, max_length=2000)
    comment_kk: str = Field(min_length=3, max_length=2000)
    inspection_date: date | None = None

    @model_validator(mode="after")
    def _inspection_date_required(self) -> ApplicationTransitionRequest:
        if self.to is ApplicationStatus.INSPECTION_SCHEDULED and self.inspection_date is None:
            raise ValueError("inspection_date is required for INSPECTION_SCHEDULED")
        return self


# ── Dashboard ───────────────────────────────────────────────────────────────


class Kpi(ApiModel):
    parcels_total: int
    area_total_ha: float
    violations_active: int
    in_remediation: int
    overdue: int
    signals_7d: int
    signals_new: int
    avg_reaction_hours: float | None


class DayCount(ApiModel):
    date: date
    count: int


class ViolationTypeCount(ApiModel):
    violation_type: ViolationType
    count: int


class StatusCount(ApiModel):
    status: ParcelStatus
    count: int


class UpcomingDeadline(ApiModel):
    parcel_id: str
    cadastral_number: str
    status: ParcelStatus
    violation_type: ViolationType | None
    deadline_at: datetime
    days_left: int


class DashboardStats(ApiModel):
    kpi: Kpi
    signals_by_day: list[DayCount]
    violations_by_type: list[ViolationTypeCount]
    status_counts: list[StatusCount]
    upcoming_deadlines: list[UpcomingDeadline]


# ── Satellite ───────────────────────────────────────────────────────────────


class NdviReadingOut(ApiModel):
    parcel_id: str
    ndvi: float
    flagged: bool
    scanned_at: datetime
    observed_at: datetime | None = Field(default=None, description="Acquisition time of the satellite scene")
    scene_id: str | None = None


class NdviLayer(ApiModel):
    provider: str
    is_demo: bool
    scanned_at: datetime | None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    scenes: list[str] = Field(default_factory=list)
    threshold: float
    readings: list[NdviReadingOut]


class SatelliteScanStarted(ApiModel):
    started: bool = Field(description="False if a scan is already running")
    provider: str
    is_demo: bool


class SatelliteScanResult(ApiModel):
    scanned: int
    flagged: int
    provider: str


# ── Events (realtime fallback) ──────────────────────────────────────────────


class EventOut(ApiModel):
    id: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class EventList(ApiModel):
    items: list[EventOut]
    last_id: int


# ── Auth ────────────────────────────────────────────────────────────────────


class AuthConfig(ApiModel):
    mode: Literal["supabase", "local"]


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class InspectorOut(ApiModel):
    id: str
    email: str | None
    name: str


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: InspectorOut


# ── Health / dev ────────────────────────────────────────────────────────────


class HealthOut(ApiModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    database: bool
    redis: bool
    bot: Literal["polling", "webhook", "disabled"]
    storage: str


class DemoResetResponse(ApiModel):
    parcels: int
    applications: int
    signals: int
