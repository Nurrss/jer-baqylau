"""Deterministic generator of fictional but plausible parcels around Taraz (Zhambyl region).

Parcels of a block share a jittered vertex grid, so neighbours touch exactly and never
overlap; each block is then rotated and placed at its own anchor. Output is committed
to ``packages/seed/parcels.geojson`` (regenerate with ``make gen-parcels``).

All cadastral numbers use the fictional quarter range 9xx and do not identify real people.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

from app.domain.enums import OwnerType, ParcelPurpose, ParcelStatus, ViolationType

SEED = 42
M_PER_DEG_LAT = 111_132.0
REGION_CODE = "06"  # Zhambyl region
DISTRICT_CODE = "097"


@dataclass(frozen=True)
class Street:
    ru: str
    kk: str


STREETS = [
    Street("ул. Жибек жолы", "Жібек жолы к-сі"),
    Street("ул. Байзак батыра", "Байзақ батыр к-сі"),
    Street("ул. Толе би", "Төле би к-сі"),
    Street("ул. Койгельды", "Қойгелді к-сі"),
    Street("ул. Сулейменова", "Сүлейменов к-сі"),
    Street("ул. Аль-Фараби", "Әл-Фараби к-сі"),
    Street("ул. Бектурова", "Бектұров к-сі"),
    Street("ул. Жамбыла", "Жамбыл к-сі"),
]


@dataclass(frozen=True)
class Block:
    """A block of parcels laid out as ``rows × cols`` cells in local metres."""

    key: str
    quarter: int
    anchor_lat: float
    anchor_lon: float
    rows: int
    cols: int
    cell_w: tuple[float, float]  # min/max width of a column, metres
    cell_h: tuple[float, float]  # min/max height of a row, metres
    rotation_deg: float
    jitter: float
    purpose: ParcelPurpose | None  # None → mixed per cell (see purpose_mix)
    district_ru: str
    district_kk: str
    rural: bool = False
    locality_ru: str = ""
    locality_kk: str = ""
    purpose_mix: tuple[ParcelPurpose, ...] = ()
    cut_corners: bool = False


BLOCKS: list[Block] = [
    Block(
        "izhs-samal",
        901,
        42.9312,
        71.3284,
        3,
        6,
        (24, 30),
        (36, 46),
        12,
        1.5,
        ParcelPurpose.IZHS,
        "Тараз, мкр. Самал",
        "Тараз, Самал ш/а",
    ),
    Block(
        "izhs-karasu",
        902,
        42.8736,
        71.4265,
        2,
        7,
        (22, 28),
        (40, 50),
        -8,
        1.5,
        None,
        "Тараз, мкр. Карасу",
        "Тараз, Қарасу ш/а",
        purpose_mix=(ParcelPurpose.IZHS, ParcelPurpose.IZHS, ParcelPurpose.LPH),
    ),
    Block(
        "commerce-bypass",
        903,
        42.9168,
        71.4485,
        2,
        4,
        (70, 150),
        (60, 110),
        24,
        4.0,
        None,
        "Тараз, Объездная трасса",
        "Тараз, айналма жол",
        purpose_mix=(ParcelPurpose.COMMERCIAL, ParcelPurpose.INDUSTRIAL, ParcelPurpose.COMMERCIAL),
    ),
    Block(
        "agro-sarykemer",
        904,
        42.9745,
        71.2710,
        3,
        4,
        (260, 520),
        (240, 520),
        5,
        25.0,
        ParcelPurpose.AGRICULTURE,
        "Байзакский район",
        "Байзақ ауданы",
        rural=True,
        locality_ru="окрестности с. Сарыкемер",
        locality_kk="Сарыкемер а. маңы",
        cut_corners=True,
    ),
    Block(
        "agro-assa",
        905,
        42.8420,
        71.3020,
        2,
        4,
        (300, 700),
        (260, 600),
        -14,
        30.0,
        ParcelPurpose.AGRICULTURE,
        "Жамбылский район",
        "Жамбыл ауданы",
        rural=True,
        locality_ru="окрестности с. Аса",
        locality_kk="Аса а. маңы",
        cut_corners=True,
    ),
]


def _metres_to_lonlat(x: float, y: float, lat0: float, lon0: float) -> tuple[float, float]:
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    return lon0 + x / m_per_deg_lon, lat0 + y / M_PER_DEG_LAT


def _cumulative(rng: random.Random, n: int, bounds: tuple[float, float]) -> list[float]:
    edges = [0.0]
    for _ in range(n):
        edges.append(edges[-1] + rng.uniform(*bounds))
    return edges


def _block_polygons(block: Block, rng: random.Random) -> list[Polygon]:
    xs = _cumulative(rng, block.cols, block.cell_w)
    ys = _cumulative(rng, block.rows, block.cell_h)
    # Shared jittered vertex grid (outer boundary also jittered slightly).
    grid = [
        [
            (x + rng.uniform(-block.jitter, block.jitter), y + rng.uniform(-block.jitter, block.jitter))
            for x in xs
        ]
        for y in ys
    ]
    polys: list[Polygon] = []
    for r in range(block.rows):
        for c in range(block.cols):
            ring = [grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]]
            poly = Polygon(ring)
            if block.cut_corners and rng.random() < 0.35:
                # Trim one corner (field following a canal or road) — keeps shapes irregular.
                cx, cy = ring[rng.randrange(4)]
                size = min(xs[c + 1] - xs[c], ys[r + 1] - ys[r]) * rng.uniform(0.2, 0.35)
                corner = Polygon(
                    [
                        (cx - size, cy - size),
                        (cx + size, cy - size),
                        (cx + size, cy + size),
                        (cx - size, cy + size),
                    ]
                ).buffer(0)
                poly = poly.difference(corner)
                if poly.geom_type != "Polygon":
                    poly = max(poly.geoms, key=lambda g: g.area)
            polys.append(poly)
    center = unary_union(polys).centroid
    return [affinity.rotate(p, block.rotation_deg, origin=center) for p in polys]


def _to_wgs84(poly: Polygon, block: Block) -> MultiPolygon:
    ring = [_metres_to_lonlat(x, y, block.anchor_lat, block.anchor_lon) for x, y in poly.exterior.coords]
    rounded = [(round(lon, 7), round(lat, 7)) for lon, lat in ring]
    return MultiPolygon([Polygon(rounded)])


def _owner_type(purpose: ParcelPurpose, rng: random.Random) -> OwnerType:
    if purpose is ParcelPurpose.AGRICULTURE:
        return OwnerType.LEASE if rng.random() < 0.8 else OwnerType.PRIVATE
    if purpose in (ParcelPurpose.COMMERCIAL, ParcelPurpose.INDUSTRIAL):
        return OwnerType.LEASE if rng.random() < 0.6 else OwnerType.PRIVATE
    return OwnerType.PRIVATE if rng.random() < 0.85 else OwnerType.LEASE


# Scenario: status, violation type, deadline offset (days from seeding; negative = overdue)
Scenario = tuple[ParcelStatus, ViolationType | None, int | None]


def _scenarios(total: int, rng: random.Random) -> list[Scenario]:
    violations: list[Scenario] = [
        (ParcelStatus.VIOLATION, ViolationType.UNUSED, 21),
        (ParcelStatus.VIOLATION, ViolationType.DUMP, -3),
        (ParcelStatus.VIOLATION, ViolationType.SELF_SEIZURE, 12),
        (ParcelStatus.VIOLATION, ViolationType.MISUSE, 5),
        (ParcelStatus.VIOLATION, ViolationType.UNUSED, -9),
        (ParcelStatus.IN_REMEDIATION, ViolationType.DUMP, 8),
        (ParcelStatus.IN_REMEDIATION, ViolationType.SELF_SEIZURE, -2),
        (ParcelStatus.IN_REMEDIATION, ViolationType.UNUSED, 30),
        (ParcelStatus.IN_REMEDIATION, ViolationType.MISUSE, 16),
        (ParcelStatus.VIOLATION, ViolationType.SELF_SEIZURE, 40),
        (ParcelStatus.VIOLATION, ViolationType.DUMP, 3),
        (ParcelStatus.IN_REMEDIATION, ViolationType.UNUSED, -5),
    ]
    under_check = round(total * 0.15)
    returned: list[Scenario] = [
        (ParcelStatus.RETURNED_TO_STATE, ViolationType.UNUSED, None),
        (ParcelStatus.RETURNED_TO_STATE, ViolationType.UNUSED, None),
        (ParcelStatus.RETURNED_TO_STATE, ViolationType.SELF_SEIZURE, None),
    ]
    resolved: list[Scenario] = [
        (ParcelStatus.RESOLVED, ViolationType.DUMP, None),
        (ParcelStatus.RESOLVED, ViolationType.MISUSE, None),
    ]
    special = violations + returned + resolved + [(ParcelStatus.UNDER_CHECK, None, None)] * under_check
    result = special + [(ParcelStatus.OK, None, None)] * (total - len(special))
    rng.shuffle(result)
    return result


def generate() -> dict[str, Any]:
    rng = random.Random(SEED)
    raw: list[tuple[Block, Polygon, ParcelPurpose, int]] = []
    for block in BLOCKS:
        for idx, poly in enumerate(_block_polygons(block, rng)):
            purpose = block.purpose or block.purpose_mix[idx % len(block.purpose_mix)]
            raw.append((block, poly, purpose, idx))

    scenarios = _scenarios(len(raw), rng)
    # Returned-to-state and "unused" scenarios make more sense on land plots, not houses:
    # nudge them onto agricultural parcels when possible.
    agro = [i for i, (_, _, p, _) in enumerate(raw) if p is ParcelPurpose.AGRICULTURE]
    for i, scenario in list(enumerate(scenarios)):
        if scenario[0] is ParcelStatus.RETURNED_TO_STATE and raw[i][2] is not ParcelPurpose.AGRICULTURE:
            for j in agro:
                if scenarios[j][0] is ParcelStatus.OK:
                    scenarios[i], scenarios[j] = scenarios[j], scenarios[i]
                    break

    # Convert to WGS84 and remove sub-metre slivers caused by coordinate rounding on shared edges.
    wgs: list[MultiPolygon] = []
    accepted: list[Polygon] = []
    for block, poly, _, _ in raw:
        geom = _to_wgs84(poly, block)
        neighbours = [a for a in accepted if a.intersects(geom)]
        if neighbours:
            cleaned = geom.difference(unary_union(neighbours))
            parts = [cleaned] if cleaned.geom_type == "Polygon" else list(cleaned.geoms)
            geom = MultiPolygon([max((p for p in parts if p.geom_type == "Polygon"), key=lambda p: p.area)])
        wgs.append(geom)
        accepted.append(geom.geoms[0])

    features = []
    today = date(2026, 1, 1)
    for i, ((block, _poly, purpose, idx), scenario) in enumerate(zip(raw, scenarios, strict=True)):
        status, violation_type, deadline_days = scenario
        owner = OwnerType.STATE if status is ParcelStatus.RETURNED_TO_STATE else _owner_type(purpose, rng)
        street = STREETS[(block.quarter + idx // block.cols) % len(STREETS)]
        if block.rural:
            address_ru = f"{block.district_ru}, {block.locality_ru}, поле № {idx + 1}"
            address_kk = f"{block.district_kk}, {block.locality_kk}, № {idx + 1} алқап"
        else:
            house = 2 * (idx % block.cols) + 1 + (idx // block.cols) * 40
            address_ru = f"г. Тараз, {block.district_ru.split(', ')[1]}, {street.ru}, {house}"
            address_kk = f"Тараз қ., {block.district_kk.split(', ')[1]}, {street.kk}, {house}"
        lease_until = (
            (today + timedelta(days=rng.randint(200, 3650))).isoformat() if owner is OwnerType.LEASE else None
        )
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(wgs[i]),
                "properties": {
                    "cadastral_number": f"{REGION_CODE}:{DISTRICT_CODE}:{block.quarter:03d}:{idx + 1:03d}",
                    "purpose": purpose.value,
                    "owner_type": owner.value,
                    "address_ru": address_ru,
                    "address_kk": address_kk,
                    "district": block.district_ru,
                    "lease_until": lease_until,
                    "seed_status": status.value,
                    "seed_violation_type": violation_type.value if violation_type else None,
                    "seed_deadline_days": deadline_days,
                    "seed_index": i,
                },
            }
        )
    return {"type": "FeatureCollection", "name": "jer-demo-parcels-taraz", "features": features}


def write(path: Path) -> int:
    data = generate()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(data["features"])
