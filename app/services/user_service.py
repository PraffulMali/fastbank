from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.schemas.auth import UserLoginRequest, UserLoginResponse
from app.utils.security import verify_password
from app.utils.jwt import create_access_token, create_refresh_token

class UserService:
    @staticmethod
    async def login_user(db: AsyncSession, login_data: UserLoginRequest) -> UserLoginResponse:
        query = select(User).where(User.email == login_data.email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError("Invalid email or password")
            
        if not verify_password(login_data.password, user.password_hash):
            raise ValueError("Invalid email or password")
            
        if not user.is_active:
            raise ValueError("User account is inactive")
            
        token_data = {
            "sub": str(user.id),
            "role": user.role.value,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return UserLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )
