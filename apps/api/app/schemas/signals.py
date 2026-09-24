from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import Lang, SignalCategory, SignalStatus, ViolationType
from app.schemas.common import ApiModel, PhotoOut, TransitionOut


class SignalSummary(ApiModel):
    id: str
    tracking_code: str
    category: SignalCategory
    status: SignalStatus
    description: str | None
    address: str | None
    lat: float
    lon: float
    parcel_id: str | None
    parcel_cadastral_number: str | None
    duplicate_of: str | None
    reports_count: int = Field(description="Root signal + its duplicates (how many citizens reported)")
    thumb_url: str | None
    photos_count: int
    created_at: datetime


class SignalList(ApiModel):
    items: list[SignalSummary]
    total: int


class SignalDetail(SignalSummary):
    reporter_lang: Lang
    has_reporter: bool
    parcel_distance_m: float | None
    resolution_comment: str | None
    allowed_transitions: list[SignalStatus]
    photos: list[PhotoOut]
    duplicates: list[SignalSummary]
    history: list[TransitionOut]


class SignalTransitionRequest(ApiModel):
    to: SignalStatus
    comment: str = Field(min_length=3, max_length=2000)
    # Used when confirming: the linked parcel moves to VIOLATION.
    violation_type: ViolationType | None = None
    deadline_at: datetime | None = None


class SimulateSignalRequest(ApiModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    category: SignalCategory = SignalCategory.DUMP
    description: str | None = Field(default=None, max_length=500)
    chat_id: int | None = None
    lang: Lang = Lang.RU
    photos: int = Field(default=1, ge=0, le=5, description="Number of generated placeholder photos")


class SimulateSignalResponse(ApiModel):
    signal: SignalSummary
    parcel_status: str | None
