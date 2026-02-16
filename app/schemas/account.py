from typing import Optional, List
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountCreateByAdmin(BaseModel):
    """
    Schema for ADMIN creating an account for a user.
    Requires user_id and account_type.
    """
    user_id: uuid.UUID

    account_type_id: uuid.UUID


class AccountUpdate(BaseModel):
    """
    Schema for updating account - only is_active can be updated (to reactivate).
    """
    is_active: bool = Field(..., description="Set to True to reactivate account")


class AccountResponse(BaseModel):
    """
    Schema for account response (ADMIN view).
    Includes is_active and deleted_at.
    """
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
    """
    Schema for single account in user view.
    Does NOT include is_active and deleted_at.
    """
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
    """
    Schema for /accounts/me endpoint (USER view).
    Returns list of accounts without is_active and deleted_at.
    """
    accounts: List[AccountUserSingleResponse]
    
    model_config = ConfigDict(from_attributes=True)