# app/schemas/loan.py

from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoanCreate(BaseModel):
    """
    Schema for USER creating a loan application.
    Interest rate is set by system, not by user.
    """
    account_id: uuid.UUID = Field(..., description="Account to receive loan amount")
    principal_amount: Decimal = Field(..., gt=0, decimal_places=2, description="Loan amount requested")
    tenure_months: int = Field(..., gt=0, le=360, description="Loan tenure in months")
    loan_purpose: str = Field(..., min_length=10, max_length=500, description="Purpose of loan")
    
    @field_validator("principal_amount")
    def validate_principal(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Principal amount must be greater than 0")
        if v > Decimal("10000000.00"):  # 1 crore max
            raise ValueError("Principal amount cannot exceed ₹1,00,00,000")
        return v
    
    @field_validator("loan_purpose")
    def validate_purpose(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Loan purpose must be at least 10 characters")
        return v


class LoanApprovalDecision(BaseModel):
    """
    Schema for ADMIN approving/rejecting loan.
    """
    decision: str = Field(..., description="APPROVED or REJECTED")
    rejection_reason: Optional[str] = Field(None, max_length=500)
    
    @field_validator("decision")
    def validate_decision(cls, v: str) -> str:
        v = v.upper()
        if v not in ["APPROVED", "REJECTED"]:
            raise ValueError("Decision must be either APPROVED or REJECTED")
        return v
    
    @field_validator("rejection_reason")
    def validate_rejection_reason(cls, v: Optional[str], info) -> Optional[str]:
        if info.data.get("decision") == "REJECTED" and not v:
            raise ValueError("Rejection reason is required when rejecting a loan")
        return v


class LoanResponse(BaseModel):
    """
    Schema for loan response (ADMIN view).
    Full details including admin fields and loan purpose.
    """
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    principal_amount: Decimal
    interest_rate: Decimal
    tenure_months: int
    loan_purpose: str
    status: str
    approved_by: Optional[uuid.UUID] = None
    applied_at: datetime
    decided_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("principal_amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v


class LoanUserResponse(BaseModel):
    """
    Schema for loan response (USER view).
    Limited fields - no admin metadata.
    """
    id: uuid.UUID
    account_id: uuid.UUID
    principal_amount: Decimal
    interest_rate: Decimal
    tenure_months: int
    loan_purpose: str
    status: str
    applied_at: datetime
    decided_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("principal_amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v