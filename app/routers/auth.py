from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    UserLoginRequest, 
    UserLoginResponse, 
    ChangePasswordRequest,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserLogoutRequest
)
from app.services.user_service import UserService
from app.dependencies import get_current_user, security
from fastapi.security import HTTPAuthorizationCredentials
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=UserLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    login_data: UserLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Login endpoint - returns access and refresh tokens
    """
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


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: ChangePasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Change password endpoint - requires valid access token
    User provides old password, new password, and confirm password
    """
    try:
        await UserService.change_password(
            db,
            current_user.id,
            password_data.old_password,
            password_data.new_password
        )
        return {"message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.post("/refresh", response_model=TokenRefreshResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    token_data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None
):
    """
    Refresh token endpoint - exchanges refresh token for new access and refresh tokens
    Also blacklists the old refresh token and the old access token (if provided)
    """
    try:
        access_token_jti = None
        access_token_exp = None
        
        if credentials:
            from app.config.settings import settings
            from jose import jwt, JWTError
            try:
                # We use verify=False because the access token might already be expired
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
    """
    Logout endpoint - invalidates the current access token and the provided refresh token
    Requires valid access token in Authorization header and refresh token in request body
    """
    try:
        from app.config.settings import settings
        from jose import jwt
        
        # Blacklist access token
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
        
        if jti and exp:
            await UserService.logout_user(jti, exp)
            
        # Blacklist refresh token
        refresh_token = logout_data.refresh_token
        try:
            refresh_payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            refresh_jti = refresh_payload.get("jti")
            refresh_exp = refresh_payload.get("exp")
            
            if refresh_jti and refresh_exp:
                await UserService.logout_user(refresh_jti, refresh_exp)
        except Exception:
            # If refresh token is already invalid/expired, we don't need to blacklist it
            pass
        
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
    """
    Email verification endpoint
    """
    success = await UserService.verify_user_email(db, token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    return {"message": "Email verified successfully"}