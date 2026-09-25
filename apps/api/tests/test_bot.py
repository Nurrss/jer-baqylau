"""Bot scenarios driven through the real Dispatcher with a fake Telegram session.

The fake session records every Bot API call and returns plausible objects, so the
handlers, FSM, localization and services run exactly as in production.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, File, Message, Update
from sqlalchemy import func, select, text

from app.bot import common
from app.bot.common import AppCb, KbCb, LangCb, ReportCb
from app.bot.handlers import report
from app.bot.runtime import build_dispatcher, process_update
from app.core.i18n import t
from app.db.models import Photo, Signal, Subscription
from app.db.session import session_scope
from app.domain.enums import Lang, PhotoOwnerType
from app.services import geocoding
from app.services.placeholders import placeholder_photo

_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append(method)
        returning = method.__returning__
        if returning is bool:
            return True
        if returning is File:
            return File(file_id="f", file_unique_id="u", file_path="photos/test.jpg")
        chat_id = getattr(method, "chat_id", None) or 1
        return Message(
            message_id=next(_ids),
            date=int(time.time()),
            chat=Chat(id=int(chat_id), type="private"),
            text=getattr(method, "text", None),
        )

    async def stream_content(self, url: str, headers: Any = None, timeout: int = 30, chunk_size: int = 65536,
                             raise_for_status: bool = True) -> AsyncGenerator[bytes, None]:  # fmt: skip
        yield placeholder_photo("bot-test")

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(getattr(c, "text", None), str)]


class Citizen:
    """Sends updates as one Telegram user."""

    def __init__(self, bot: Bot, dp: Dispatcher, session: FakeSession, chat_id: int):
        self.bot, self.dp, self.session, self.chat_id = bot, dp, session, chat_id
        self.last_message_id = 1

    def _user(self) -> dict[str, Any]:
        return {"id": self.chat_id, "is_bot": False, "first_name": "Тест"}

    def _message(self, **extra: Any) -> dict[str, Any]:
        self.last_message_id += 1
        return {
            "message_id": self.last_message_id,
            "date": int(time.time()),
            "chat": {"id": self.chat_id, "type": "private"},
            "from": self._user(),
            **extra,
        }

    async def _feed(self, payload: dict[str, Any]) -> list[str]:
        before = len(self.session.calls)
        update = Update.model_validate(
            {"update_id": next(_ids) + 10_000_000, **payload}, context={"bot": self.bot}
        )
        await process_update(self.bot, self.dp, update)
        await asyncio.sleep(0)
        return [c.text for c in self.session.calls[before:] if isinstance(getattr(c, "text", None), str)]

    async def send(self, **message: Any) -> list[str]:
        return await self._feed({"message": self._message(**message)})

    async def click(self, data: str) -> list[str]:
        return await self._feed(
            {
                "callback_query": {
                    "id": str(next(_ids)),
                    "from": self._user(),
                    "chat_instance": "ci",
                    "data": data,
                    "message": self._message(text="…"),
                }
            }
        )


_shared: dict[str, Any] = {}


@pytest.fixture
async def bot_env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Bot, Dispatcher, FakeSession]]:
    async def no_network(lat: float, lon: float, lang: Lang) -> str | None:
        return "Тараз, тестовая улица"

    monkeypatch.setattr(geocoding, "_fetch", no_network)
    monkeypatch.setattr(report, "PHOTO_ACK_DELAY", 0.01)
    common.clear_lang_cache()
    # Routers attach to one Dispatcher only (as in production): share it; tests use distinct chat ids.
    if "dp" not in _shared:
        _shared["dp"] = build_dispatcher(MemoryStorage())
    session = FakeSession()
    bot = Bot(token="42:TEST", session=session)
    yield bot, _shared["dp"], session
    await asyncio.gather(*report._background, return_exceptions=True)


async def _free_ok_parcel_centroid() -> tuple[float, float]:
    """An OK parcel with no signal within 100 m (taken from the end so other tests don't collide)."""
    async with session_scope() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT ST_Y(p.centroid), ST_X(p.centroid) FROM parcels p
                     WHERE p.status = 'OK' AND NOT EXISTS (
                       SELECT 1 FROM signals s WHERE ST_DWithin(s.location::geography, p.geometry::geography, 100))
                  ORDER BY p.cadastral_number DESC LIMIT 1
                    """
                )
            )
        ).one()
    return float(row[0]), float(row[1])


async def test_first_start_asks_language_then_welcomes_in_kazakh(
    bot_env: tuple[Bot, Dispatcher, FakeSession],
) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_001)
    replies = await citizen.send(text="/start")
    assert replies == [t(Lang.KK, "choose-lang")]
    replies = await citizen.click(LangCb(code="kk").pack())
    assert any("ЖерБақылау" in r and "Сәлеметсіз бе" in r for r in replies)
    # Next /start goes straight to the menu in the saved language.
    replies = await citizen.send(text="/start")
    assert "Сәлеметсіз бе" in replies[0]


async def test_application_status_normalizes_number_and_subscribes(
    bot_env: tuple[Bot, Dispatcher, FakeSession],
) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_002)
    await common.set_user_lang(citizen.chat_id, Lang.RU)

    await citizen.send(text=t(Lang.RU, "menu-status"))
    assert await citizen.send(text="hello") == [t(Lang.RU, "status-bad-format")]
    assert "не найдено" in (await citizen.send(text="kz 2026 999"))[0]

    replies = await citizen.send(text="kz 2026 42")
    card = replies[0]
    assert "KZ-2026-042" in card
    assert "✅ Подано → ✅ Рассмотрение → ⏳ Выезд инспектора → ▫️ Решение" in card

    from app.seed.loader import det_uuid

    app_id = det_uuid("application", "KZ-2026-042")
    await citizen.click(AppCb(action="sub", id=str(app_id)).pack())
    async with session_scope() as db:
        count = await db.scalar(
            select(func.count()).select_from(Subscription).where(Subscription.chat_id == citizen.chat_id)
        )
    assert count == 1
    await citizen.click(AppCb(action="unsub", id=str(app_id)).pack())


async def test_menu_press_during_number_input_is_not_a_number(
    bot_env: tuple[Bot, Dispatcher, FakeSession],
) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_003)
    await common.set_user_lang(citizen.chat_id, Lang.RU)
    await citizen.send(text=t(Lang.RU, "menu-status"))
    replies = await citizen.send(text=t(Lang.RU, "menu-knowledge"))
    assert replies == [t(Lang.RU, "kb-list")]


async def test_knowledge_paging(bot_env: tuple[Bot, Dispatcher, FakeSession]) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_004)
    await common.set_user_lang(citizen.chat_id, Lang.KK)
    await citizen.send(text=t(Lang.KK, "menu-knowledge"))
    step = await citizen.click(KbCb(action="step", id="izhs", n=2).pack())
    assert "2-қадамы" in step[0]
    docs = await citizen.click(KbCb(action="docs", id="izhs").pack())
    assert "egov.kz" in docs[0]
    await citizen.click(KbCb(action="ask", id="izhs").pack())
    assert await citizen.send(text="Сколько ждать в очереди?") == [t(Lang.KK, "kb-question-saved")]


async def test_report_flow_creates_signal_with_photo(bot_env: tuple[Bot, Dispatcher, FakeSession]) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_005)
    await common.set_user_lang(citizen.chat_id, Lang.RU)
    lat, lon = await _free_ok_parcel_centroid()

    assert "Выберите категорию" in (await citizen.send(text=t(Lang.RU, "menu-report")))[0]
    await citizen.click(ReportCb(action="cat", value="DUMP").pack())
    # Outside the region → asked again.
    assert await citizen.send(location={"latitude": 51.13, "longitude": 71.43}) == [
        t(Lang.RU, "report-out-of-region")
    ]
    assert "фото" in (await citizen.send(location={"latitude": lat, "longitude": lon}))[0]
    # Done without photos is refused.
    assert await citizen.send(text=t(Lang.RU, "btn-done")) == [t(Lang.RU, "report-photo-required")]
    await citizen.send(photo=[{"file_id": "p1", "file_unique_id": "u1", "width": 10, "height": 10}])
    await asyncio.sleep(0.05)
    assert any("Получено фото: 1" in s for s in session.texts())
    # A non-image document is rejected.
    replies = await citizen.send(
        document={"file_id": "d1", "file_unique_id": "du", "mime_type": "application/pdf"}
    )
    assert replies == [t(Lang.RU, "report-photo-not-image")]
    await citizen.send(text=t(Lang.RU, "btn-done"))
    assert "Слишком длинно" in (await citizen.send(text="x" * 501))[0]
    summary = await citizen.send(text="Свалка строительного мусора")
    assert any("Проверьте обращение" in s and "Тараз, тестовая улица" in s for s in summary)

    accepted = await citizen.click(ReportCb(action="submit").pack())
    assert any("принят" in s and "SIG-" in s for s in accepted)
    await asyncio.gather(*report._background)

    async with session_scope() as db:
        signal = await db.scalar(
            select(Signal)
            .where(Signal.reporter_chat_id == citizen.chat_id)
            .order_by(Signal.created_at.desc())
        )
        assert signal is not None
        assert signal.description == "Свалка строительного мусора"
        assert signal.address == "Тараз, тестовая улица"
        assert signal.parcel_id is not None
        photos = await db.scalar(
            select(func.count()).where(Photo.owner_type == PhotoOwnerType.SIGNAL, Photo.owner_id == signal.id)
        )
        assert photos == 1


async def test_cancel_at_any_step_returns_to_menu(bot_env: tuple[Bot, Dispatcher, FakeSession]) -> None:
    bot, dp, session = bot_env
    citizen = Citizen(bot, dp, session, chat_id=810_006)
    await common.set_user_lang(citizen.chat_id, Lang.RU)
    await citizen.send(text=t(Lang.RU, "menu-report"))
    await citizen.click(ReportCb(action="cat", value="OTHER").pack())
    assert await citizen.send(text=t(Lang.RU, "btn-cancel")) == [t(Lang.RU, "cancelled")]
    # After cancelling, free text is not treated as a location/photo.
    assert await citizen.send(text="привет") == [t(Lang.RU, "unknown")]


async def test_duplicate_update_is_processed_once(bot_env: tuple[Bot, Dispatcher, FakeSession]) -> None:
    bot, dp, session = bot_env
    await common.set_user_lang(810_007, Lang.RU)
    payload = {
        "update_id": 99_000_001,
        "message": {
            "message_id": 5,
            "date": int(time.time()),
            "chat": {"id": 810_007, "type": "private"},
            "from": {"id": 810_007, "is_bot": False, "first_name": "Т"},
            "text": "/start",
        },
    }
    for _ in range(2):
        await process_update(bot, dp, Update.model_validate(payload, context={"bot": bot}))
    assert len(session.texts()) == 1
