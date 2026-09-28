"""State land fund: Mini App applications confirmed in Telegram, allocation, owner inspections."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.telegram_webapp import sign_init_data
from app.db.models import Parcel
from app.domain import person
from app.domain.enums import AllocationStatus, Lang, OwnerType, ParcelStatus
from app.providers.notification import LogNotificationProvider
from app.services import land

API = "/api/v1"
BOT_TOKEN = "123456:TEST-TOKEN"
CITIZEN = 777_000_111
OTHER_CITIZEN = 777_000_222
VALID_IIN = "900101300017"  # synthetic, passes the check digit


@pytest.fixture(autouse=True)
def _bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_bot_token", SecretStr(BOT_TOKEN))
    monkeypatch.setattr(get_settings(), "public_web_url", "https://jer.example")


def init_data(chat_id: int, *, token: str = BOT_TOKEN, lang: str = "ru") -> str:
    user = json.dumps({"id": chat_id, "first_name": "Ерлан", "language_code": lang}, separators=(",", ":"))
    return sign_init_data({"auth_date": str(int(time.time())), "query_id": "AAE", "user": user}, token)


def tg(chat_id: int, **kwargs: Any) -> dict[str, str]:
    return {"X-Telegram-Init-Data": init_data(chat_id, **kwargs)}


async def _fund(client: AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(f"{API}/land/fund")
    assert resp.status_code == 200, resp.text
    return [f["properties"] for f in resp.json()["features"]]


def _body(parcel_ids: list[str], **overrides: Any) -> dict[str, Any]:
    return {
        "parcel_ids": parcel_ids,
        "full_name": "Серикбаев Ерлан Нурланович",
        "iin": VALID_IIN,
        "phone": "8 701 234 56 78",
        "comment": "Многодетная семья",
        **overrides,
    }


def test_iin_and_masking() -> None:
    assert person.iin_is_valid(VALID_IIN)
    assert not person.iin_is_valid("900101300014")
    assert not person.iin_is_valid("901301300013")  # month 13
    assert person.normalize_phone("8 (701) 234-56-78") == "+77012345678"
    assert person.normalize_phone("+1 202 555 0100") is None
    assert person.mask_name("Серикбаев Ерлан Нурланович") == "Ерлан С."
    assert person.mask_iin(VALID_IIN).endswith("0017")


async def test_mini_app_requires_a_valid_telegram_signature(client: AsyncClient) -> None:
    fund = await _fund(client)
    body = _body([fund[0]["id"]])
    assert (await client.post(f"{API}/miniapp/applications", json=body)).status_code == 401
    forged = await client.post(
        f"{API}/miniapp/applications", json=body, headers=tg(CITIZEN, token="999:OTHER")
    )
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "TELEGRAM_AUTH_INVALID"


async def test_full_cycle_apply_confirm_approve_inspect(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
    notifications: LogNotificationProvider,
) -> None:
    fund = await _fund(client)
    housing = [p for p in fund if p["purpose"] == "IZHS" and p["allocation_status"] == "OFFERED"]
    assert len(housing) >= 3
    first, second = housing[0]["id"], housing[1]["id"]

    # 1. Mini App: pick two parcels (by priority) → draft + confirmation message in Telegram.
    resp = await client.post(
        f"{API}/miniapp/applications", json=_body([first, second]), headers=tg(CITIZEN, lang="kk")
    )
    assert resp.status_code == 201, resp.text
    draft = resp.json()
    assert draft["status"] == "DRAFT"
    assert draft["type"] == "IZHS_ALLOCATION"
    message = next(n for n in notifications.sent if n.chat_id == CITIZEN)
    assert f"land:confirm:{draft['id']}" in [b.callback_data for b in message.buttons]
    assert "ЖСН" in message.text  # the citizen's language (kk) from Telegram
    # Drafts are not the akimat's business yet.
    panel = (await client.get(f"{API}/applications", headers=auth_headers)).json()["items"]
    assert draft["tracking_number"] not in [a["tracking_number"] for a in panel]

    # 2. The citizen taps «Confirm» in the chat.
    application = await land.confirm(session, uuid.UUID(draft["id"]), CITIZEN, Lang.KK)
    await session.commit()
    assert application.status.value == "UNDER_REVIEW"
    statuses = {p["id"]: p["allocation_status"] for p in await _fund(client)}
    assert statuses[first] == statuses[second] == "RESERVED"

    # Someone else cannot apply for the reserved parcel.
    taken = await client.post(f"{API}/miniapp/applications", json=_body([first]), headers=tg(OTHER_CITIZEN))
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "PARCEL_TAKEN"

    # 3. The akimat sees it with the parcels and masked contacts, and approves the second choice.
    panel = (await client.get(f"{API}/applications", headers=auth_headers)).json()["items"]
    item = next(a for a in panel if a["tracking_number"] == draft["tracking_number"])
    assert [p["id"] for p in item["parcels"]] == [first, second]
    assert item["applicant_name"] == "Ерлан С."
    assert item["applicant_iin_masked"].endswith("0017")
    approved = await client.post(
        f"{API}/applications/{draft['id']}/transitions",
        json={
            "to": "APPROVED",
            "comment_ru": "Участок предоставлен",
            "comment_kk": "Учаске берілді",
            "grant_parcel_ids": [second],
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    granted = await session.get(Parcel, uuid.UUID(second))
    released = await session.get(Parcel, uuid.UUID(first))
    assert granted is not None
    assert released is not None
    await session.refresh(granted)
    await session.refresh(released)
    assert granted.allocation_status is AllocationStatus.ALLOCATED
    assert granted.owner_chat_id == CITIZEN
    assert granted.owner_type is OwnerType.PRIVATE
    assert released.allocation_status is AllocationStatus.OFFERED

    # 4. Remote inspection of the new owner: the link goes straight to their Telegram, no QR.
    notifications.sent.clear()
    resp = await client.post(
        f"{API}/parcels/{second}/inspection-requests",
        json={"due_hours": 48, "note": "Покажите участок"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_telegram"] is True
    sent = next(n for n in notifications.sent if n.chat_id == CITIZEN)
    web_app = next(b.web_app_url for b in sent.buttons if b.web_app_url)
    assert web_app.startswith("https://jer.example/inspect/")
    assert "lang=kk" in web_app


async def test_fund_parcel_cannot_be_inspected_and_drafts_are_citizen_only(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    fund = await _fund(client)
    free = next(p for p in fund if p["allocation_status"] == "OFFERED")
    resp = await client.post(
        f"{API}/parcels/{free['id']}/inspection-requests", json={"due_hours": 24}, headers=auth_headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PARCEL_IN_FUND"

    draft = (
        await client.post(f"{API}/miniapp/applications", json=_body([free["id"]]), headers=tg(CITIZEN))
    ).json()
    resp = await client.post(
        f"{API}/applications/{draft['id']}/transitions",
        json={"to": "APPROVED", "comment_ru": "Одобрено", "comment_kk": "Мақұлданды"},
        headers=auth_headers,
    )
    assert resp.status_code == 409  # only the citizen confirms a draft
    # Cancelling in the chat keeps the parcel free.
    await land.cancel(session, uuid.UUID(draft["id"]), CITIZEN)
    await session.commit()
    statuses = {p["id"]: p["allocation_status"] for p in await _fund(client)}
    assert statuses[free["id"]] == "OFFERED"


async def test_validation_mixed_purpose_and_bad_iin(client: AsyncClient) -> None:
    fund = [p for p in await _fund(client) if p["allocation_status"] == "OFFERED"]
    housing = next(p["id"] for p in fund if p["purpose"] == "IZHS")
    field = next(p["id"] for p in fund if p["purpose"] == "AGRICULTURE")
    mixed = await client.post(
        f"{API}/miniapp/applications", json=_body([housing, field]), headers=tg(CITIZEN)
    )
    assert mixed.json()["error"]["code"] == "PARCELS_MIXED_PURPOSE"
    bad = await client.post(
        f"{API}/miniapp/applications", json=_body([housing], iin="123456789012"), headers=tg(CITIZEN)
    )
    assert bad.json()["error"]["code"] == "IIN_INVALID"


async def test_returned_parcel_goes_back_to_citizens(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    returned = await session.scalar(
        select(Parcel).where(Parcel.status == ParcelStatus.RETURNED_TO_STATE).limit(1)
    )
    assert returned is not None
    resp = await client.post(f"{API}/parcels/{returned.id}/offer", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["allocation_status"] == "OFFERED"
    assert str(returned.id) in [p["id"] for p in await _fund(client)]
    back = await client.delete(f"{API}/parcels/{returned.id}/offer", headers=auth_headers)
    assert back.json()["allocation_status"] == "NONE"
