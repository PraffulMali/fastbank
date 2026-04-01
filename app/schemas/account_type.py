from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountTypeCreate(BaseModel):
    name: str = Field(
        ..., min_length=2, max_length=100, description="Account type name"
    )

    @field_validator("name", mode="before")
    def validate_name(cls, v: str) -> str:
        if isinstance(v, str):
            return " ".join(v.split())
        return v


class AccountTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            return " ".join(v.split())
        return v


class AccountTypeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AccountTypeWithRulesResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    interest_rules: list[dict]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
