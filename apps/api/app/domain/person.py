"""Citizen identifiers: IIN check digit, phone normalization and masking (minimal personal data)."""

from __future__ import annotations

import re
from datetime import date

_W1 = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
_W2 = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)


def iin_is_valid(iin: str) -> bool:
    """Kazakhstan IIN: 12 digits, YYMMDD birth date, century/sex digit and a mod-11 check digit."""
    if not re.fullmatch(r"\d{12}", iin):
        return False
    d = [int(c) for c in iin]
    century = {1: 1800, 2: 1800, 3: 1900, 4: 1900, 5: 2000, 6: 2000}.get(d[6])
    if century is None:
        return False
    try:
        date(century + int(iin[0:2]), int(iin[2:4]), int(iin[4:6]))
    except ValueError:
        return False
    check = sum(a * b for a, b in zip(d[:11], _W1, strict=True)) % 11
    if check == 10:
        check = sum(a * b for a, b in zip(d[:11], _W2, strict=True)) % 11
        if check == 10:
            return False
    return check == d[11]


def mask_iin(iin: str) -> str:
    return "•" * 8 + iin[-4:]


def normalize_phone(phone: str) -> str | None:
    """+7 7XX XXX XX XX (Kazakhstan mobile) → '+77XXXXXXXXX', otherwise None."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return f"+{digits}" if re.fullmatch(r"77\d{9}", digits) else None


def mask_phone(phone: str) -> str:
    return f"+7 {phone[2:4]}• ••• {phone[-4:-2]} {phone[-2:]}"


def mask_name(full_name: str) -> str:
    """'Серикбаев Ерлан Нурланович' → 'Ерлан С.' (surname first, as in documents of Kazakhstan)."""
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if len(parts) >= 2:
        return f"{parts[1].capitalize()} {parts[0][0].upper()}."
    return parts[0].capitalize() if parts else "—"
