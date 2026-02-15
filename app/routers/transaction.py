from typing import Annotated, Union
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.transaction import (
    TransferRequest,
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
        
        # TODO: Trigger background task here to process the transfer
        # The background task will:
        # 1. Update transaction statuses to SUCCESS
        # 2. Update account balances
        # 3. Send WebSocket notification to both users
        
        return TransferResponse(
            reference_id=reference_id,
            debit_transaction=TransactionResponse(
                id=debit_txn.id,
                account_id=debit_txn.account_id,
                account_number=debit_txn.account.account_number,
                transaction_type=debit_txn.transaction_type.value,
                reference_type=debit_txn.reference_type.value,
                amount=debit_txn.amount,
                status=debit_txn.status.value,
                created_at=debit_txn.created_at,
                updated_at=debit_txn.updated_at
            ),
            credit_transaction=TransactionResponse(
                id=credit_txn.id,
                account_id=credit_txn.account_id,
                account_number=credit_txn.account.account_number,
                transaction_type=credit_txn.transaction_type.value,
                reference_type=credit_txn.reference_type.value,
                amount=credit_txn.amount,
                status=credit_txn.status.value,
                created_at=credit_txn.created_at,
                updated_at=credit_txn.updated_at
            )
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