from typing import Optional, Literal
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoanCreate(BaseModel):
    account_id: uuid.UUID = Field(..., description="Account to receive loan amount")
    loan_type_id: uuid.UUID = Field(
        ..., description="Type of loan (e.g., Personal, Home, Education)"
    )
    principal_amount: Decimal = Field(
        ..., gt=0, decimal_places=2, description="Loan amount requested"
    )
    tenure_months: int = Field(..., gt=0, le=360, description="Loan tenure in months")
    loan_purpose: str = Field(
        ..., min_length=10, max_length=500, description="Purpose of loan"
    )


    @field_validator("loan_purpose", mode="before")
    def validate_purpose(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class LoanApprovalDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"] = Field(
        ..., description="APPROVED or REJECTED"
    )
    rejection_reason: Optional[str] = Field(None, max_length=500)

    @field_validator("decision", mode="before")
    def validate_decision(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.upper()
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

    @field_validator(
        "principal_amount", "remaining_principal", "emi_amount", mode="before"
    )
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

    @field_validator(
        "principal_amount", "remaining_principal", "emi_amount", mode="before"
    )
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v


class LoanRepaymentResponse(BaseModel):
    id: uuid.UUID
    loan_id: uuid.UUID
    transaction_id: uuid.UUID
    amount_paid: Decimal
    principal_component: Decimal
    interest_component: Decimal
    payment_date: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "amount_paid", "principal_component", "interest_component", mode="before"
    )
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v


class AdvanceLoanRepaymentRequest(BaseModel):
    payment_amount: Decimal = Field(
        ..., gt=0, decimal_places=2, description="Payment amount in rupees"
    )


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
