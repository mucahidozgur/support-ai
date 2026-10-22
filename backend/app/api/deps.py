"""FastAPI bağımlılıkları: Bearer token doğrulama."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.schemas.auth import UserInfo

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> UserInfo:
    """Bearer token'ı çözer ve UserInfo döndürür; hata olursa 401."""
    payload = decode_token(creds.credentials)
    try:
        return UserInfo(id=payload["sub"], username=payload["username"])
    except KeyError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
