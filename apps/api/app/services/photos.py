"""Photo processing (Pillow), EXIF extraction and persistence."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from geoalchemy2.shape import from_shape
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailedError
from app.db.models import Photo
from app.domain.enums import PhotoOwnerType, PhotoSource
from app.providers.storage import StorageProvider
from app.schemas.common import PhotoOut

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SIDE = 2048
THUMB_SIDE = 480
JPEG_QUALITY = 85
LOCAL_TZ = ZoneInfo("Asia/Almaty")

_GPS_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")
_DATETIME_ORIGINAL = next(k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal")
_EXIF_IFD = 0x8769


def perceptual_hash(image: Image.Image) -> str:
    """64-bit difference hash: survives re-compression and resizing, so a re-sent photo is recognized."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | int(left > right)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


@dataclass(slots=True)
class ProcessedImage:
    full: bytes
    thumb: bytes
    sha256: str
    phash: str
    width: int
    height: int
    taken_at: datetime | None
    lat: float | None
    lon: float | None


def _to_degrees(value: tuple[float, float, float]) -> float:
    d, m, s = (float(x) for x in value)
    return d + m / 60 + s / 3600


def _extract_gps(exif: Image.Exif) -> tuple[float | None, float | None]:
    try:
        gps = exif.get_ifd(_GPS_TAG)
    except (KeyError, AttributeError):
        return None, None
    if not gps or 2 not in gps or 4 not in gps:
        return None, None
    try:
        lat = _to_degrees(gps[2]) * (-1 if gps.get(1) == "S" else 1)
        lon = _to_degrees(gps[4]) * (-1 if gps.get(3) == "W" else 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None, None
    return round(lat, 7), round(lon, 7)


def _extract_taken_at(exif: Image.Exif) -> datetime | None:
    raw = None
    with contextlib.suppress(KeyError, AttributeError):
        raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL)
    raw = raw or exif.get(306)  # DateTime
    if not isinstance(raw, str):
        return None
    try:
        # EXIF has no timezone; assume local time of the region.
        return datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def _encode(image: Image.Image, side: int) -> tuple[bytes, int, int]:
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buffer.getvalue(), copy.width, copy.height


def process_image(data: bytes) -> ProcessedImage:
    """Validate, normalize orientation, strip metadata, build a thumbnail. CPU-bound."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationFailedError("Photo is too large (max 15 MB)", code="PHOTO_TOO_LARGE")
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            exif = source.getexif()
            lat, lon = _extract_gps(exif)
            taken_at = _extract_taken_at(exif)
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationFailedError(
            "Unsupported image format (use JPEG, PNG or WebP)", code="PHOTO_INVALID"
        ) from exc
    full, width, height = _encode(image, MAX_SIDE)
    thumb, _, _ = _encode(image, THUMB_SIDE)
    return ProcessedImage(
        full=full,
        thumb=thumb,
        sha256=hashlib.sha256(full).hexdigest(),
        phash=perceptual_hash(image),
        width=width,
        height=height,
        taken_at=taken_at,
        lat=lat,
        lon=lon,
    )


UPLOAD_CONCURRENCY = 8


@dataclass(slots=True)
class PhotoSpec:
    owner_type: PhotoOwnerType
    owner_id: uuid.UUID
    data: bytes
    source: PhotoSource
    uploaded_by: str


def _build(spec: PhotoSpec, processed: ProcessedImage) -> tuple[Photo, list[tuple[str, bytes]]]:
    photo_id = uuid.uuid4()
    base = f"{spec.owner_type.value.lower()}/{spec.owner_id}/{photo_id}"
    full_path, thumb_path = f"{base}.jpg", f"{base}_thumb.jpg"
    photo = Photo(
        id=photo_id,
        owner_type=spec.owner_type,
        owner_id=spec.owner_id,
        storage_path=full_path,
        thumb_path=thumb_path,
        content_type="image/jpeg",
        width=processed.width,
        height=processed.height,
        source=spec.source,
        taken_at=processed.taken_at,
        location=(
            from_shape(Point(processed.lon, processed.lat), srid=4326)
            if processed.lat is not None and processed.lon is not None
            else None
        ),
        uploaded_by=spec.uploaded_by,
        sha256=processed.sha256,
        phash=processed.phash,
        # Upload moment (not the transaction start that the DB default would give): evidence timing matters.
        created_at=datetime.now(UTC),
    )
    return photo, [(full_path, processed.full), (thumb_path, processed.thumb)]


async def save_photos(session: AsyncSession, storage: StorageProvider, specs: list[PhotoSpec]) -> list[Photo]:
    """Process images, upload all files concurrently (storage may be far away), then insert rows."""
    if not specs:
        return []
    processed = await asyncio.gather(*(asyncio.to_thread(process_image, spec.data) for spec in specs))
    built = [_build(spec, image) for spec, image in zip(specs, processed, strict=True)]
    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)

    async def upload(path: str, data: bytes) -> None:
        async with semaphore:
            await storage.upload(path, data, "image/jpeg")

    await asyncio.gather(*(upload(path, data) for _, files in built for path, data in files))
    photos = [photo for photo, _ in built]
    session.add_all(photos)
    await session.flush()
    return photos


async def save_photo(
    session: AsyncSession,
    storage: StorageProvider,
    *,
    owner_type: PhotoOwnerType,
    owner_id: uuid.UUID,
    data: bytes,
    source: PhotoSource,
    uploaded_by: str,
) -> Photo:
    [photo] = await save_photos(
        session, storage, [PhotoSpec(owner_type, owner_id, data, source, uploaded_by)]
    )
    return photo


async def photos_for(
    session: AsyncSession,
    storage: StorageProvider,
    owner_type: PhotoOwnerType,
    owner_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[PhotoOut]]:
    """Photos grouped by owner, with signed URLs (one signing round-trip)."""
    if not owner_ids:
        return {}
    rows = (
        await session.execute(
            select(Photo, func.ST_Y(Photo.location), func.ST_X(Photo.location))
            .where(Photo.owner_type == owner_type, Photo.owner_id.in_(owner_ids))
            .order_by(Photo.created_at, Photo.id)
        )
    ).all()
    paths = [p for photo, _, _ in rows for p in (photo.storage_path, photo.thumb_path)]
    urls = await storage.signed_urls(paths)
    grouped: dict[uuid.UUID, list[PhotoOut]] = defaultdict(list)
    for photo, lat, lon in rows:
        grouped[photo.owner_id].append(
            PhotoOut(
                id=str(photo.id),
                url=urls.get(photo.storage_path, ""),
                thumb_url=urls.get(photo.thumb_path, ""),
                source=photo.source.value,
                taken_at=photo.taken_at,
                lat=lat,
                lon=lon,
                uploaded_by=photo.uploaded_by,
                created_at=photo.created_at,
            )
        )
    return grouped
