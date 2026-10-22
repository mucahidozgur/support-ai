"""Auth ile ilgili Pydantic modelleri."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login isteği; mock auth olduğu için içerik doğrulanmaz."""

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class TokenResponse(BaseModel):
    """Login sonucu dönen JWT token bilgisi."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # saniye


class UserInfo(BaseModel):
    """Token'dan çözülen kullanıcı bilgisi."""

    id: str  # UUID string
    username: str
