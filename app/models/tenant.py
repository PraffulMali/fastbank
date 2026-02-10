from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.user_identity import UserIdentity
    from app.models.account import Account
    from app.models.transaction import Transaction  

class Tenant(BaseModel):
    __tablename__ = "tenants"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    user_identities: Mapped[list["UserIdentity"]] = relationship(
        "UserIdentity",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id})>"