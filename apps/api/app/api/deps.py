"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.core.security import Inspector, verify_service_key, verify_token
from app.db.session import get_db
from app.providers.storage import StorageProvider, get_storage

_bearer = HTTPBearer(auto_error=False, description="Supabase access token (or local dev token)")


async def current_inspector(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Inspector:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthError("Authorization header with Bearer token required")
    return await verify_token(credentials.credentials)


async def service_key(x_service_key: Annotated[str | None, Header()] = None) -> None:
    verify_service_key(x_service_key)


def storage_dep() -> StorageProvider:
    return get_storage()


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentInspector = Annotated[Inspector, Depends(current_inspector)]
Storage = Annotated[StorageProvider, Depends(storage_dep)]
