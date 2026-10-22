"""Auth endpoint'leri: mock login + token doğrulama."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, deterministic_user_id
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Mock login: her username+password ikilisi için token üretir."""
    user_id = deterministic_user_id(req.username)
    token = create_access_token(user_id, req.username)
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().JWT_EXPIRE_MIN * 60,
    )


@router.get("/me", response_model=UserInfo)
async def me(current_user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
    """Token sahibinin bilgilerini döndürür."""
    return current_user
