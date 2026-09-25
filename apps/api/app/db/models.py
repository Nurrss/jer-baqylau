"""SQLAlchemy ORM models. All geometries are stored in PostGIS, SRID 4326."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.enums import (
    ApplicationStatus,
    ApplicationType,
    EntityType,
    Lang,
    OwnerType,
    ParcelPurpose,
    ParcelStatus,
    PhotoOwnerType,
    PhotoSource,
    SignalCategory,
    SignalStatus,
    SubscriptionTarget,
    ViolationType,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Enum stored as VARCHAR + CHECK constraint (easier to evolve than native PG enums)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_col() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


signal_seq = Sequence("signal_tracking_seq", start=1, metadata=Base.metadata)


class Parcel(Base):
    __tablename__ = "parcels"

    id: Mapped[uuid.UUID] = uuid_pk()
    cadastral_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    geometry: Mapped[WKBElement] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False
    )
    centroid: Mapped[WKBElement] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=True), nullable=False
    )
    area_ha: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    purpose: Mapped[ParcelPurpose] = mapped_column(str_enum(ParcelPurpose, "parcel_purpose"), nullable=False)
    owner_type: Mapped[OwnerType] = mapped_column(str_enum(OwnerType, "owner_type"), nullable=False)
    address_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    address_kk: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ParcelStatus] = mapped_column(
        str_enum(ParcelStatus, "parcel_status"), nullable=False, default=ParcelStatus.OK, index=True
    )
    violation_type: Mapped[ViolationType | None] = mapped_column(str_enum(ViolationType, "violation_type"))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    inspector_id: Mapped[str | None] = mapped_column(String(64))
    ndvi: Mapped[float | None] = mapped_column(Float)
    ndvi_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ndvi_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ndvi_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ndvi_scene_id: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="seed")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    signals: Mapped[list[Signal]] = relationship(back_populates="parcel", foreign_keys="Signal.parcel_id")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    tracking_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    location: Mapped[WKBElement] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=True), nullable=False
    )
    category: Mapped[SignalCategory] = mapped_column(
        str_enum(SignalCategory, "signal_category"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[SignalStatus] = mapped_column(
        str_enum(SignalStatus, "signal_status"), nullable=False, default=SignalStatus.NEW, index=True
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), index=True
    )
    parcel_distance_m: Mapped[float | None] = mapped_column(Float)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), index=True
    )
    reporter_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    reporter_lang: Mapped[Lang] = mapped_column(str_enum(Lang, "lang"), nullable=False, default=Lang.RU)
    resolution_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    parcel: Mapped[Parcel | None] = relationship(back_populates="signals", foreign_keys=[parcel_id])

    __table_args__ = (Index("ix_signals_created_at", "created_at"),)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_type: Mapped[PhotoOwnerType] = mapped_column(
        str_enum(PhotoOwnerType, "photo_owner_type"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    thumb_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/jpeg")
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[PhotoSource] = mapped_column(str_enum(PhotoSource, "photo_source"), nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_photos_owner", "owner_type", "owner_id"),)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = uuid_pk()
    tracking_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    applicant_name: Mapped[str] = mapped_column(String(64), nullable=False)  # already masked
    type: Mapped[ApplicationType] = mapped_column(
        str_enum(ApplicationType, "application_type"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus, "application_status"), nullable=False, index=True
    )
    status_comment_ru: Mapped[str | None] = mapped_column(Text)
    status_comment_kk: Mapped[str | None] = mapped_column(Text)
    inspection_date: Mapped[date | None] = mapped_column(Date)
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parcels.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    parcel: Mapped[Parcel | None] = relationship()


class StatusTransition(Base):
    """Audit log of every status change."""

    __tablename__ = "status_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[EntityType] = mapped_column(str_enum(EntityType, "entity_type"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_status_transitions_entity", "entity_type", "entity_id", "created_at"),)


class Event(Base):
    """Append-only domain events; the web panel subscribes to inserts (Supabase Realtime)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    lang: Mapped[Lang | None] = mapped_column(str_enum(Lang, "lang"))
    signals_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_signal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_users.chat_id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[SubscriptionTarget] = mapped_column(
        str_enum(SubscriptionTarget, "subscription_target"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("chat_id", "target_type", "target_id", name="uq_subscriptions_target"),
        Index("ix_subscriptions_target", "target_type", "target_id"),
    )


class KnowledgeQuestion(Base):
    """Questions citizens asked when the knowledge base did not help."""

    __tablename__ = "knowledge_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lang: Mapped[Lang] = mapped_column(str_enum(Lang, "lang"), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class NdviScan(Base):
    __tablename__ = "ndvi_scans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False)
    ndvi: Mapped[float] = mapped_column(Float, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scene_id: Mapped[str | None] = mapped_column(String(64))
    valid_fraction: Mapped[float | None] = mapped_column(Float)
    scanned_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_ndvi_scans_parcel", "parcel_id", "scanned_at"),)


class ProcessedUpdate(Base):
    """Telegram update ids already handled (webhook idempotency)."""

    __tablename__ = "tg_processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = created_at_col()


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    address_ru: Mapped[str | None] = mapped_column(String(512))
    address_kk: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = created_at_col()
