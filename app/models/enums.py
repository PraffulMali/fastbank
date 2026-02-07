from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN" 
    ADMIN = "ADMIN"             
    STAFF = "STAFF"              
    USER = "USER"


class AccountType(str, Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"
