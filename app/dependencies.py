from typing import Annotated
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.database import get_db
from app.database.redis import get_redis
from app.models.user import User
from app.models.enums import UserRole

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    Dependency to get current authenticated user from JWT token
    Also checks if user is blacklisted (logged out)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        jti = payload.get("jti")
        
        if user_id_str is None or jti is None:
            raise credentials_exception
        
        user_id = uuid.UUID(user_id_str)
        
        # Check if token is blacklisted
        redis = await get_redis()
        is_blacklisted = await redis.get(f"blacklist:token:{jti}")
        
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated. Please login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
    except JWTError:
        raise credentials_exception
    except ValueError:
        raise credentials_exception
    
    # Get user from database
    user = await db.get(User, user_id)
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


async def require_super_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Dependency to require SUPER_ADMIN role
    """
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires SUPER_ADMIN privileges"
        )
    return current_user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Dependency to require at least ADMIN role (SUPER_ADMIN or ADMIN)
    """
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires ADMIN privileges"
        )
    return current_user