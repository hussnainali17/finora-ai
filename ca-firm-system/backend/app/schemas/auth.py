import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import StrictModel


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    firm_id: uuid.UUID
    firm_name: str
    role: str
    permissions: list[str]


class TokenResponse(BaseModel):
    """The refresh token is NOT in the body: it travels only in an HttpOnly cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: CurrentUser

    model_config = ConfigDict(from_attributes=True)
