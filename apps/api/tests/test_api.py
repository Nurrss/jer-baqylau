"""HTTP contract: auth, parcels, signals, applications, dev endpoints, notifications."""

from __future__ import annotations

import io
import uuid

from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Lang, SubscriptionTarget
from app.providers.notification import LogNotificationProvider
from app.seed.loader import det_uuid
from app.services import applications as application_service
from app.services import outbox
from tests.conftest import SERVICE_HEADERS

API = "/api/v1"


async def _search_one(client: AsyncClient, headers: dict[str, str], q: str) -> dict:
    resp = await client.get(f"{API}/parcels/search", params={"q": q}, headers=headers)
    assert resp.status_code == 200
    return resp.json()[0]


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["database"] is True


async def test_protected_routes_require_token(client: AsyncClient) -> None:
    resp = await client.get(f"{API}/parcels")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    bad = await client.get(f"{API}/parcels", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    resp = await client.post(f"{API}/auth/login", json={"email": "inspector@jer.kz", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_parcels_geojson_and_filters(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(f"{API}/parcels", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert {"cadastral_number", "status", "area_ha", "is_overdue"} <= feature["properties"].keys()

    overdue = await client.get(f"{API}/parcels", params={"overdue": "true"}, headers=auth_headers)
    assert overdue.json()["features"]
    assert all(f["properties"]["is_overdue"] for f in overdue.json()["features"])

    red = await client.get(
        f"{API}/parcels", params=[("status", "VIOLATION"), ("status", "IN_REMEDIATION")], headers=auth_headers
    )
    assert {f["properties"]["status"] for f in red.json()["features"]} == {"VIOLATION", "IN_REMEDIATION"}

    # bbox far away → nothing
    empty = await client.get(f"{API}/parcels", params={"bbox": "10,10,11,11"}, headers=auth_headers)
    assert empty.json()["features"] == []
    bad = await client.get(f"{API}/parcels", params={"bbox": "1,2,3"}, headers=auth_headers)
    assert bad.status_code == 422


async def test_parcel_detail_has_card_data(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    hit = await _search_one(client, auth_headers, "06:097:902:003")
    resp = await client.get(f"{API}/parcels/{hit['id']}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "VIOLATION"
    assert detail["allowed_transitions"] == ["IN_REMEDIATION"]
    assert detail["photos"][0]["source"] == "INSPECTOR"
    assert detail["signals"][0]["status"] == "CONFIRMED"
    assert [h["to_status"] for h in detail["history"]][:2] == ["VIOLATION", "UNDER_CHECK"]

    missing = await client.get(f"{API}/parcels/{uuid.uuid4()}", headers=auth_headers)
    assert missing.status_code == 404


async def test_full_signal_to_resolution_cycle(
    client: AsyncClient, auth_headers: dict[str, str], notifications: LogNotificationProvider
) -> None:
    """Spec §6: citizen signal → UNDER_CHECK → confirm → VIOLATION → IN_REMEDIATION → RESOLVED."""
    hit = await _search_one(client, auth_headers, "06:097:904:009")
    last_id = (await client.get(f"{API}/events", headers=auth_headers)).json()["last_id"]

    sim = await client.post(
        f"{API}/dev/simulate-signal",
        json={
            "lat": hit["centroid"]["lat"],
            "lon": hit["centroid"]["lon"],
            "category": "ABANDONED",
            "chat_id": 777001,
            "lang": "kk",
            "photos": 1,
        },
        headers=SERVICE_HEADERS,
    )
    assert sim.status_code == 200, sim.text
    signal = sim.json()["signal"]
    assert sim.json()["parcel_status"] == "UNDER_CHECK"
    assert signal["parcel_id"] == hit["id"]
    assert signal["photos_count"] == 1

    events = (await client.get(f"{API}/events", params={"since": last_id}, headers=auth_headers)).json()
    assert {"signal.created", "parcel.status_changed"} <= {e["type"] for e in events["items"]}

    confirm = await client.post(
        f"{API}/signals/{signal['id']}/transitions",
        json={"to": "CONFIRMED", "comment": "Поле не обрабатывается"},
        headers=auth_headers,
    )
    assert confirm.status_code == 200, confirm.text
    parcel = (await client.get(f"{API}/parcels/{hit['id']}", headers=auth_headers)).json()
    assert parcel["status"] == "VIOLATION"
    assert parcel["violation_type"] == "UNUSED"  # mapped from ABANDONED
    assert parcel["deadline_at"] is not None

    skip = await client.post(
        f"{API}/parcels/{hit['id']}/transitions",
        json={"to": "RESOLVED", "comment": "skip"},
        headers=auth_headers,
    )
    assert skip.status_code == 409
    assert skip.json()["error"]["details"]["allowed"] == ["IN_REMEDIATION"]

    for target in ("IN_REMEDIATION", "RESOLVED"):
        step = await client.post(
            f"{API}/parcels/{hit['id']}/transitions",
            json={"to": target, "comment": f"Шаг {target}"},
            headers=auth_headers,
        )
        assert step.status_code == 200, step.text
        assert step.json()["status"] == target

    await outbox.drain()
    texts = [n.text for n in notifications.sent if n.chat_id == 777001]
    # signal confirmed + parcel in remediation + resolved, all in Kazakh
    assert len(texts) == 3
    assert "расталды" in texts[0]
    assert "жойылуда" in texts[1]
    assert "жойылды" in texts[2]


async def test_reject_signal_returns_parcel_to_ok(
    client: AsyncClient, auth_headers: dict[str, str], notifications: LogNotificationProvider
) -> None:
    hit = await _search_one(client, auth_headers, "06:097:904:008")
    sim = await client.post(
        f"{API}/dev/simulate-signal",
        json={"lat": hit["centroid"]["lat"], "lon": hit["centroid"]["lon"], "chat_id": 777002, "photos": 0},
        headers=SERVICE_HEADERS,
    )
    signal_id = sim.json()["signal"]["id"]
    reject = await client.post(
        f"{API}/signals/{signal_id}/transitions",
        json={"to": "REJECTED", "comment": "Мусор убран, нарушения нет"},
        headers=auth_headers,
    )
    assert reject.status_code == 200
    assert reject.json()["resolution_comment"] == "Мусор убран, нарушения нет"
    parcel = (await client.get(f"{API}/parcels/{hit['id']}", headers=auth_headers)).json()
    assert parcel["status"] == "OK"
    await outbox.drain()
    [message] = [n.text for n in notifications.sent if n.chat_id == 777002]
    assert "Мусор убран" in message


async def test_application_transition_notifies_subscribers(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
    notifications: LogNotificationProvider,
) -> None:
    application_id = det_uuid("application", "KZ-2026-042")
    await application_service.subscribe(
        session, 555001, Lang.KK, SubscriptionTarget.APPLICATION, application_id
    )
    await application_service.subscribe(
        session, 555002, Lang.RU, SubscriptionTarget.APPLICATION, application_id
    )
    # Each HTTP request in tests shares this session; persist the setup before a request that fails.
    await session.commit()

    bad = await client.post(
        f"{API}/applications/{application_id}/transitions",
        json={"to": "UNDER_REVIEW", "comment_ru": "назад", "comment_kk": "артқа"},
        headers=auth_headers,
    )
    assert bad.status_code == 409

    resp = await client.post(
        f"{API}/applications/{application_id}/transitions",
        json={"to": "APPROVED", "comment_ru": "Решение положительное", "comment_kk": "Шешім оң"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"
    assert resp.json()["subscribers_count"] == 2

    await outbox.drain()
    by_chat = {n.chat_id: n.text for n in notifications.sent}
    assert "мақұлданды" in by_chat[555001]
    assert "Шешім оң" in by_chat[555001]
    assert "одобрено" in by_chat[555002]
    assert "Решение положительное" in by_chat[555002]


async def test_inspection_date_required(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    application_id = det_uuid("application", "KZ-2026-037")
    resp = await client.post(
        f"{API}/applications/{application_id}/transitions",
        json={"to": "INSPECTION_SCHEDULED", "comment_ru": "Выезд", "comment_kk": "Барып шығу"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_dev_endpoints_require_service_key(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.post(
        f"{API}/dev/simulate-signal", json={"lat": 42.9, "lon": 71.37}, headers=auth_headers
    )
    assert resp.status_code == 403
    resp = await client.post(f"{API}/dev/demo-reset", headers={"X-Service-Key": "wrong"})
    assert resp.status_code == 403


def _jpeg_with_gps(lat: float, lon: float) -> bytes:
    image = Image.new("RGB", (64, 48), (120, 140, 90))
    exif = Image.Exif()

    def dms(value: float) -> tuple[float, float, float]:
        d = int(value)
        m = int((value - d) * 60)
        s = round(((value - d) * 60 - m) * 60, 4)
        return (float(d), float(m), s)

    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lon)}
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


async def test_photo_upload_extracts_exif_gps(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    hit = await _search_one(client, auth_headers, "06:097:901:004")
    resp = await client.post(
        f"{API}/parcels/{hit['id']}/photos",
        files=[("files", ("a.jpg", _jpeg_with_gps(42.9312, 71.3284), "image/jpeg"))],
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    uploaded = [p for p in resp.json()["photos"] if p["lat"] is not None]
    assert uploaded
    assert abs(uploaded[-1]["lat"] - 42.9312) < 1e-3
    assert abs(uploaded[-1]["lon"] - 71.3284) < 1e-3
    image = await client.get(uploaded[-1]["thumb_url"].replace("http://localhost:8000", ""))
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"

    junk = await client.post(
        f"{API}/parcels/{hit['id']}/photos",
        files=[("files", ("a.jpg", b"not an image", "image/jpeg"))],
        headers=auth_headers,
    )
    assert junk.status_code == 422
    assert junk.json()["error"]["code"] == "PHOTO_INVALID"


async def test_stats_and_exports(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    stats = (await client.get(f"{API}/stats/dashboard", headers=auth_headers)).json()
    assert stats["kpi"]["parcels_total"] >= 40
    assert len(stats["signals_by_day"]) == 14
    assert stats["upcoming_deadlines"][0]["days_left"] < 0  # overdue first
    csv = await client.get(f"{API}/export/parcels.csv", headers=auth_headers)
    assert csv.status_code == 200
    assert csv.text.splitlines()[0].lstrip("﻿").startswith("cadastral_number,")
    geo = await client.get(f"{API}/export/parcels.geojson", headers=auth_headers)
    assert geo.json()["type"] == "FeatureCollection"
    ndvi = (await client.get(f"{API}/satellite/ndvi", headers=auth_headers)).json()
    assert ndvi["is_demo"] is True
    assert any(r["flagged"] for r in ndvi["readings"])


async def test_inspection_act_pdf_in_both_languages(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    hit = await _search_one(client, auth_headers, "06:097:902:003")
    for lang in ("ru", "kk"):
        resp = await client.get(
            f"{API}/parcels/{hit['id']}/act.pdf", params={"lang": lang}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert f"_{lang}.pdf" in resp.headers["content-disposition"]
