import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func

from app.celery.app import celery_app
from app.models.user import User
from app.database.session import AsyncSessionLocal
from app.services.loan_repayment_service import LoanRepaymentService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.celery.tasks.process_monthly_emi_deductions")
def process_monthly_emi_deductions():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info(
            f"[EMI Task] Starting monthly EMI deduction process at {datetime.now(timezone.utc)}"
        )
        stats = loop.run_until_complete(_process_monthly_emi_deductions_task())
        logger.info(f"[EMI Task] Completed. Stats: {stats}")
        return stats
    except Exception as e:
        logger.error(f"[EMI Task] Failed with error: {str(e)}")
        raise
    finally:
        loop.close()


async def _process_monthly_emi_deductions_task():
    async with AsyncSessionLocal() as db:
        try:
            stats = await LoanRepaymentService.process_monthly_emis(db)

            await db.commit()

            return stats
        except Exception as e:
            await db.rollback()
            logger.error(f"Error in EMI deduction task: {str(e)}")
            raise


from app.services.interest_rule_service import InterestRuleService


@celery_app.task(name="app.celery.tasks.process_monthly_interest_accrual")
def process_monthly_interest_accrual():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        logger.info(
            f"[Interest Task] Starting monthly interest accrual at {datetime.now(timezone.utc)}"
        )
        stats = loop.run_until_complete(_process_monthly_interest_accrual_task())
        logger.info(f"[Interest Task] Completed. Stats: {stats}")
        return stats
    except Exception as e:
        logger.error(f"[Interest Task] Failed with error: {str(e)}")
        raise
    finally:
        loop.close()


async def _process_monthly_interest_accrual_task():
    async with AsyncSessionLocal() as db:
        try:
            stats = await InterestRuleService.process_monthly_interest_accrual(db)
            await db.commit()
            return stats
        except Exception as e:
            await db.rollback()
            logger.error(f"Error in interest accrual task: {str(e)}")
            raise
