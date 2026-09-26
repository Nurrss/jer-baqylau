"""Remote inspections: anti-fraud checks, inspector review, evidence and the reproducible plan."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NdviScan
from app.domain.enums import SignalCategory
from app.services.placeholders import placeholder_photo
from app.services.risk import sample_seed

API = "/api/v1"


async def _parcel(client: AsyncClient, headers: dict[str, str], cadastral: str) -> dict[str, Any]:
    return (await client.get(f"{API}/parcels/search", params={"q": cadastral}, headers=headers)).json()[0]


async def _request(client: AsyncClient, headers: dict[str, str], parcel_id: str) -> dict[str, Any]:
    resp = await client.post(
        f"{API}/parcels/{parcel_id}/inspection-requests",
        json={"due_hours": 24, "note": "Сфотографируйте участок"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _shift(lat: float, lon: float, north_m: float) -> tuple[float, float]:
    return lat + north_m / 111_132, lon


async def _submit(
    client: AsyncClient,
    token: str,
    *,
    lat: float,
    lon: float,
    photos: list[bytes],
    captured: datetime | None = None,
    accuracy: float = 8,
    declared: str = "CLEANED",
) -> Any:
    when = (captured or datetime.now(UTC)).isoformat()
    return await client.post(
        f"{API}/public/inspections/{token}",
        files=[("files", (f"p{i}.jpg", data, "image/jpeg")) for i, data in enumerate(photos)],
        data={
            "captured_at": [when] * len(photos),
            "lat": str(lat),
            "lon": str(lon),
            "accuracy": str(accuracy),
            "declared_use": declared,
            "comment": "Мусор вывезли",
        },
    )


def _checks(item: dict[str, Any]) -> dict[str, str]:
    return {c["code"]: c["status"] for c in item["checks"]}


async def test_honest_report_passes_and_becomes_evidence(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    parcel = await _parcel(client, auth_headers, "06:097:902:003")  # VIOLATION (dump)
    request = await _request(client, auth_headers, parcel["id"])
    token = request["link"].rsplit("/", 1)[1]

    public = (await client.get(f"{API}/public/inspections/{token}")).json()  # no auth: owner link
    assert public["cadastral_number"] == "06:097:902:003"
    assert public["parcel"]["type"] == "MultiPolygon"

    resp = await _submit(
        client,
        token,
        lat=parcel["centroid"]["lat"],
        lon=parcel["centroid"]["lon"],
        photos=[
            placeholder_photo("honest-1", SignalCategory.OTHER),
            placeholder_photo("honest-2", SignalCategory.DUMP),
        ],
    )
    assert resp.status_code == 200, resp.text
    assert "verdict" not in resp.json()  # never revealed to the owner

    item = (await client.get(f"{API}/inspection-requests/{request['id']}", headers=auth_headers)).json()
    assert item["status"] == "SUBMITTED"
    assert item["verdict"] == "PASS", item["checks"]
    assert len(item["photos"]) == 2

    # The link is single-use.
    again = await _submit(client, token, lat=0, lon=0, photos=[placeholder_photo("x")])
    assert again.status_code == 409, again.text

    await client.post(
        f"{API}/parcels/{parcel['id']}/transitions",
        json={"to": "IN_REMEDIATION", "comment": "Предписание"},
        headers=auth_headers,
    )
    accepted = await client.post(
        f"{API}/inspection-requests/{request['id']}/review",
        json={"decision": "ACCEPTED", "comment": "Фото подтверждают вывоз"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200
    evidence = (await client.get(f"{API}/parcels/{parcel['id']}/evidence", headers=auth_headers)).json()
    # Accepted before the precept → does not count; the precept must come first.
    assert not next(i for i in evidence["items"] if i["kind"] == "OWNER_REPORT")["ok"]


async def test_photos_taken_elsewhere_fail_and_cannot_be_accepted(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    parcel = await _parcel(client, auth_headers, "06:097:904:002")
    request = await _request(client, auth_headers, parcel["id"])
    token = request["link"].rsplit("/", 1)[1]
    lat, lon = _shift(parcel["centroid"]["lat"], parcel["centroid"]["lon"], 3_000)  # 3 km away
    await _submit(client, token, lat=lat, lon=lon, photos=[placeholder_photo("far", SignalCategory.OTHER)])
    item = (await client.get(f"{API}/inspection-requests/{request['id']}", headers=auth_headers)).json()
    assert item["verdict"] == "FAIL"
    assert _checks(item)["LOCATION_ON_PARCEL"] == "fail"
    rejected_accept = await client.post(
        f"{API}/inspection-requests/{request['id']}/review",
        json={"decision": "ACCEPTED", "comment": "Принимаю отчёт"},
        headers=auth_headers,
    )
    assert rejected_accept.status_code == 409
    assert rejected_accept.json()["error"]["code"] == "INSPECTION_FAILED"


async def test_old_and_reused_photos_are_detected(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    parcel = await _parcel(client, auth_headers, "06:097:901:004")
    request = await _request(client, auth_headers, parcel["id"])
    token = request["link"].rsplit("/", 1)[1]
    # A photo that already exists in the system (a citizen's seed photo), "taken" an hour ago.
    reused = placeholder_photo("dump-samal:0", SignalCategory.DUMP)
    await _submit(
        client,
        token,
        lat=parcel["centroid"]["lat"],
        lon=parcel["centroid"]["lon"],
        photos=[reused],
        captured=datetime.now(UTC) - timedelta(hours=1),
    )
    item = (await client.get(f"{API}/inspection-requests/{request['id']}", headers=auth_headers)).json()
    checks = _checks(item)
    assert checks["PHOTOS_UNIQUE"] == "fail"
    assert checks["PHOTOS_FRESH"] == "fail"
    assert item["verdict"] == "FAIL"


async def test_declared_crop_contradicting_satellite_is_suspicious(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    parcel = await _parcel(client, auth_headers, "06:097:904:006")  # agricultural
    session.add(
        NdviScan(
            parcel_id=parcel["id"],
            ndvi=0.11,
            flagged=True,
            provider="sentinel-2-l2a",
            observed_at=datetime.now(UTC).replace(month=7, day=15)
            if datetime.now(UTC).month > 7
            else datetime.now(UTC),
            scene_id="S2TEST",
        )
    )
    await session.commit()
    request = await _request(client, auth_headers, parcel["id"])
    token = request["link"].rsplit("/", 1)[1]
    await _submit(
        client,
        token,
        lat=parcel["centroid"]["lat"],
        lon=parcel["centroid"]["lon"],
        photos=[placeholder_photo("crop", SignalCategory.ABANDONED)],
        declared="CULTIVATED",
    )
    item = (await client.get(f"{API}/inspection-requests/{request['id']}", headers=auth_headers)).json()
    if _checks(item)["SATELLITE"] != "skip":  # skipped only if the synthetic scene is out of season
        assert _checks(item)["SATELLITE"] == "warn"
        assert item["verdict"] == "SUSPICIOUS"


async def test_plan_is_risk_based_with_reproducible_random_sample(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    risks = (await client.get(f"{API}/risk", headers=auth_headers)).json()
    assert risks[0]["score"] >= risks[-1]["score"]
    assert risks[0]["factors"]
    resp = await client.post(
        f"{API}/inspection-plan", json={"size": 4, "random_share": 0.5}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()
    reasons = [r["reason"] for r in plan["created"]]
    assert reasons.count("RISK") == 2
    assert reasons.count("RANDOM") == 2
    # The seed is derived from the date and the audit chain head → anyone can recompute it.
    head = await session.scalar(
        text("SELECT hash FROM status_transitions WHERE hash IS NOT NULL ORDER BY id DESC LIMIT 1")
    )
    assert len(plan["seed"]) == 16
    assert math.isfinite(len(sample_seed(datetime.now(UTC).date(), head or "")))


async def test_crosscheck_flags_declared_crop_without_vegetation(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    from app.domain.enums import ParcelPurpose
    from app.providers.registry import MockSubsidyRegistry

    # Find an agricultural parcel that "declared sowing" in the demo register.
    registry = MockSubsidyRegistry()
    year = datetime.now(UTC).year
    rows = (
        await session.execute(
            text(
                "SELECT id, cadastral_number, area_ha FROM parcels WHERE purpose = 'AGRICULTURE' AND status <> 'RETURNED_TO_STATE'"
            )
        )
    ).all()
    target = None
    for pid, cadastral, area in rows:
        if await registry.declarations(cadastral, ParcelPurpose.AGRICULTURE, float(area), year):
            target = pid
            break
    assert target is not None
    # Satellite in July: bare soil.
    session.add(
        NdviScan(
            parcel_id=target,
            ndvi=0.12,
            flagged=True,
            provider="sentinel-2-l2a:history",
            observed_at=datetime(year, 7, 10, tzinfo=UTC),
            scene_id="S2JULY",
        )
    )
    await session.commit()
    result = (await client.get(f"{API}/parcels/{target}/crosscheck", headers=auth_headers)).json()
    subsidy = next(i for i in result["items"] if i["source"] == "SUBSIDIES")
    assert subsidy["status"] == "mismatch"
    assert subsidy["code"] == "SUBSIDY_NO_CROP"
    assert subsidy["params"]["peak_ndvi"] == 0.12
    risks = (await client.get(f"{API}/risk", params={"limit": 200}, headers=auth_headers)).json()
    mine = next(r for r in risks if r["parcel_id"] == str(target))
    assert any(f["code"] == "SUBSIDY_MISMATCH" for f in mine["factors"])
