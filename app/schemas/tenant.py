from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())

        v = v.upper()

        if not re.match(r"^[A-Z\s]+$", v):
            raise ValueError("Tenant name must contain only alphabets and spaces")

        return v


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = " ".join(v.split())

        v = v.upper()

        if not re.match(r"^[A-Z\s]+$", v):
            raise ValueError("Tenant name must contain only alphabets and spaces")

        return v


class TenantResponse(TenantBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
