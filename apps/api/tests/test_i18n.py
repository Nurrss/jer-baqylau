"""Both languages must define exactly the same message ids (no missing Kazakh strings)."""

from __future__ import annotations

from fluent.syntax import FluentParser
from fluent.syntax.ast import Message

from app.core.i18n import LOCALES_DIR, resource_ids, t
from app.domain.enums import ApplicationStatus, Lang, ParcelStatus, SignalStatus


def _ids(lang: str) -> dict[str, set[str]]:
    parser = FluentParser()
    result: dict[str, set[str]] = {}
    for name in resource_ids():
        resource = parser.parse((LOCALES_DIR / lang / name).read_text(encoding="utf-8"))
        junk = [e for e in resource.body if e.__class__.__name__ == "Junk"]
        assert not junk, f"{lang}/{name} has syntax errors: {junk}"
        result[name] = {e.id.name for e in resource.body if isinstance(e, Message)}
    return result


def test_locale_files_match() -> None:
    assert sorted(p.name for p in (LOCALES_DIR / "kk").glob("*.ftl")) == resource_ids()


def test_same_keys_in_ru_and_kk() -> None:
    ru, kk = _ids("ru"), _ids("kk")
    for name in ru:
        assert ru[name] == kk[name], f"{name}: only ru={ru[name] - kk[name]}, only kk={kk[name] - ru[name]}"


def test_status_labels_exist_for_every_enum_value() -> None:
    for lang in Lang:
        for prefix, enum in (
            ("signal-status", SignalStatus),
            ("parcel-status", ParcelStatus),
            ("application-status", ApplicationStatus),
        ):
            for value in enum:
                key = f"{prefix}-{value.value}"
                assert t(lang, key) != key, f"missing {lang}:{key}"
