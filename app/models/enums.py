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


class NotificationType(str, Enum):
    TRANSACTION_SUCCESS = "TRANSACTION_SUCCESS"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    LOAN_APPLIED = "LOAN_APPLIED"
    LOAN_APPROVED = "LOAN_APPROVED"
    LOAN_REJECTED = "LOAN_REJECTED"
    LOAN_DISBURSED = "LOAN_DISBURSED"
    HIGH_VALUE_TRANSACTION = "HIGH_VALUE_TRANSACTION"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    
class LoanStatus(str, Enum):
    APPLIED = "APPLIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"