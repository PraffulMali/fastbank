from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountTypeCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Account type name")
    
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())  # Remove extra spaces
        if len(v) < 2:
            raise ValueError("Account type name must be at least 2 characters")
        return v


class AccountTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None
    
    @field_validator("name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Account type name must be at least 2 characters")
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
    interest_rules: list[dict]  # Will be populated by service
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)