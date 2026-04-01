from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

    @field_validator("name", mode="before")
    def validate_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = " ".join(v.split()).upper()

        if not re.match(r"^[A-Z\s]+$", v):
            raise ValueError("Tenant name must contain only alphabets and spaces")

        return v


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = " ".join(v.split()).upper()

        if v is not None and not re.match(r"^[A-Z\s]+$", v):
            raise ValueError("Tenant name must contain only alphabets and spaces")

        return v


class TenantResponse(TenantBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
