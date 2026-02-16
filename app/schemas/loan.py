from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoanCreate(BaseModel):
    account_id: uuid.UUID = Field(..., description="Account to receive loan amount")
    loan_type_id: uuid.UUID = Field(..., description="Type of loan (e.g., Personal, Home, Education)")
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
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    loan_type_id: uuid.UUID
    principal_amount: Decimal
    interest_rate: Decimal
    tenure_months: int
    remaining_principal: Decimal
    emi_amount: Decimal
    loan_purpose: str
    status: str
    decided_by: Optional[uuid.UUID] = None
    rejection_reason: Optional[str] = None
    applied_at: datetime
    decided_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("principal_amount", "remaining_principal", "emi_amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v


class LoanUserResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    loan_type_id: uuid.UUID
    principal_amount: Decimal
    interest_rate: Decimal
    tenure_months: int
    remaining_principal: Decimal
    emi_amount: Decimal
    loan_purpose: str
    status: str
    rejection_reason: Optional[str] = None
    applied_at: datetime
    decided_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("principal_amount", "remaining_principal", "emi_amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v


class AdvanceLoanRepaymentRequest(BaseModel):
    payment_amount: Decimal = Field(
        ..., 
        gt=0, 
        decimal_places=2, 
        description="Payment amount in rupees"
    )
    
    @field_validator("payment_amount")
    def validate_payment_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Payment amount must be greater than zero")
        if v > Decimal("100000000.00"):  # 10 crore max
            raise ValueError("Payment amount cannot exceed ₹10,00,00,000")
        return v


class AdvanceLoanRepaymentResponse(BaseModel):
    success: bool
    message: str
    payment_amount: Optional[Decimal] = None
    interest_component: Optional[Decimal] = None
    principal_component: Optional[Decimal] = None
    old_remaining_principal: Optional[Decimal] = None
    new_remaining_principal: Optional[Decimal] = None
    old_tenure: Optional[int] = None
    new_tenure: Optional[int] = None
    is_foreclosure: Optional[bool] = None
    loan_status: Optional[str] = None
    transaction_id: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)