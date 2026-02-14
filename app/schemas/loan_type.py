from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoanTypeCreate(BaseModel):
    """Schema for creating loan type (ADMIN only)"""
    name: str = Field(..., min_length=2, max_length=100, description="Loan type name")
    
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())  # Remove extra spaces
        if len(v) < 2:
            raise ValueError("Loan type name must be at least 2 characters")
        return v


class LoanTypeUpdate(BaseModel):
    """Schema for updating loan type"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None
    
    @field_validator("name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Loan type name must be at least 2 characters")
        return v


class LoanTypeResponse(BaseModel):
    """Schema for loan type response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class LoanTypeWithRateResponse(BaseModel):
    """Schema for loan type with its interest rate"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    interest_rate: Optional[float] = None  # From interest_rules
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)