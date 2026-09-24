"""Fluent-based localization for the bot and citizen notifications.

Messages live in ``app/locales/<lang>/*.ftl``. A test asserts that both
languages define exactly the same message ids.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fluent.runtime import FluentLocalization, FluentResourceLoader

from app.domain.enums import Lang

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
FLUENT_LOCALES: dict[Lang, list[str]] = {Lang.RU: ["ru"], Lang.KK: ["kk", "ru"]}


def resource_ids() -> list[str]:
    return sorted(p.name for p in (LOCALES_DIR / "ru").glob("*.ftl"))


@lru_cache
def _localization(lang: Lang) -> FluentLocalization:
    loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}"))
    return FluentLocalization(FLUENT_LOCALES[lang], resource_ids(), loader, use_isolating=False)


def _prepare(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if value is None:
        return ""
    if hasattr(value, "value") and isinstance(value.value, str):  # StrEnum
        return value.value
    return value


def t(lang: Lang | str | None, key: str, **kwargs: Any) -> str:
    """Translate ``key`` for ``lang`` (defaults to Russian)."""
    try:
        resolved = Lang(lang) if lang else Lang.RU
    except ValueError:
        resolved = Lang.RU
    args = {name: _prepare(value) for name, value in kwargs.items()}
    return _localization(resolved).format_value(key, args)


def has_key(lang: Lang, key: str) -> bool:
    return t(lang, key) != key
