"""Knowledge base for the bot: procedures loaded from packages/seed/knowledge/{lang}/*.yaml."""

from __future__ import annotations

from functools import lru_cache

import yaml
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SEED_DIR
from app.db.models import KnowledgeQuestion
from app.domain.enums import Lang

KNOWLEDGE_DIR = SEED_DIR / "knowledge"
MAX_QUESTION_LENGTH = 1000


class Link(BaseModel):
    title: str
    url: HttpUrl


class Article(BaseModel):
    id: str
    order: int
    emoji: str
    title: str
    summary: str
    steps: list[str]
    documents: list[str]
    terms: str
    fee: str
    where: str
    links: list[Link]
    note: str | None = None


@lru_cache
def articles(lang: Lang) -> tuple[Article, ...]:
    items = [
        Article.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted((KNOWLEDGE_DIR / lang.value).glob("*.yaml"))
    ]
    return tuple(sorted(items, key=lambda a: a.order))


def article(lang: Lang, article_id: str) -> Article | None:
    return next((a for a in articles(lang) if a.id == article_id), None)


async def save_question(
    session: AsyncSession, chat_id: int, lang: Lang, topic: str | None, text: str
) -> None:
    session.add(
        KnowledgeQuestion(chat_id=chat_id, lang=lang, topic=topic, text=text.strip()[:MAX_QUESTION_LENGTH])
    )
