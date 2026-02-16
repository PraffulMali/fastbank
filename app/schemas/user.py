from typing import Optional
import uuid
from datetime import datetime, date
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
import re


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    
    @field_validator("full_name")
    def validate_full_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not re.match(r"^[A-Za-z\s]+$", v):
            raise ValueError("Full name must contain only alphabets and spaces")
        return v


class UserCreateBySuperAdmin(UserBase):
    tenant_id: uuid.UUID
    role: str = Field(default="ADMIN")
    
    @field_validator("role")
    def validate_role(cls, v: str) -> str:
        if v != "ADMIN":
            raise ValueError("SUPER_ADMIN can only create ADMIN users")
        return v


class UserCreateByAdmin(UserBase):
    phone_number: str = Field(..., min_length=10, max_length=20)
    date_of_birth: date
    pan_number: str = Field(..., min_length=10, max_length=10)
    address_line1: str = Field(..., min_length=5, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=4, max_length=20)
    country: str = Field(default="India", max_length=100)
    account_type_id: uuid.UUID = Field(..., description="ID of the account type")
    
    @field_validator("pan_number")
    def validate_pan(cls, v: str) -> str:
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", v):
            raise ValueError("Invalid PAN number format")
        return v
    
    @field_validator("phone_number")
    def validate_phone(cls, v: str) -> str:
        v = re.sub(r'\D', '', v) 
        if len(v) < 10:
            raise ValueError("Phone number must be at least 10 digits")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    
    @field_validator("new_password")
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if not any(char.islower() for char in v):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in v):
            raise ValueError("Password must contain at least one special character")
        
        return v
    
    @field_validator("confirm_password")
    def passwords_match(cls, v: str, info) -> str:
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError("Passwords do not match")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None
    
    @field_validator("full_name")
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if not re.match(r"^[A-Za-z\s]+$", v):
            raise ValueError("Full name must contain only alphabets and spaces")
        return v


class UserIdentityResponse(BaseModel):
    phone_number: str
    date_of_birth: date
    pan_number: str
    address_line1: str
    address_line2: Optional[str]
    city: str
    state: str
    postal_code: str
    country: str
    verified_by: Optional[uuid.UUID]
    verified_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: Optional[uuid.UUID]
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: Optional[uuid.UUID]
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    user_identity: Optional[UserIdentityResponse] = None
    
    model_config = ConfigDict(from_attributes=True)


class UserSelfResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: Optional[uuid.UUID]
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime
    user_identity: Optional[UserIdentityResponse] = None
    
    model_config = ConfigDict(from_attributes=True)
