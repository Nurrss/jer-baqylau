"""Flexible import of organizer-provided GeoJSON parcels (``packages/seed/organizers/*.geojson``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.domain.enums import OwnerType, ParcelPurpose, ParcelStatus

log = get_logger(__name__)

CADASTRAL_KEYS = ("cadastral_number", "kad_nomer", "kadastr", "cad_num", "cadnum", "kn", "кадастровый_номер",
                  "кад_номер", "cadastre", "kad_number")  # fmt: skip
PURPOSE_KEYS = ("purpose", "target", "celevoe", "naznachenie", "назначение", "целевое_назначение", "landuse")
ADDRESS_KEYS = ("address", "adres", "адрес", "location", "address_ru")
OWNER_KEYS = ("owner_type", "pravo", "right", "вид_права", "ownership")

PURPOSE_KEYWORDS: list[tuple[tuple[str, ...], ParcelPurpose]] = [
    (("ижс", "жилищ", "izhs", "residential", "жтқ", "тұрғын"), ParcelPurpose.IZHS),
    (("лпх", "подсоб", "lph"), ParcelPurpose.LPH),
    (("сельск", "с/х", "с\\х", "агро", "пашн", "пастбищ", "farm", "agri", "ауыл"), ParcelPurpose.AGRICULTURE),
    (("пром", "industr", "производ", "өнеркәсіп"), ParcelPurpose.INDUSTRIAL),
    (("коммер", "торгов", "commerc", "retail", "сауда"), ParcelPurpose.COMMERCIAL),
]


def _pick(props: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).lower(): v for k, v in props.items()}
    for key in keys:
        value = lowered.get(key)
        if value not in (None, ""):
            return value
    return None


def map_purpose(raw: Any) -> ParcelPurpose:
    if raw is None:
        return ParcelPurpose.IZHS
    text = str(raw).lower()
    try:
        return ParcelPurpose(text.upper())
    except ValueError:
        pass
    for keywords, purpose in PURPOSE_KEYWORDS:
        if any(k in text for k in keywords):
            return purpose
    return ParcelPurpose.IZHS


def map_owner(raw: Any) -> OwnerType:
    text = str(raw or "").lower()
    if any(k in text for k in ("аренд", "lease", "жалға", "землепольз")):
        return OwnerType.LEASE
    if any(k in text for k in ("гос", "state", "мемлекет")):
        return OwnerType.STATE
    return OwnerType.PRIVATE


def _looks_geographic(geometry: dict[str, Any]) -> bool:
    def first_coord(coords: Any) -> Any:
        while isinstance(coords, list) and coords and isinstance(coords[0], list):
            coords = coords[0]
        return coords

    coord = first_coord(geometry.get("coordinates"))
    return isinstance(coord, list) and len(coord) >= 2 and abs(coord[0]) <= 180 and abs(coord[1]) <= 90


def load_features(directory: Path) -> list[dict[str, Any]]:
    """Return features normalized to the same property schema as the generated seed."""
    features: list[dict[str, Any]] = []
    counter = 0
    for path in sorted(directory.glob("*.geojson")) + sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("organizers_file_unreadable", file=path.name, error=str(exc))
            continue
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in ("Polygon", "MultiPolygon") or not _looks_geographic(geometry):
                log.warning("organizers_feature_skipped", file=path.name, reason="geometry")
                continue
            props = feature.get("properties") or {}
            counter += 1
            cadastral = _pick(props, CADASTRAL_KEYS) or f"06:097:8{counter // 1000:02d}:{counter % 1000:03d}"
            address = str(_pick(props, ADDRESS_KEYS) or "Жамбылская область")
            status_raw = str(props.get("status", "")).upper()
            status = status_raw if status_raw in ParcelStatus.__members__ else ParcelStatus.OK.value
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "cadastral_number": str(cadastral).strip(),
                        "purpose": map_purpose(_pick(props, PURPOSE_KEYS)).value,
                        "owner_type": map_owner(_pick(props, OWNER_KEYS)).value,
                        "address_ru": address,
                        "address_kk": address,
                        "district": str(props.get("district") or props.get("район") or "Жамбылская область"),
                        "lease_until": None,
                        "seed_status": status,
                        "seed_violation_type": None,
                        "seed_deadline_days": None,
                        "source": "organizers",
                    },
                }
            )
    log.info("organizers_features_loaded", count=len(features))
    return features
