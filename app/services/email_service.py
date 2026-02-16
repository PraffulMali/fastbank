import logging
from typing import Optional
import aiosmtplib
from email.message import EmailMessage

from app.config.settings import settings
from app.database.redis import get_redis
from app.utils.security import hash_token
from app.templates.email_templates import EmailTemplates

logger = logging.getLogger(__name__)


class EmailService:

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:

        try:
            message = EmailMessage()
            message["From"] = settings.SMTP_FROM
            message["To"] = to_email
            message["Subject"] = subject

            message.set_content(body)

            if html_body:
                message.add_alternative(html_body, subtype="html")

            # ✅ PRODUCTION SMTP
            if settings.SMTP_USER and settings.SMTP_PASSWORD:

                await aiosmtplib.send(
                    message,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USER,
                    password=settings.SMTP_PASSWORD,
                    use_tls=True if settings.SMTP_PORT == 465 else False,
                    start_tls=True if settings.SMTP_PORT == 587 else False,
                )

                logger.info(f"Email successfully sent to {to_email}")

            else:
                # ✅ DEVELOPMENT FALLBACK
                logger.info("SMTP not configured — logging email instead")
                logger.info(f"[EMAIL] To: {to_email}")
                logger.info(f"[EMAIL] Subject: {subject}")
                logger.info(f"[EMAIL] Body: {body}")

            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    @staticmethod
    async def send_verification_email(email: str, token: str, temp_password: str, user_id: str):
        # 1. Store hashed token in Redis with 15 minutes TTL
        hashed_token = hash_token(token)
        redis = await get_redis()
        await redis.setex(f"verify_token:{hashed_token}", 900, str(user_id))
        
        # 2. Get content
        verify_link = f"{settings.FRONTEND_URL}/verify?token={token}"
        subject, content = EmailTemplates.get_verification_email("", verify_link, temp_password) # username unknown here, kept generic
        
        # 3. Send email
        await EmailService.send_email(email, subject, content)
        logger.info(f"Verification email task completed for {email}")

    @staticmethod
    async def send_password_reset_email(email: str, token: str, user_id: str):
        # 1. Store hashed token in Redis with 15 minutes TTL
        hashed_token = hash_token(token)
        redis = await get_redis()
        await redis.setex(f"reset_token:{hashed_token}", 900, str(user_id))
        
        # 2. Get content
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        subject, content = EmailTemplates.get_password_reset_email(reset_link)
        
        # 3. Send email
        await EmailService.send_email(email, subject, content)
        logger.info(f"Password reset email sent to {email}")

    @staticmethod
    async def send_verification_resend_email(email: str, token: str, user_id: str):
        # 1. Store hashed token in Redis with 15 minutes TTL
        hashed_token = hash_token(token)
        redis = await get_redis()
        await redis.setex(f"verify_token:{hashed_token}", 900, str(user_id))
        
        # 2. Get content
        verify_link = f"{settings.FRONTEND_URL}/verify?token={token}"
        subject, content = EmailTemplates.get_verification_resend_email(verify_link)
        
        # 3. Send email
        await EmailService.send_email(email, subject, content)
        logger.info(f"Verification resend email sent to {email}")

    @staticmethod
    async def send_emi_failure_email(
        to_email: str,
        user_name: str,
        loan_amount: float,
        emi_amount: float,
        account_balance: float,
        due_date: str
    ) -> bool:
        subject, body = EmailTemplates.get_emi_failure_email(
            user_name, loan_amount, emi_amount, account_balance, due_date
        )
        return await EmailService.send_email(to_email, subject, body)

    @staticmethod
    async def send_advance_repayment_failure_email(
        to_email: str,
        user_name: str,
        payment_amount: float,
        account_balance: float
    ) -> bool:
        subject, body = EmailTemplates.get_advance_repayment_failure_email(
            user_name, payment_amount, account_balance
        )
        return await EmailService.send_email(to_email, subject, body)
