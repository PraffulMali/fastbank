from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import UserLoginRequest, UserLoginResponse
from app.services.user_service import UserService

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