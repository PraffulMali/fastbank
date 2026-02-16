from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    UserLoginRequest, 
    UserLoginResponse, 
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserLogoutRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResendVerificationRequest
)
from app.services.user_service import UserService
from app.dependencies import get_current_user, security
from app.services.email_service import EmailService
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config.settings import settings
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=UserLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    login_data: UserLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await UserService.login_user(db, login_data)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )




@router.post("/refresh", response_model=TokenRefreshResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    token_data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None
):
    try:
        access_token_jti = None
        access_token_exp = None
        
        if credentials:
            try:
                payload = jwt.decode(
                    credentials.credentials, 
                    settings.SECRET_KEY, 
                    algorithms=[settings.ALGORITHM],
                    options={"verify_exp": False}
                )
                access_token_jti = payload.get("jti")
                access_token_exp = payload.get("exp")
            except JWTError:
                pass

        result = await UserService.refresh_token(
            token_data.refresh_token, 
            db,
            access_token_jti=access_token_jti,
            access_token_exp=access_token_exp
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    logout_data: UserLogoutRequest,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    try:
        await UserService.blacklist_token(credentials.credentials)
        await UserService.blacklist_token(logout_data.refresh_token)
        
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to logout"
        )


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    success = await UserService.verify_user_email(db, token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    return {"message": "Email verified successfully"}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    result = await UserService.request_password_reset(db, request_data.email)
    
    if result:
        user, reset_token = result
        background_tasks.add_task(
            EmailService.send_password_reset_email,
            user.email,
            reset_token,
            str(user.id)
        )
    
    return {"message": "If your email is registered and verified, you will receive a password reset link"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    reset_data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    success = await UserService.reset_password_with_token(
        db,
        reset_data.token,
        reset_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    return {"message": "Password has been reset successfully"}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(
    request_data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    result = await UserService.resend_verification_email(db, request_data.email)
    
    if result:
        user, verification_token = result
        background_tasks.add_task(
            EmailService.send_verification_resend_email,
            user.email,
            verification_token,
            str(user.id)
        )
    
    return {"message": "If your email is registered and unverified, you will receive a new verification link"}