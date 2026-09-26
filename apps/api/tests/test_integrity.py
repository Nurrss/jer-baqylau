"""Anti-tampering: the audit log is hash-chained; any edit of a past record is detected."""

from __future__ import annotations

import hashlib
import uuid

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Act, StatusTransition
from app.domain.audit_chain import GENESIS_HASH, transition_hash
from app.domain.enums import EntityType, ParcelStatus
from app.services import audit


async def test_seeded_chain_is_intact(session: AsyncSession) -> None:
    status = await audit.verify_chain(session)
    assert status.intact
    assert status.length > 50
    first = await session.scalar(select(StatusTransition).order_by(StatusTransition.id).limit(1))
    assert first is not None
    assert first.prev_hash == GENESIS_HASH


async def test_new_records_extend_the_chain(session: AsyncSession) -> None:
    head_before, length_before = await audit.chain_state(session)
    parcel_id = await session.scalar(text("SELECT id FROM parcels LIMIT 1"))
    row = await audit.record_transition(
        session,
        entity_type=EntityType.PARCEL,
        entity_id=parcel_id,
        from_status=ParcelStatus.OK,
        to_status=ParcelStatus.UNDER_CHECK,
        actor="inspector:test",
        comment="плановая проверка",
    )
    await session.flush()
    assert row.prev_hash == head_before
    assert row.hash == transition_hash(
        head_before,
        entity_type="PARCEL",
        entity_id=str(parcel_id),
        from_status="OK",
        to_status="UNDER_CHECK",
        actor="inspector:test",
        comment="плановая проверка",
        meta={},
        created_at=row.created_at,
    )
    status = await audit.verify_chain(session)
    assert status.intact
    assert status.length == length_before + 1


async def test_editing_a_past_record_breaks_the_chain(session: AsyncSession) -> None:
    victim = await session.scalar(
        select(StatusTransition.id).order_by(StatusTransition.id).offset(10).limit(1)
    )
    # An insider rewrites history directly in the database...
    await session.execute(
        text("UPDATE status_transitions SET comment = 'нарушений не выявлено' WHERE id = :id"), {"id": victim}
    )
    session.expire_all()
    status = await audit.verify_chain(session)
    # ...and verification pinpoints the altered record.
    assert not status.intact
    assert status.broken_at_id == victim


async def test_deleting_a_record_breaks_the_chain(session: AsyncSession) -> None:
    victim = await session.scalar(
        select(StatusTransition.id).order_by(StatusTransition.id).offset(5).limit(1)
    )
    await session.execute(text("DELETE FROM status_transitions WHERE id = :id"), {"id": victim})
    session.expire_all()
    status = await audit.verify_chain(session)
    assert not status.intact


async def test_act_is_registered_and_verifiable_publicly(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    hit = (
        await client.get("/api/v1/parcels/search", params={"q": "06:097:902:003"}, headers=auth_headers)
    ).json()[0]
    resp = await client.get(
        f"/api/v1/parcels/{hit['id']}/act.pdf", params={"lang": "kk"}, headers=auth_headers
    )
    assert resp.status_code == 200
    act = await session.scalar(select(Act).order_by(Act.created_at.desc()).limit(1))
    assert act is not None
    assert act.number in resp.headers["content-disposition"]

    public = (await client.get(f"/api/v1/public/acts/{act.id}")).json()  # no auth header: public
    assert public["number"] == act.number
    assert public["pdf_sha256"] == hashlib.sha256(resp.content).hexdigest()
    assert public["chain_at_issue"]["intact"] is True
    assert public["cadastral_number"] == "06:097:902:003"

    assert (await client.get(f"/api/v1/public/acts/{uuid.uuid4()}")).status_code == 404


async def test_act_shows_tampering_after_issue(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    hit = (
        await client.get("/api/v1/parcels/search", params={"q": "06:097:902:003"}, headers=auth_headers)
    ).json()[0]
    await client.get(f"/api/v1/parcels/{hit['id']}/act.pdf", headers=auth_headers)
    act = await session.scalar(select(Act).order_by(Act.created_at.desc()).limit(1))
    assert act is not None
    await session.execute(
        text(
            "UPDATE status_transitions SET actor = 'someone-else' WHERE id = (SELECT min(id) FROM status_transitions)"
        )
    )
    await session.commit()
    public = (await client.get(f"/api/v1/public/acts/{act.id}")).json()
    assert public["chain_at_issue"]["intact"] is False
