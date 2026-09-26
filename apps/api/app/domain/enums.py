"""Domain enumerations shared by the API, the bot, the database and the seed."""

from __future__ import annotations

from enum import StrEnum


class Lang(StrEnum):
    RU = "ru"
    KK = "kk"


class ParcelStatus(StrEnum):
    OK = "OK"
    UNDER_CHECK = "UNDER_CHECK"
    VIOLATION = "VIOLATION"
    IN_REMEDIATION = "IN_REMEDIATION"
    RESOLVED = "RESOLVED"
    RETURNED_TO_STATE = "RETURNED_TO_STATE"


class ViolationType(StrEnum):
    UNUSED = "UNUSED"
    SELF_SEIZURE = "SELF_SEIZURE"
    DUMP = "DUMP"
    MISUSE = "MISUSE"


class ParcelPurpose(StrEnum):
    IZHS = "IZHS"  # индивидуальное жилищное строительство
    AGRICULTURE = "AGRICULTURE"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    LPH = "LPH"  # личное подсобное хозяйство


class OwnerType(StrEnum):
    PRIVATE = "PRIVATE"
    LEASE = "LEASE"
    STATE = "STATE"


class SignalStatus(StrEnum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class SignalCategory(StrEnum):
    DUMP = "DUMP"
    ABANDONED = "ABANDONED"
    SELF_SEIZURE = "SELF_SEIZURE"
    OTHER = "OTHER"


class ApplicationStatus(StrEnum):
    UNDER_REVIEW = "UNDER_REVIEW"
    INSPECTION_SCHEDULED = "INSPECTION_SCHEDULED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApplicationType(StrEnum):
    PURPOSE_CHANGE = "PURPOSE_CHANGE"
    LEASE_EXTENSION = "LEASE_EXTENSION"
    IZHS_ALLOCATION = "IZHS_ALLOCATION"


class EntityType(StrEnum):
    PARCEL = "PARCEL"
    SIGNAL = "SIGNAL"
    APPLICATION = "APPLICATION"


class PhotoOwnerType(StrEnum):
    PARCEL = "PARCEL"
    SIGNAL = "SIGNAL"


class PhotoSource(StrEnum):
    INSPECTOR = "INSPECTOR"
    CITIZEN = "CITIZEN"


class SubscriptionTarget(StrEnum):
    APPLICATION = "APPLICATION"
    SIGNAL = "SIGNAL"


class EventType(StrEnum):
    SIGNAL_CREATED = "signal.created"
    SIGNAL_STATUS_CHANGED = "signal.status_changed"
    PARCEL_STATUS_CHANGED = "parcel.status_changed"
    PARCEL_UPDATED = "parcel.updated"
    PHOTO_ADDED = "photo.added"
    APPLICATION_STATUS_CHANGED = "application.status_changed"
    SATELLITE_SCAN_COMPLETED = "satellite.scan_completed"
    SATELLITE_HISTORY_READY = "satellite.history_ready"
    DEMO_RESET = "demo.reset"


# Signal category → the parcel violation type suggested when a signal is confirmed.
SIGNAL_CATEGORY_TO_VIOLATION: dict[SignalCategory, ViolationType] = {
    SignalCategory.DUMP: ViolationType.DUMP,
    SignalCategory.ABANDONED: ViolationType.UNUSED,
    SignalCategory.SELF_SEIZURE: ViolationType.SELF_SEIZURE,
    SignalCategory.OTHER: ViolationType.MISUSE,
}
