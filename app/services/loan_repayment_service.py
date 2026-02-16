# """
# Loan Repayment Service
# Handles EMI deductions, repayment tracking, and related operations.
# """
# from typing import Optional, Tuple
# import uuid
# from datetime import datetime, timezone
# from decimal import Decimal
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, and_

# from app.models.loan import Loan
# from app.models.loan_repayment import LoanRepayment
# from app.models.account import Account
# from app.models.transaction import Transaction
# from app.models.user import User
# from app.models.enums import (
#     LoanStatus, 
#     TransactionType, 
#     TransactionStatus, 
#     ReferenceType,
#     NotificationType,
#     UserRole
# )
# from app.services.notification_service import NotificationService
# from app.services.email_service import EmailService
# import logging

# logger = logging.getLogger(__name__)


# class LoanRepaymentService:
    
#     @staticmethod
#     def calculate_emi_split(
#         emi_amount: int,
#         remaining_principal: int,
#         annual_interest_rate: Decimal,
#         tenure_months: int
#     ) -> Tuple[int, int]:
#         """
#         Calculate how much of the EMI goes to interest vs principal.
        
#         Formula:
#         - Interest component = (remaining_principal * annual_rate / 12 / 100)
#         - Principal component = EMI - Interest component
        
#         Args:
#             emi_amount: Total EMI amount in paisa
#             remaining_principal: Remaining principal in paisa
#             annual_interest_rate: Annual interest rate (e.g., 12.00 for 12%)
#             tenure_months: Total tenure in months (not used in calculation but kept for context)
            
#         Returns:
#             Tuple of (principal_component, interest_component) in paisa
#         """
#         # Calculate monthly interest
#         monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
#         interest_component = int(Decimal(remaining_principal) * monthly_rate)
        
#         # Principal is the remainder
#         principal_component = emi_amount - interest_component
        
#         # Ensure principal doesn't exceed remaining principal
#         if principal_component > remaining_principal:
#             principal_component = remaining_principal
#             interest_component = emi_amount - principal_component
        
#         return (principal_component, interest_component)
    
#     @staticmethod
#     async def process_emi_deduction(
#         db: AsyncSession,
#         loan: Loan
#     ) -> Tuple[bool, str]:
#         """
#         Process EMI deduction for a single loan.
        
#         This is an atomic operation:
#         1. Check if account has sufficient balance
#         2. If yes:
#            - Create DEBIT transaction
#            - Reduce account balance
#            - Split EMI into principal and interest
#            - Update loan's remaining_principal
#            - Create loan repayment record
#            - Send success notification
#         3. If no:
#            - Send failure notification
#            - Send failure email
#            - Notify admins
        
#         Args:
#             db: Database session
#             loan: Loan object to process
            
#         Returns:
#             Tuple of (success: bool, message: str)
#         """
#         try:
#             # Get account
#             account = await db.get(Account, loan.account_id)
#             if not account:
#                 return (False, f"Account not found for loan {loan.id}")
            
#             # Get user for notifications
#             user = await db.get(User, loan.user_id)
#             if not user:
#                 return (False, f"User not found for loan {loan.id}")
            
#             # Check if sufficient balance
#             if account.balance < loan.emi_amount:
#                 # Insufficient funds - send notifications and email
#                 shortfall = loan.emi_amount - account.balance
                
#                 # Send notification to user
#                 await NotificationService.create_notification(
#                     db=db,
#                     tenant_id=loan.tenant_id,
#                     user_id=loan.user_id,
#                     notification_type=NotificationType.SYSTEM_ALERT,
#                     message=f"EMI payment of ₹{loan.emi_amount / 100:,.2f} failed due to insufficient funds. Current balance: ₹{account.balance / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
#                     reference_id=loan.id,
#                     reference_type="loan",
#                     send_websocket=True
#                 )
                
#                 # Send email to user
#                 await EmailService.send_emi_failure_email(
#                     to_email=user.email,
#                     user_name=user.full_name,
#                     loan_amount=loan.principal_amount / 100,
#                     emi_amount=loan.emi_amount / 100,
#                     account_balance=account.balance / 100,
#                     due_date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
#                 )
                
#                 # Notify all admins
#                 admin_query = select(User).where(
#                     and_(
#                         User.tenant_id == loan.tenant_id,
#                         User.role == UserRole.ADMIN,
#                         User.is_active == True
#                     )
#                 )
#                 admin_result = await db.execute(admin_query)
#                 admins = list(admin_result.scalars().all())
                
#                 for admin in admins:
#                     await NotificationService.create_notification(
#                         db=db,
#                         tenant_id=loan.tenant_id,
#                         user_id=admin.id,
#                         notification_type=NotificationType.SYSTEM_ALERT,
#                         message=f"EMI payment failed for {user.full_name} - Loan ID: {loan.id}. Amount: ₹{loan.emi_amount / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
#                         reference_id=loan.id,
#                         reference_type="loan",
#                         send_websocket=True
#                     )
                
#                 logger.warning(
#                     f"Insufficient funds for EMI deduction. "
#                     f"Loan: {loan.id}, User: {user.email}, "
#                     f"Required: {loan.emi_amount / 100}, Available: {account.balance / 100}"
#                 )
                
#                 return (False, f"Insufficient funds. Required: ₹{loan.emi_amount / 100:,.2f}, Available: ₹{account.balance / 100:,.2f}")
            
#             # Sufficient funds - proceed with deduction
#             # Calculate EMI split
#             principal_component, interest_component = LoanRepaymentService.calculate_emi_split(
#                 emi_amount=loan.emi_amount,
#                 remaining_principal=loan.remaining_principal,
#                 annual_interest_rate=loan.interest_rate,
#                 tenure_months=loan.tenure_months
#             )
            
#             # Create DEBIT transaction
#             emi_transaction = Transaction(
#                 tenant_id=loan.tenant_id,
#                 account_id=loan.account_id,
#                 reference_id=loan.id,
#                 transaction_type=TransactionType.DEBIT,
#                 reference_type=ReferenceType.LOAN,
#                 amount=loan.emi_amount,
#                 status=TransactionStatus.SUCCESS
#             )
            
#             db.add(emi_transaction)
            
#             # Reduce account balance
#             account.balance -= loan.emi_amount
            
#             # Update loan's remaining principal
#             loan.remaining_principal -= principal_component
            
#             # Ensure remaining principal doesn't go negative
#             if loan.remaining_principal < 0:
#                 loan.remaining_principal = 0
            
#             # Flush to get transaction ID
#             await db.flush()
            
#             # Create loan repayment record
#             repayment = LoanRepayment(
#                 tenant_id=loan.tenant_id,
#                 loan_id=loan.id,
#                 transaction_id=emi_transaction.id,
#                 amount_paid=loan.emi_amount,
#                 principal_component=principal_component,
#                 interest_component=interest_component,
#                 payment_date=datetime.now(timezone.utc),
#                 status=TransactionStatus.SUCCESS
#             )
            
#             db.add(repayment)
            
#             # Commit all changes atomically
#             await db.commit()
#             await db.refresh(loan)
#             await db.refresh(account)
            
#             # Send success notification to user
#             await NotificationService.create_notification(
#                 db=db,
#                 tenant_id=loan.tenant_id,
#                 user_id=loan.user_id,
#                 notification_type=NotificationType.TRANSACTION_SUCCESS,
#                 message=f"EMI payment of ₹{loan.emi_amount / 100:,.2f} deducted successfully. Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}. Remaining principal: ₹{loan.remaining_principal / 100:,.2f}",
#                 reference_id=emi_transaction.id,
#                 reference_type="transaction",
#                 send_websocket=True
#             )
            
#             logger.info(
#                 f"EMI deducted successfully. "
#                 f"Loan: {loan.id}, User: {user.email}, "
#                 f"Amount: {loan.emi_amount / 100}, "
#                 f"Principal: {principal_component / 100}, "
#                 f"Interest: {interest_component / 100}, "
#                 f"Remaining: {loan.remaining_principal / 100}"
#             )
            
#             return (True, f"EMI of ₹{loan.emi_amount / 100:,.2f} deducted successfully")
            
#         except Exception as e:
#             logger.error(f"Error processing EMI for loan {loan.id}: {str(e)}")
#             await db.rollback()
#             return (False, f"Error: {str(e)}")
    
#     @staticmethod
#     async def process_monthly_emis(db: AsyncSession) -> dict:
#         """
#         Process EMI deductions for all active approved loans.
#         This is called by the Celery task on the 1st of every month.
        
#         Returns:
#             Dictionary with statistics about the processing
#         """
#         # Get all active approved loans
#         query = select(Loan).where(
#             and_(
#                 Loan.status == LoanStatus.APPROVED,
#                 Loan.is_active == True,
#                 Loan.remaining_principal > 0
#             )
#         )
        
#         result = await db.execute(query)
#         loans = list(result.scalars().all())
        
#         stats = {
#             "total_loans": len(loans),
#             "successful": 0,
#             "failed": 0,
#             "total_amount_collected": 0,
#             "errors": []
#         }
        
#         logger.info(f"Processing monthly EMIs for {len(loans)} loans")
        
#         for loan in loans:
#             success, message = await LoanRepaymentService.process_emi_deduction(db, loan)
            
#             if success:
#                 stats["successful"] += 1
#                 stats["total_amount_collected"] += loan.emi_amount
#             else:
#                 stats["failed"] += 1
#                 stats["errors"].append({
#                     "loan_id": str(loan.id),
#                     "message": message
#                 })
        
#         logger.info(
#             f"Monthly EMI processing complete. "
#             f"Total: {stats['total_loans']}, "
#             f"Successful: {stats['successful']}, "
#             f"Failed: {stats['failed']}, "
#             f"Amount Collected: ₹{stats['total_amount_collected'] / 100:,.2f}"
#         )
        
#         return stats

"""
Loan Repayment Service
Handles EMI deductions, repayment tracking, and related operations.
"""
from typing import Optional, Tuple
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.loan import Loan
from app.models.loan_repayment import LoanRepayment
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.models.enums import (
    LoanStatus, 
    TransactionType, 
    TransactionStatus, 
    ReferenceType,
    NotificationType,
    UserRole
)
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)


class LoanRepaymentService:
    
    @staticmethod
    def calculate_emi_split(
        emi_amount: int,
        remaining_principal: int,
        annual_interest_rate: Decimal,
        tenure_months: int
    ) -> Tuple[int, int]:
        """
        Calculate how much of the EMI goes to interest vs principal.
        
        Formula:
        - Interest component = (remaining_principal * annual_rate / 12 / 100)
        - Principal component = EMI - Interest component
        
        Args:
            emi_amount: Total EMI amount in paisa
            remaining_principal: Remaining principal in paisa
            annual_interest_rate: Annual interest rate (e.g., 12.00 for 12%)
            tenure_months: Total tenure in months (not used in calculation but kept for context)
            
        Returns:
            Tuple of (principal_component, interest_component) in paisa
        """
        # Calculate monthly interest
        monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
        interest_component = int(Decimal(remaining_principal) * monthly_rate)
        
        # Principal is the remainder
        principal_component = emi_amount - interest_component
        
        # Ensure principal doesn't exceed remaining principal
        if principal_component > remaining_principal:
            principal_component = remaining_principal
            interest_component = emi_amount - principal_component
        
        return (principal_component, interest_component)
    
    @staticmethod
    async def process_emi_deduction(
        db: AsyncSession,
        loan: Loan
    ) -> Tuple[bool, str]:
        """
        Process EMI deduction for a single loan.
        
        IMPORTANT: This method does NOT manage transactions. The caller must ensure
        this method is called within a transaction context (e.g., within db.begin() 
        or db.begin_nested()).
        
        For batch processing, use process_monthly_emis() which handles transactions properly.
        
        Steps:
        1. Check if account has sufficient balance
        2. If yes:
           - Create DEBIT transaction
           - Reduce account balance
           - Split EMI into principal and interest
           - Update loan's remaining_principal
           - Create loan repayment record
        3. If no:
           - Return failure (caller handles notifications)
        
        Args:
            db: Database session (caller must manage transaction)
            loan: Loan object to process
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Get account
        account = await db.get(Account, loan.account_id)
        if not account:
            return (False, f"Account not found for loan {loan.id}")
        
        # Get user for reference
        user = await db.get(User, loan.user_id)
        if not user:
            return (False, f"User not found for loan {loan.id}")
        
        # Check if sufficient balance
        if account.balance < loan.emi_amount:
            shortfall = loan.emi_amount - account.balance
            logger.warning(
                f"Insufficient funds for EMI deduction. "
                f"Loan: {loan.id}, User: {user.email}, "
                f"Required: {loan.emi_amount / 100}, Available: {account.balance / 100}"
            )
            return (False, f"Insufficient funds. Required: ₹{loan.emi_amount / 100:,.2f}, Available: ₹{account.balance / 100:,.2f}")
        
        # Calculate EMI split
        principal_component, interest_component = LoanRepaymentService.calculate_emi_split(
            emi_amount=loan.emi_amount,
            remaining_principal=loan.remaining_principal,
            annual_interest_rate=loan.interest_rate,
            tenure_months=loan.tenure_months
        )
        
        # Create DEBIT transaction
        emi_transaction = Transaction(
            tenant_id=loan.tenant_id,
            account_id=loan.account_id,
            reference_id=loan.id,
            transaction_type=TransactionType.DEBIT,
            reference_type=ReferenceType.LOAN,
            amount=loan.emi_amount,
            status=TransactionStatus.SUCCESS
        )
        
        db.add(emi_transaction)
        
        # Reduce account balance
        account.balance -= loan.emi_amount
        
        # Update loan's remaining principal
        loan.remaining_principal -= principal_component
        
        # Ensure remaining principal doesn't go negative
        if loan.remaining_principal < 0:
            loan.remaining_principal = 0
        
        # Flush to get transaction ID
        await db.flush()
        
        # Create loan repayment record
        repayment = LoanRepayment(
            tenant_id=loan.tenant_id,
            loan_id=loan.id,
            transaction_id=emi_transaction.id,
            amount_paid=loan.emi_amount,
            principal_component=principal_component,
            interest_component=interest_component,
            payment_date=datetime.now(timezone.utc),
            status=TransactionStatus.SUCCESS
        )
        
        db.add(repayment)
        await db.flush()
        
        logger.info(
            f"EMI deducted successfully. "
            f"Loan: {loan.id}, User: {user.email}, "
            f"Amount: {loan.emi_amount / 100}, "
            f"Principal: {principal_component / 100}, "
            f"Interest: {interest_component / 100}, "
            f"Remaining: {loan.remaining_principal / 100}"
        )
        
        return (True, f"EMI of ₹{loan.emi_amount / 100:,.2f} deducted successfully")
    
    @staticmethod
    async def process_monthly_emis(db: AsyncSession) -> dict:
        """
        Process EMI deductions for all active approved loans.
        This is called by the Celery task on the 1st of every month.
        
        Each loan is processed in its own savepoint transaction to ensure
        atomicity per loan while allowing other loans to succeed if one fails.
        
        Returns:
            Dictionary with statistics about the processing
        """
        # Get all active approved loans
        query = select(Loan).where(
            and_(
                Loan.status == LoanStatus.APPROVED,
                Loan.is_active == True,
                Loan.remaining_principal > 0
            )
        )
        
        result = await db.execute(query)
        loans = list(result.scalars().all())
        
        stats = {
            "total_loans": len(loans),
            "successful": 0,
            "failed": 0,
            "total_amount_collected": 0,
            "errors": []
        }
        
        logger.info(f"Processing monthly EMIs for {len(loans)} loans")
        
        for loan in loans:
            try:
                # Get account and user for this loan
                account = await db.get(Account, loan.account_id)
                if not account:
                    raise Exception(f"Account not found for loan {loan.id}")
                
                user = await db.get(User, loan.user_id)
                if not user:
                    raise Exception(f"User not found for loan {loan.id}")
                
                # Check if sufficient balance
                if account.balance < loan.emi_amount:
                    # Insufficient funds - handle failure notifications
                    shortfall = loan.emi_amount - account.balance
                    
                    # Send notification to user
                    await NotificationService.create_notification(
                        db=db,
                        tenant_id=loan.tenant_id,
                        user_id=loan.user_id,
                        notification_type=NotificationType.SYSTEM_ALERT,
                        message=f"EMI payment of ₹{loan.emi_amount / 100:,.2f} failed due to insufficient funds. Current balance: ₹{account.balance / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                        reference_id=loan.id,
                        reference_type="loan",
                        send_websocket=True
                    )
                    
                    # Send email to user
                    await EmailService.send_emi_failure_email(
                        to_email=user.email,
                        user_name=user.full_name,
                        loan_amount=loan.principal_amount / 100,
                        emi_amount=loan.emi_amount / 100,
                        account_balance=account.balance / 100,
                        due_date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    )
                    
                    # Notify all admins
                    admin_query = select(User).where(
                        and_(
                            User.tenant_id == loan.tenant_id,
                            User.role == UserRole.ADMIN,
                            User.is_active == True
                        )
                    )
                    admin_result = await db.execute(admin_query)
                    admins = list(admin_result.scalars().all())
                    
                    for admin in admins:
                        await NotificationService.create_notification(
                            db=db,
                            tenant_id=loan.tenant_id,
                            user_id=admin.id,
                            notification_type=NotificationType.SYSTEM_ALERT,
                            message=f"EMI payment failed for {user.full_name} - Loan ID: {loan.id}. Amount: ₹{loan.emi_amount / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                            reference_id=loan.id,
                            reference_type="loan",
                            send_websocket=True
                        )
                    
                    logger.warning(
                        f"Insufficient funds for EMI deduction. "
                        f"Loan: {loan.id}, User: {user.email}, "
                        f"Required: {loan.emi_amount / 100}, Available: {account.balance / 100}"
                    )
                    
                    raise Exception(f"Insufficient funds. Required: ₹{loan.emi_amount / 100:,.2f}, Available: ₹{account.balance / 100:,.2f}")
                
                # Calculate EMI split
                principal_component, interest_component = LoanRepaymentService.calculate_emi_split(
                    emi_amount=loan.emi_amount,
                    remaining_principal=loan.remaining_principal,
                    annual_interest_rate=loan.interest_rate,
                    tenure_months=loan.tenure_months
                )
                
                # Variables to capture for post-transaction notifications
                transaction_id = None
                emi_amount = loan.emi_amount
                remaining_principal_after = None
                
                # ATOMIC TRANSACTION BLOCK - Process each loan in its own savepoint
                async with db.begin_nested():
                    # Create DEBIT transaction
                    emi_transaction = Transaction(
                        tenant_id=loan.tenant_id,
                        account_id=loan.account_id,
                        reference_id=loan.id,
                        transaction_type=TransactionType.DEBIT,
                        reference_type=ReferenceType.LOAN,
                        amount=loan.emi_amount,
                        status=TransactionStatus.SUCCESS
                    )
                    
                    db.add(emi_transaction)
                    
                    # Reduce account balance
                    account.balance -= loan.emi_amount
                    
                    # Update loan's remaining principal
                    loan.remaining_principal -= principal_component
                    
                    # Ensure remaining principal doesn't go negative
                    if loan.remaining_principal < 0:
                        loan.remaining_principal = 0
                    
                    # Flush to get transaction ID
                    await db.flush()
                    
                    # Capture values for notifications
                    transaction_id = emi_transaction.id
                    remaining_principal_after = loan.remaining_principal
                    
                    # Create loan repayment record
                    repayment = LoanRepayment(
                        tenant_id=loan.tenant_id,
                        loan_id=loan.id,
                        transaction_id=emi_transaction.id,
                        amount_paid=loan.emi_amount,
                        principal_component=principal_component,
                        interest_component=interest_component,
                        payment_date=datetime.now(timezone.utc),
                        status=TransactionStatus.SUCCESS
                    )
                    
                    db.add(repayment)
                    await db.flush()
                    
                    # Savepoint transaction commits here automatically
                
                # Refresh objects after savepoint commit
                await db.refresh(loan)
                await db.refresh(account)
                
                # Send success notification AFTER transaction commits
                await NotificationService.create_notification(
                    db=db,
                    tenant_id=loan.tenant_id,
                    user_id=loan.user_id,
                    notification_type=NotificationType.TRANSACTION_SUCCESS,
                    message=f"EMI payment of ₹{emi_amount / 100:,.2f} deducted successfully. Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}. Remaining principal: ₹{remaining_principal_after / 100:,.2f}",
                    reference_id=transaction_id,
                    reference_type="transaction",
                    send_websocket=True
                )
                
                logger.info(
                    f"EMI deducted successfully. "
                    f"Loan: {loan.id}, User: {user.email}, "
                    f"Amount: {emi_amount / 100}, "
                    f"Principal: {principal_component / 100}, "
                    f"Interest: {interest_component / 100}, "
                    f"Remaining: {remaining_principal_after / 100}"
                )
                
                # Success - update stats
                stats["successful"] += 1
                stats["total_amount_collected"] += emi_amount
                    
            except Exception as e:
                # This loan failed - log it and continue with others
                stats["failed"] += 1
                stats["errors"].append({
                    "loan_id": str(loan.id),
                    "message": str(e)
                })
                logger.error(f"Failed to process EMI for loan {loan.id}: {str(e)}")
        
        logger.info(
            f"Monthly EMI processing complete. "
            f"Total: {stats['total_loans']}, "
            f"Successful: {stats['successful']}, "
            f"Failed: {stats['failed']}, "
            f"Amount Collected: ₹{stats['total_amount_collected'] / 100:,.2f}"
        )
        
        return stats