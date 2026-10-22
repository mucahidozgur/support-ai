"""JWT üretim/doğrulama yardımcıları (mock auth için)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from jose import JWTError, jwt

from app.core.config import get_settings


def create_access_token(user_id: str, username: str) -> str:
    """Kullanıcı için JWT erişim token'ı üretir."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MIN),
        "iat": now,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict[str, object]:
    """JWT'yi çözer; geçersiz/süresi dolmuşsa 401 fırlatır."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def deterministic_user_id(username: str) -> str:
    """Aynı username için her zaman aynı user_id üretir (kalıcı user tablosu yok)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, username))
