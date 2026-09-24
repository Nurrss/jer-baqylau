from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentInspector
from app.core.config import AuthMode, get_settings
from app.core.errors import AuthError, ForbiddenError
from app.core.security import check_demo_credentials, issue_local_token
from app.schemas.common import ERROR_RESPONSES
from app.schemas.misc import AuthConfig, InspectorOut, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


@router.get("/config", response_model=AuthConfig, summary="Which login flow the web panel must use")
async def auth_config() -> AuthConfig:
    return AuthConfig(mode=get_settings().auth_mode.value)


@router.post("/login", response_model=TokenResponse, summary="Local dev login (AUTH_MODE=local only)")
async def login(body: LoginRequest) -> TokenResponse:
    settings = get_settings()
    if settings.auth_mode is not AuthMode.LOCAL:
        raise ForbiddenError("Local login is disabled; use Supabase Auth", code="LOCAL_LOGIN_DISABLED")
    if not check_demo_credentials(settings, body.email, body.password):
        raise AuthError("Invalid email or password", code="INVALID_CREDENTIALS")
    token, ttl = issue_local_token(settings, settings.demo_inspector_email, settings.demo_inspector_name)
    return TokenResponse(
        access_token=token,
        expires_in=ttl,
        user=InspectorOut(
            id=f"local:{settings.demo_inspector_email}",
            email=settings.demo_inspector_email,
            name=settings.demo_inspector_name,
        ),
    )


@router.get("/me", response_model=InspectorOut)
async def me(inspector: CurrentInspector) -> InspectorOut:
    return InspectorOut(id=inspector.id, email=inspector.email, name=inspector.name)
