"""Explicit state machines for every entity with a lifecycle.

This module is the single source of truth for allowed status transitions.
Services must call :func:`ensure_transition` before changing a status; the web
panel reads :func:`allowed_transitions` (exposed via the API) to render only
valid actions.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from app.core.errors import InvalidTransitionError
from app.domain.enums import ApplicationStatus, EntityType, ParcelStatus, SignalStatus

PARCEL_TRANSITIONS: Mapping[ParcelStatus, frozenset[ParcelStatus]] = {
    ParcelStatus.OK: frozenset({ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION}),
    ParcelStatus.UNDER_CHECK: frozenset({ParcelStatus.OK, ParcelStatus.VIOLATION}),
    ParcelStatus.VIOLATION: frozenset({ParcelStatus.IN_REMEDIATION}),
    ParcelStatus.IN_REMEDIATION: frozenset({ParcelStatus.RESOLVED, ParcelStatus.RETURNED_TO_STATE}),
    # A remediated parcel can be re-inspected if new evidence appears.
    ParcelStatus.RESOLVED: frozenset({ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION}),
    ParcelStatus.RETURNED_TO_STATE: frozenset(),
}

SIGNAL_TRANSITIONS: Mapping[SignalStatus, frozenset[SignalStatus]] = {
    SignalStatus.NEW: frozenset({SignalStatus.IN_REVIEW, SignalStatus.CONFIRMED, SignalStatus.REJECTED}),
    SignalStatus.IN_REVIEW: frozenset({SignalStatus.CONFIRMED, SignalStatus.REJECTED}),
    SignalStatus.CONFIRMED: frozenset(),
    SignalStatus.REJECTED: frozenset(),
}

APPLICATION_TRANSITIONS: Mapping[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {ApplicationStatus.INSPECTION_SCHEDULED, ApplicationStatus.APPROVED, ApplicationStatus.REJECTED}
    ),
    ApplicationStatus.INSPECTION_SCHEDULED: frozenset(
        {ApplicationStatus.APPROVED, ApplicationStatus.REJECTED}
    ),
    ApplicationStatus.APPROVED: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
}

# Parcel statuses that mean "an active violation exists" (drawn red on the map).
ACTIVE_VIOLATION_STATUSES: frozenset[ParcelStatus] = frozenset(
    {ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION}
)

_TABLES: dict[EntityType, Mapping[StrEnum, frozenset[StrEnum]]] = {
    EntityType.PARCEL: PARCEL_TRANSITIONS,  # type: ignore[dict-item]
    EntityType.SIGNAL: SIGNAL_TRANSITIONS,  # type: ignore[dict-item]
    EntityType.APPLICATION: APPLICATION_TRANSITIONS,  # type: ignore[dict-item]
}


def allowed_transitions[S: StrEnum](entity: EntityType, current: S) -> list[S]:
    """Allowed target statuses from ``current``, in declaration order of the enum."""
    targets = _TABLES[entity].get(current, frozenset())
    return [status for status in type(current) if status in targets]


def can_transition(entity: EntityType, current: StrEnum, target: StrEnum) -> bool:
    return target in _TABLES[entity].get(current, frozenset())


def ensure_transition(entity: EntityType, current: StrEnum, target: StrEnum) -> None:
    if not can_transition(entity, current, target):
        raise InvalidTransitionError(
            f"Transition {current} → {target} is not allowed for {entity.lower()}",
            details={
                "entity": entity.value,
                "from": current.value,
                "to": target.value,
                "allowed": [s.value for s in allowed_transitions(entity, current)],
            },
        )


def is_terminal(entity: EntityType, current: StrEnum) -> bool:
    return not _TABLES[entity].get(current)
