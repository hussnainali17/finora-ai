import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import StrictModel

CurrencyCode = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    legal_name: str | None
    base_currency: str
    fiscal_year_end_month: int
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ClientCreate(StrictModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)
    base_currency: str = CurrencyCode
    fiscal_year_end_month: int = Field(default=12, ge=1, le=12)
    notes: str | None = Field(default=None, max_length=4000)


class ClientUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)
    fiscal_year_end_month: int | None = Field(default=None, ge=1, le=12)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    label: str
    start_date: date
    end_date: date
    status: str
    closed_at: datetime | None
    created_at: datetime


class PeriodCreate(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _ordered(self) -> "PeriodCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class PeriodUpdate(StrictModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    start_date: date | None = None
    end_date: date | None = None


class AccessGrant(StrictModel):
    user_id: uuid.UUID


class AccessOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role_key: str
    granted_at: datetime
