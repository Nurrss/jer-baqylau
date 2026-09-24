"""Tracking numbers: formatting and tolerant parsing of user input."""

from __future__ import annotations

import re

_APPLICATION_RE = re.compile(
    r"^[\s#№]*(?:KZ|КЗ|ҚЗ)?[\s\-_./#№]*(\d{4})[\s\-_./]+(\d{1,5})\s*$", re.IGNORECASE
)
_APPLICATION_SHORT_RE = re.compile(r"^[\s#№]*(?:KZ|КЗ|ҚЗ)[\s\-_./#№]*(\d{1,5})\s*$", re.IGNORECASE)
_SIGNAL_RE = re.compile(r"^\s*(?:SIG|СИГ)?[\s\-_./#№]*(\d{4})[\s\-_./]+(\d{1,6})\s*$", re.IGNORECASE)


def format_application_number(year: int, seq: int) -> str:
    return f"KZ-{year}-{seq:03d}"


def format_signal_code(year: int, seq: int) -> str:
    return f"SIG-{year}-{seq:04d}"


def normalize_application_number(raw: str, default_year: int) -> str | None:
    """Normalize free-form input to ``KZ-YYYY-NNN``.

    Accepts e.g. ``kz 2026 42``, ``KZ-2026-042``, ``кз/2026/42``, ``2026-42`` or ``KZ 42``
    (the latter uses ``default_year``). Returns ``None`` if the input is not recognizable.
    """
    text = raw.strip()
    match = _APPLICATION_RE.match(text)
    if match:
        year, seq = int(match.group(1)), int(match.group(2))
    else:
        short = _APPLICATION_SHORT_RE.match(text)
        if not short:
            return None
        year, seq = default_year, int(short.group(1))
    if seq <= 0 or not 2000 <= year <= 2100:
        return None
    return format_application_number(year, seq)


def normalize_signal_code(raw: str) -> str | None:
    match = _SIGNAL_RE.match(raw.strip())
    if not match:
        return None
    year, seq = int(match.group(1)), int(match.group(2))
    if seq <= 0 or not 2000 <= year <= 2100:
        return None
    return format_signal_code(year, seq)


def mask_person_name(full_name: str) -> str:
    """``Серкулов Ерлан`` / ``Ерлан Серкулов`` → ``Ерлан С.`` (given name + surname initial).

    Input is expected as "Given Surname"; extra parts are ignored.
    """
    parts = [p for p in full_name.split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0].upper()}."
