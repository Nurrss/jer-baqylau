"""Pure domain logic: state machines and tracking numbers."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidTransitionError
from app.domain.enums import ApplicationStatus, EntityType, ParcelStatus, SignalStatus
from app.domain.state_machine import allowed_transitions, can_transition, ensure_transition, is_terminal
from app.domain.tracking import (
    format_signal_code,
    mask_person_name,
    normalize_application_number,
    normalize_signal_code,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ParcelStatus.OK, ParcelStatus.UNDER_CHECK),
        (ParcelStatus.OK, ParcelStatus.VIOLATION),
        (ParcelStatus.UNDER_CHECK, ParcelStatus.OK),
        (ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION),
        (ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION),
        (ParcelStatus.IN_REMEDIATION, ParcelStatus.RESOLVED),
        (ParcelStatus.IN_REMEDIATION, ParcelStatus.RETURNED_TO_STATE),
    ],
)
def test_parcel_lifecycle_from_spec_is_allowed(current: ParcelStatus, target: ParcelStatus) -> None:
    assert can_transition(EntityType.PARCEL, current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ParcelStatus.OK, ParcelStatus.RESOLVED),
        (ParcelStatus.VIOLATION, ParcelStatus.RESOLVED),
        (ParcelStatus.VIOLATION, ParcelStatus.OK),
        (ParcelStatus.UNDER_CHECK, ParcelStatus.IN_REMEDIATION),
        (ParcelStatus.RETURNED_TO_STATE, ParcelStatus.OK),
    ],
)
def test_parcel_invalid_transitions_raise_409(current: ParcelStatus, target: ParcelStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        ensure_transition(EntityType.PARCEL, current, target)
    assert exc.value.status_code == 409
    assert exc.value.details["allowed"] == [s.value for s in allowed_transitions(EntityType.PARCEL, current)]


def test_terminal_states() -> None:
    assert is_terminal(EntityType.PARCEL, ParcelStatus.RETURNED_TO_STATE)
    assert is_terminal(EntityType.SIGNAL, SignalStatus.CONFIRMED)
    assert is_terminal(EntityType.SIGNAL, SignalStatus.REJECTED)
    assert is_terminal(EntityType.APPLICATION, ApplicationStatus.APPROVED)
    assert not is_terminal(EntityType.SIGNAL, SignalStatus.NEW)


def test_allowed_transitions_keep_enum_order() -> None:
    assert allowed_transitions(EntityType.SIGNAL, SignalStatus.NEW) == [
        SignalStatus.IN_REVIEW,
        SignalStatus.CONFIRMED,
        SignalStatus.REJECTED,
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KZ-2026-042", "KZ-2026-042"),
        ("kz 2026 42", "KZ-2026-042"),
        ("kz-2026-42", "KZ-2026-042"),
        ("КЗ/2026/42", "KZ-2026-042"),
        ("2026-42", "KZ-2026-042"),
        ("  kz2026 042 ", "KZ-2026-042"),
        ("KZ 42", "KZ-2026-042"),
        ("№ KZ-2026-7", "KZ-2026-007"),
        ("kz 2026 1234", "KZ-2026-1234"),
    ],
)
def test_normalize_application_number(raw: str, expected: str) -> None:
    assert normalize_application_number(raw, default_year=2026) == expected


@pytest.mark.parametrize("raw", ["", "hello", "KZ", "KZ-2026-0", "KZ-1800-5", "42-2026"])
def test_normalize_application_number_rejects_garbage(raw: str) -> None:
    assert normalize_application_number(raw, default_year=2026) is None


def test_signal_codes() -> None:
    assert format_signal_code(2026, 7) == "SIG-2026-0007"
    assert normalize_signal_code("sig 2026 7") == "SIG-2026-0007"
    assert normalize_signal_code("nope") is None


def test_mask_person_name() -> None:
    assert mask_person_name("Ерлан Серкулов") == "Ерлан С."
    assert mask_person_name("Айгерим") == "Айгерим"
    assert mask_person_name("") == ""
