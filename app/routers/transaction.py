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
    try:
        debit_txn, credit_txn, reference_id = await TransactionService.initiate_transfer(
            db, transfer_request, current_user
        )
        
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

    
    try:
        await TransactionService.verify_transaction_access(db, transaction_id, current_user)
        
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