"""Tamper-evident audit log: every status transition is hash-linked to the previous one.

``hash = sha256(prev_hash + canonical_json(record))``. Editing or deleting any past record changes
its hash and breaks every link after it, which :func:`app.services.audit.verify_chain` detects.
The same canonical form is used by the service, the migration backfill and the tests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def transition_hash(
    prev_hash: str,
    *,
    entity_type: str,
    entity_id: str,
    from_status: str | None,
    to_status: str,
    actor: str,
    comment: str | None,
    meta: dict[str, Any] | None,
    created_at: datetime,
) -> str:
    record = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "from": from_status,
        "to": to_status,
        "actor": actor,
        "comment": comment,
        "meta": meta or {},
        "created_at": canonical_time(created_at),
    }
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()
