import aiosmtplib
from email.message import EmailMessage
from app.config.settings import settings
from app.database.redis import get_redis
from app.utils.security import hash_token

async def send_verification_email(email: str, token: str, temp_password: str, user_id: str):
    # 1. Store hashed token in Redis with 15 minutes TTL
    hashed_token = hash_token(token)
    redis = await get_redis()
    await redis.setex(f"verify_token:{hashed_token}", 900, str(user_id))

    
    # 2. Build verification link
    verify_link = f"{settings.FRONTEND_URL}/verify?token={token}"
    
    # 3. Create email message
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    message["Subject"] = "Welcome to FastBank - Verify Your Account"
    
    content = f"""
    Hello,
    
    Welcome to FastBank! Your account has been created.
    
    Your temporary password is: {temp_password}
    
    Please verify your account by clicking the link below (valid for 15 minutes):
    {verify_link}
    
    If you did not request this, please ignore this email.
    """
    message.set_content(content)
    
    # 4. Send email
    try:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=True if settings.SMTP_PORT == 465 else False,
                start_tls=True if settings.SMTP_PORT == 587 else False
            )
        else:
            # Fallback for development if SMTP credentials are missing
            print("\n" + "!"*60)
            print("SMTP CREDENTIALS MISSING. PRINTING EMAIL TO CONSOLE:")
            print(f"To:      {email}")
            print(f"Subject: {message['Subject']}")
            print(f"Body:    {content}")
            print("!"*60 + "\n")
            
        print(f"Verification email task completed for {email}")
    except Exception as e:
        print(f"Failed to send email to {email}: {e}")


async def send_password_reset_email(email: str, token: str, user_id: str):
    # 1. Store hashed token in Redis with 15 minutes TTL
    hashed_token = hash_token(token)
    redis = await get_redis()
    await redis.setex(f"reset_token:{hashed_token}", 900, str(user_id))
    
    # 2. Build reset link
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    
    # 3. Create email message
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    message["Subject"] = "FastBank - Password Reset Request"
    
    content = f"""
    Hello,
    
    We received a request to reset your password for your FastBank account.
    
    Please reset your password by clicking the link below (valid for 15 minutes):
    {reset_link}
    
    If you did not request a password reset, please ignore this email.
    Your password will remain unchanged.
    """
    message.set_content(content)
    
    # 4. Send email
    try:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=True if settings.SMTP_PORT == 465 else False,
                start_tls=True if settings.SMTP_PORT == 587 else False
            )
        else:
            # Fallback for development if SMTP credentials are missing
            print("\n" + "!"*60)
            print("SMTP CREDENTIALS MISSING. PRINTING EMAIL TO CONSOLE:")
            print(f"To:      {email}")
            print(f"Subject: {message['Subject']}")
            print(f"Body:    {content}")
            print("!"*60 + "\n")
            
        print(f"Password reset email sent to {email}")
    except Exception as e:
        print(f"Failed to send password reset email to {email}: {e}")


async def send_verification_resend_email(email: str, token: str, user_id: str):
    # 1. Store hashed token in Redis with 15 minutes TTL
    hashed_token = hash_token(token)
    redis = await get_redis()
    await redis.setex(f"verify_token:{hashed_token}", 900, str(user_id))
    
    # 2. Build verification link
    verify_link = f"{settings.FRONTEND_URL}/verify?token={token}"
    
    # 3. Create email message
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    message["Subject"] = "FastBank - Verify Your Account"
    
    content = f"""
    Hello,
    
    You requested a new verification link for your FastBank account.
    
    Please verify your account by clicking the link below (valid for 15 minutes):
    {verify_link}
    
    If you did not request this, please ignore this email.
    """
    message.set_content(content)
    
    # 4. Send email
    try:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=True if settings.SMTP_PORT == 465 else False,
                start_tls=True if settings.SMTP_PORT == 587 else False
            )
        else:
            # Fallback for development if SMTP credentials are missing
            print("\n" + "!"*60)
            print("SMTP CREDENTIALS MISSING. PRINTING EMAIL TO CONSOLE:")
            print(f"To:      {email}")
            print(f"Subject: {message['Subject']}")
            print(f"Body:    {content}")
            print("!"*60 + "\n")
            
        print(f"Verification resend email sent to {email}")
    except Exception as e:
        print(f"Failed to send verification resend email to {email}: {e}")