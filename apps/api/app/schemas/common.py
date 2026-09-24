from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorInfo(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(ApiModel):
    error: ErrorInfo


class TransitionOut(ApiModel):
    id: int
    from_status: str | None
    to_status: str
    actor: str
    comment: str | None
    meta: dict[str, Any]
    created_at: datetime


class PhotoOut(ApiModel):
    id: str
    url: str
    thumb_url: str
    source: str
    taken_at: datetime | None
    lat: float | None
    lon: float | None
    uploaded_by: str
    created_at: datetime


class LngLat(ApiModel):
    lon: float
    lat: float


# Standard error responses documented on every protected route.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}
TRANSITION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **ERROR_RESPONSES,
    409: {"model": ErrorResponse, "description": "Transition not allowed"},
}
