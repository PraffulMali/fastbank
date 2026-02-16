from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.transaction import (
    TransferRequest,
    DepositRequest,
    TransferResponse,
    TransactionResponse,
    TransactionDetailResponse
)
from app.services.transaction_service import TransactionService
from app.dependencies import get_current_user, require_user, require_tenant_member
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"]
)


@router.post("/transfer", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    transfer_request: TransferRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)]
):
    """
    Initiate a transfer between accounts (USER only).
    
    - USER: Can transfer from their own accounts to any other account
    - Creates both DEBIT and CREDIT transactions with PENDING status
    - Background task will process and update status to SUCCESS/FAILED
    - ADMIN and SUPER_ADMIN cannot use this endpoint
    
    Validations:
    - Source account must belong to current user
    - Source account must have sufficient balance
    - Destination account must exist and be active
    - Cannot transfer to the same account
    """
    try:
        debit_txn, credit_txn, reference_id = await TransactionService.initiate_transfer(
            db, transfer_request, current_user
        )
        
        # We return the data as a dictionary, and FastAPI will use TransferResponse 
        # to validate and serialize it. Since TransactionResponse has from_attributes=True,
        # it will correctly handle the ORM objects.
        return TransferResponse(
            reference_id=reference_id,
            debit_transaction=debit_txn,
            credit_transaction=credit_txn
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/deposit", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(
    deposit_request: DepositRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)]
):
    """
    Deposit cash into an account (USER only).
    
    - USER: Can deposit into their own accounts
    - Creates a CREDIT transaction with CASH reference type
    - Status is set to SUCCESS immediately
    - Balance is updated immediately
    """
    try:
        transaction = await TransactionService.deposit(
            db, deposit_request, current_user
        )
        
        return transaction
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get("/", response_model=Page[TransactionResponse])
async def list_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
    paginator: Paginator = Depends()
):
    """
    List transactions based on user role.
    
    - USER: See only their own account transactions (from active accounts)
    - ADMIN: See all transactions in their tenant (including inactive accounts)
    - SUPER_ADMIN: Cannot access this endpoint
    """

    
    try:
        return await TransactionService.list_transactions(db, current_user, paginator)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)]
):
    """
    Get detailed transaction information with counterparty details.
    
    - USER: Can view their own account transactions
    - ADMIN: Can view any transaction in their tenant
    - SUPER_ADMIN: Cannot access this endpoint
    
    For TRANSFER transactions, includes counterparty information:
    - Counterparty tenant_id
    - Counterparty account_number
    - Counterparty user_name
    """

    
    try:
        # Verify access permissions
        await TransactionService.verify_transaction_access(db, transaction_id, current_user)
        
        # Get transaction with counterparty info
        transaction_detail = await TransactionService.get_transaction_detail_with_counterparty(
            db, transaction_id
        )
        
        if not transaction_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        return transaction_detail
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )