"""Inspector authentication (Supabase JWT or local dev JWT) and service-key auth."""

from __future__ import annotations

import asyncio
import hmac
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import AuthMode, Settings, get_settings
from app.core.errors import AuthError, ForbiddenError

LOCAL_ISSUER = "jer-local"
LOCAL_TOKEN_TTL_SECONDS = 12 * 3600
SUPABASE_AUDIENCE = "authenticated"


@dataclass(frozen=True, slots=True)
class Inspector:
    id: str
    email: str | None
    name: str

    @property
    def actor(self) -> str:
        return f"inspector:{self.email or self.id}"


@lru_cache
def _jwks_client(supabase_url: str) -> PyJWKClient:
    return PyJWKClient(
        f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600
    )


def issue_local_token(settings: Settings, email: str, name: str) -> tuple[str, int]:
    now = int(time.time())
    payload = {
        "sub": f"local:{email}",
        "email": email,
        "name": name,
        "role": "authenticated",
        "iss": LOCAL_ISSUER,
        "iat": now,
        "exp": now + LOCAL_TOKEN_TTL_SECONDS,
    }
    token = jwt.encode(payload, settings.local_jwt_secret.get_secret_value(), algorithm="HS256")
    return token, LOCAL_TOKEN_TTL_SECONDS


def check_demo_credentials(settings: Settings, email: str, password: str) -> bool:
    email_ok = hmac.compare_digest(email.strip().lower(), settings.demo_inspector_email.lower())
    password_ok = hmac.compare_digest(password, settings.demo_inspector_password.get_secret_value())
    return email_ok and password_ok


def _claims_to_inspector(claims: dict[str, Any]) -> Inspector:
    if claims.get("role") != "authenticated":
        raise ForbiddenError("Inspector role required")
    metadata = claims.get("user_metadata") or {}
    email = claims.get("email")
    name = claims.get("name") or metadata.get("full_name") or metadata.get("name") or email or "Inspector"
    return Inspector(id=str(claims["sub"]), email=email, name=str(name))


async def verify_token(token: str, settings: Settings | None = None) -> Inspector:
    settings = settings or get_settings()
    try:
        if settings.auth_mode is AuthMode.LOCAL:
            claims = jwt.decode(
                token,
                settings.local_jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                issuer=LOCAL_ISSUER,
                options={"require": ["exp", "sub"]},
            )
        else:
            header = jwt.get_unverified_header(token)
            if header.get("alg") == "HS256":
                secret = settings.supabase_jwt_secret.get_secret_value()
                if not secret:
                    raise AuthError("HS256 tokens are not accepted (SUPABASE_JWT_SECRET is not set)")
                key: Any = secret
            else:
                client = _jwks_client(settings.supabase_url)
                signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
                key = signing_key.key
            claims = jwt.decode(
                token,
                key,
                algorithms=["HS256", "RS256", "ES256"],
                audience=SUPABASE_AUDIENCE,
                options={"require": ["exp", "sub"]},
            )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired", code="TOKEN_EXPIRED") from exc
    except (jwt.PyJWTError, KeyError) as exc:
        raise AuthError("Invalid token") from exc
    return _claims_to_inspector(claims)


def verify_service_key(provided: str | None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    expected = settings.service_api_key.get_secret_value()
    if not provided or not expected or not hmac.compare_digest(provided, expected):
        raise ForbiddenError("Valid X-Service-Key header required")
