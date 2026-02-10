from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN" 
    ADMIN = "ADMIN"             
    STAFF = "STAFF"              
    USER = "USER"


class AccountType(str, Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"


class TransactionType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ReferenceType(str, Enum):
    TRANSFER = "TRANSFER"  
    LOAN = "LOAN"          
    SYSTEM = "SYSTEM"     