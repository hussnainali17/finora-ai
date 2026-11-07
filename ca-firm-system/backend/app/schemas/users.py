import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import StrictModel


class RoleOut(BaseModel):
    key: str
    name: str
    description: str
    permissions: list[str]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role_key: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(StrictModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role_key: str
    password: str = Field(min_length=1, max_length=128)


class UserUpdate(StrictModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role_key: str | None = None
    is_active: bool | None = None
