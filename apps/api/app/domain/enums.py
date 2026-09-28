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
    DRAFT = "DRAFT"  # formed in the Mini App, waiting for the citizen's confirmation in Telegram
    UNDER_REVIEW = "UNDER_REVIEW"
    INSPECTION_SCHEDULED = "INSPECTION_SCHEDULED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"  # the citizen cancelled the draft


class ApplicationType(StrEnum):
    PURPOSE_CHANGE = "PURPOSE_CHANGE"
    LEASE_EXTENSION = "LEASE_EXTENSION"
    IZHS_ALLOCATION = "IZHS_ALLOCATION"
    AGRO_LEASE = "AGRO_LEASE"  # lease of agricultural land from the state fund


class AllocationStatus(StrEnum):
    """Place of a parcel in the state land fund (земельный фонд акимата)."""

    NONE = "NONE"  # not in the fund: owned or leased, or not offered
    OFFERED = "OFFERED"  # free, citizens can apply in the Mini App
    RESERVED = "RESERVED"  # an application for it is under review
    ALLOCATED = "ALLOCATED"  # granted to a citizen through an application


class EntityType(StrEnum):
    PARCEL = "PARCEL"
    SIGNAL = "SIGNAL"
    APPLICATION = "APPLICATION"
    INSPECTION = "INSPECTION"


class PhotoOwnerType(StrEnum):
    PARCEL = "PARCEL"
    SIGNAL = "SIGNAL"
    INSPECTION = "INSPECTION"  # owner photo report (remote inspection)


class PhotoSource(StrEnum):
    INSPECTOR = "INSPECTOR"
    CITIZEN = "CITIZEN"
    OWNER = "OWNER"


class InspectionStatus(StrEnum):
    REQUESTED = "REQUESTED"  # link sent to the owner
    SUBMITTED = "SUBMITTED"  # owner sent photos, anti-fraud verdict computed
    ACCEPTED = "ACCEPTED"  # inspector accepted the report as evidence
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class InspectionReason(StrEnum):
    MANUAL = "MANUAL"
    RISK = "RISK"  # selected by the risk score
    RANDOM = "RANDOM"  # random control sample
    SIGNAL = "SIGNAL"


class InspectionVerdict(StrEnum):
    PASS = "PASS"
    SUSPICIOUS = "SUSPICIOUS"
    FAIL = "FAIL"


class DeclaredUse(StrEnum):
    CULTIVATED = "CULTIVATED"  # sown / cultivated
    BUILDING = "BUILDING"  # construction / house
    FALLOW = "FALLOW"  # not used this season
    CLEANED = "CLEANED"  # dump removed / violation fixed
    OTHER = "OTHER"


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
    APPLICATION_SUBMITTED = "application.submitted"
    SATELLITE_SCAN_COMPLETED = "satellite.scan_completed"
    SATELLITE_HISTORY_READY = "satellite.history_ready"
    INSPECTION_REQUESTED = "inspection.requested"
    INSPECTION_SUBMITTED = "inspection.submitted"
    INSPECTION_REVIEWED = "inspection.reviewed"
    INSPECTION_PLAN_CREATED = "inspection.plan_created"
    DEMO_RESET = "demo.reset"


# Signal category → the parcel violation type suggested when a signal is confirmed.
SIGNAL_CATEGORY_TO_VIOLATION: dict[SignalCategory, ViolationType] = {
    SignalCategory.DUMP: ViolationType.DUMP,
    SignalCategory.ABANDONED: ViolationType.UNUSED,
    SignalCategory.SELF_SEIZURE: ViolationType.SELF_SEIZURE,
    SignalCategory.OTHER: ViolationType.MISUSE,
}
