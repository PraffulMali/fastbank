from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransferRequest(BaseModel):
    """
    Schema for initiating a transfer between accounts.
    """
    source_account_number: str = Field(..., min_length=15, max_length=20)
    destination_account_number: str = Field(..., min_length=15, max_length=20)
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    
    @field_validator("amount")
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        if v.as_tuple().exponent < -2:
            raise ValueError("Amount cannot have more than 2 decimal places")
        return v


class DepositRequest(BaseModel):
    """
    Schema for depositing cash into an account.
    """
    account_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    
    @field_validator("amount")
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        if v.as_tuple().exponent < -2:
            raise ValueError("Amount cannot have more than 2 decimal places")
        return v


class TransactionResponse(BaseModel):
    """
    Schema for single transaction response.
    Used in list view.
    """
    id: uuid.UUID
    account_id: uuid.UUID
    account_number: str
    transaction_type: str
    reference_type: str
    amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    
    @field_validator("amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v



class CounterpartyInfo(BaseModel):
    """
    Information about the other party in a transfer.
    """
    tenant_id: uuid.UUID
    account_number: str
    user_name: str
    
    model_config = ConfigDict(from_attributes=True)


class TransactionDetailResponse(BaseModel):
    """
    Schema for detailed transaction response.
    Includes counterparty information.
    """
    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    account_number: str
    reference_id: uuid.UUID
    transaction_type: str
    reference_type: str
    amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    counterparty: Optional[CounterpartyInfo] = None
    
    model_config = ConfigDict(from_attributes=True)
    
    @field_validator("amount", mode="before")
    def convert_paise_to_rupees(cls, v):
        if isinstance(v, int):
            return Decimal(v) / 100
        return v



class TransferResponse(BaseModel):
    """
    Schema for transfer initiation response.
    Returns both debit and credit transaction details.
    """
    reference_id: uuid.UUID
    debit_transaction: TransactionResponse
    credit_transaction: TransactionResponse
    
    model_config = ConfigDict(from_attributes=True)