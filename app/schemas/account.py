from typing import Optional, List
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountCreateByAdmin(BaseModel):
    user_id: uuid.UUID

    account_type_id: uuid.UUID


class AccountUpdate(BaseModel):
    is_active: bool = Field(..., description="Set to True to reactivate account")


class AccountResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    account_number: str
    account_type_id: uuid.UUID
    account_type: str
    balance: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("account_type", mode="before")
    def get_account_type_name(cls, v):
        if hasattr(v, "name"):
            return v.name
        return str(v)

    @field_validator("balance", mode="before")
    def convert_balance_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v



class AccountUserSingleResponse(BaseModel):
    id: uuid.UUID
    account_number: str
    account_type_id: uuid.UUID
    account_type: str
    balance: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("account_type", mode="before")
    def get_account_type_name(cls, v):
        if hasattr(v, "name"):
            return v.name
        return str(v)
    
    @field_validator("balance", mode="before")
    def convert_balance_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v



class AccountUserResponse(BaseModel):
    accounts: List[AccountUserSingleResponse]
    
    model_config = ConfigDict(from_attributes=True)