# """
# Email Service for sending emails to users.
# This is a basic implementation. In production, you should use a proper email service
# like SendGrid, AWS SES, or similar.
# """
# import logging
# from typing import Optional

# logger = logging.getLogger(__name__)


# class EmailService:
#     """
#     Service for sending emails.
#     Currently logs emails instead of sending them.
#     TODO: Integrate with actual email service (SendGrid, AWS SES, etc.)
#     """
    
#     @staticmethod
#     async def send_email(
#         to_email: str,
#         subject: str,
#         body: str,
#         html_body: Optional[str] = None
#     ) -> bool:
#         """
#         Send an email to a user.
        
#         Args:
#             to_email: Recipient email address
#             subject: Email subject
#             body: Plain text email body
#             html_body: Optional HTML email body
            
#         Returns:
#             True if email was sent successfully, False otherwise
#         """
#         try:
#             # TODO: Replace with actual email sending logic
#             logger.info(f"[EMAIL] To: {to_email}")
#             logger.info(f"[EMAIL] Subject: {subject}")
#             logger.info(f"[EMAIL] Body: {body}")
            
#             # In production, you would use something like:
#             # await send_via_sendgrid(to_email, subject, body, html_body)
#             # or
#             # await send_via_aws_ses(to_email, subject, body, html_body)
            
#             return True
#         except Exception as e:
#             logger.error(f"Failed to send email to {to_email}: {str(e)}")
#             return False
    
#     @staticmethod
#     async def send_emi_failure_email(
#         to_email: str,
#         user_name: str,
#         loan_amount: float,
#         emi_amount: float,
#         account_balance: float,
#         due_date: str
#     ) -> bool:
#         """
#         Send EMI payment failure notification email.
#         """
#         subject = "EMI Payment Failed - Insufficient Funds"
        
#         body = f"""
# Dear {user_name},

# We attempted to deduct your EMI payment of ₹{emi_amount:,.2f} on {due_date}, but the transaction could not be completed due to insufficient funds in your account.

# Loan Details:
# - Loan Amount: ₹{loan_amount:,.2f}
# - EMI Amount: ₹{emi_amount:,.2f}
# - Current Account Balance: ₹{account_balance:,.2f}
# - Required Amount: ₹{emi_amount:,.2f}
# - Shortfall: ₹{(emi_amount - account_balance):,.2f}

# Please ensure sufficient funds are available in your account to avoid late payment charges and maintain your credit score.

# You can add funds to your account and the system will attempt the deduction again next month.

# If you have any questions, please contact our support team.

# Best regards,
# FastBank Team
#         """.strip()
        
#         return await EmailService.send_email(to_email, subject, body)


"""
Email Service for sending emails to users.
Logs emails if SMTP is not configured.
"""

import logging
from typing import Optional
import aiosmtplib
from email.message import EmailMessage

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending emails.
    Uses SMTP if configured, otherwise logs emails.
    """

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send an email to a user.
        """

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
    async def send_emi_failure_email(
        to_email: str,
        user_name: str,
        loan_amount: float,
        emi_amount: float,
        account_balance: float,
        due_date: str
    ) -> bool:
        """
        Send EMI payment failure notification email.
        """

        subject = "EMI Payment Failed - Insufficient Funds"

        shortfall = emi_amount - account_balance

        body = f"""
Dear {user_name},

We attempted to deduct your EMI payment of ₹{emi_amount:,.2f} on {due_date}, but the transaction could not be completed due to insufficient funds in your account.

Loan Details:
- Loan Amount: ₹{loan_amount:,.2f}
- EMI Amount: ₹{emi_amount:,.2f}
- Current Account Balance: ₹{account_balance:,.2f}
- Required Amount: ₹{emi_amount:,.2f}
- Shortfall: ₹{shortfall:,.2f}

Please ensure sufficient funds are available in your account to avoid late payment charges and maintain your credit score.

You can add funds to your account and the system will attempt the deduction again next month.

If you have any questions, please contact our support team.

Best regards,
FastBank Team
        """.strip()

        return await EmailService.send_email(to_email, subject, body)
