from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InterestRuleCreate(BaseModel):
    rule_type: str = Field(..., description="ACCOUNT or LOAN")

    account_type_id: Optional[uuid.UUID] = None
    min_balance: Optional[Decimal] = Field(
        None, ge=0, description="Minimum balance in rupees"
    )
    max_balance: Optional[Decimal] = Field(
        None, ge=0, description="Maximum balance in rupees (NULL = unlimited)"
    )

    loan_type_id: Optional[uuid.UUID] = None

    interest_rate: Decimal = Field(
        ..., ge=0, le=100, decimal_places=2, description="Interest rate as percentage"
    )

    @field_validator("rule_type")
    def validate_rule_type(cls, v: str) -> str:
        v = v.upper()
        if v not in ["ACCOUNT", "LOAN"]:
            raise ValueError("rule_type must be either ACCOUNT or LOAN")
        return v

    @model_validator(mode="after")
    def validate_rule_constraints(self):
        if self.rule_type == "LOAN":
            if not self.loan_type_id:
                raise ValueError("loan_type_id is required for LOAN rules")

            if self.account_type_id:
                raise ValueError("LOAN rules cannot have account_type_id")
            if self.min_balance is not None:
                raise ValueError("LOAN rules cannot have min_balance")
            if self.max_balance is not None:
                raise ValueError("LOAN rules cannot have max_balance")

        elif self.rule_type == "ACCOUNT":
            if not self.account_type_id:
                raise ValueError("account_type_id is required for ACCOUNT rules")
            if self.min_balance is None:
                raise ValueError("min_balance is required for ACCOUNT rules")

            if self.loan_type_id:
                raise ValueError("ACCOUNT rules cannot have loan_type_id")

            if self.max_balance is not None and self.max_balance <= self.min_balance:
                raise ValueError("max_balance must be greater than min_balance")

        return self


class InterestRuleUpdate(BaseModel):
    interest_rate: Optional[Decimal] = Field(
        None, ge=0, le=100, decimal_places=2, description="Interest rate as percentage"
    )
    min_balance: Optional[Decimal] = Field(
        None, ge=0, description="Minimum balance in rupees"
    )
    max_balance: Optional[Decimal] = Field(
        None, ge=0, description="Maximum balance in rupees (NULL = unlimited)"
    )

    @model_validator(mode="after")
    def validate_update_constraints(self):
        if self.min_balance is not None and self.max_balance is not None:
            if self.max_balance <= self.min_balance:
                raise ValueError("max_balance must be greater than min_balance")
        return self


class TypeNameResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class InterestRuleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    rule_type: str
    account_type: Optional[TypeNameResponse] = None
    loan_type: Optional[TypeNameResponse] = None
    min_balance: Optional[Decimal] = None
    max_balance: Optional[Decimal] = None
    interest_rate: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("min_balance", "max_balance", mode="before")
    def convert_paise_to_rupees(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, Decimal)):
            return (Decimal(v) / 100).quantize(Decimal("0.01"))
        return v
