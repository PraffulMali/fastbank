from typing import Optional, List
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from jose import JWTError, jwt

from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import UserCreateBySuperAdmin, UserCreateByAdmin, UserUpdate
from app.schemas.auth import UserLoginRequest, UserLoginResponse, TokenRefreshResponse
from app.utils.security import get_password_hash, verify_password
from app.utils.jwt import create_access_token, create_refresh_token
from app.config.settings import settings
import secrets


class UserService:
    @staticmethod
    async def login_user(db: AsyncSession, login_data: UserLoginRequest) -> UserLoginResponse:
        query = select(User).where(User.email == login_data.email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError("Invalid email or password")
            
        if not verify_password(login_data.password, user.password):
            raise ValueError("Invalid email or password")
            
        if not user.is_active:
            raise ValueError("User account is inactive")
            
        token_data = {
            "sub": str(user.id),
            "role": user.role.value,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None
        }
        
        access_token, access_jti, access_exp = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data, access_jti=access_jti, access_exp=access_exp)
        
        return UserLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: uuid.UUID,
        old_password: str,
        new_password: str
    ) -> bool:
        """Change user password"""
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        # Verify old password
        if not verify_password(old_password, user.password):
            raise ValueError("Invalid old password")
        
        # Update password
        user.password = get_password_hash(new_password)
        await db.commit()
        
        return True

    @staticmethod
    async def refresh_token(
        refresh_token: str, 
        db: AsyncSession,
        access_token_jti: Optional[str] = None,
        access_token_exp: Optional[int] = None
    ) -> TokenRefreshResponse:
        """Refresh access token using refresh token"""
        from app.database.redis import get_redis
        try:
            # Decode refresh token
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            # Validate token type
            if payload.get("token_type") != "refresh":
                raise ValueError("Invalid token type")
            
            refresh_jti = payload.get("jti")
            refresh_exp = payload.get("exp")
            
            if not refresh_jti or not refresh_exp:
                raise ValueError("Invalid token payload")
            
            # Check if refresh token is blacklisted
            redis = await get_redis()
            is_blacklisted = await redis.get(f"blacklist:token:{refresh_jti}")
            if is_blacklisted:
                raise ValueError("Token has been invalidated. Please login again.")
            
            # Get user ID from token
            user_id_str = payload.get("sub")
            if not user_id_str:
                raise ValueError("Invalid token payload")
            
            user_id = uuid.UUID(user_id_str)
            
            # Verify user still exists and is active
            user = await db.get(User, user_id)
            if not user:
                raise ValueError("User not found")
            
            if not user.is_active:
                raise ValueError("User account is inactive")
            
            # Create new token pair
            token_data = {
                "sub": str(user.id),
                "role": user.role.value,
                "tenant_id": str(user.tenant_id) if user.tenant_id else None
            }
            
            new_access_token, new_access_jti, new_access_exp = create_access_token(token_data)
            new_refresh_token = create_refresh_token(
                token_data, 
                access_jti=new_access_jti, 
                access_exp=new_access_exp
            )
            
            # Blacklist the old refresh token
            await UserService.logout_user(refresh_jti, refresh_exp)
            
            # Blacklist the old access token if provided in header
            if access_token_jti and access_token_exp:
                await UserService.logout_user(access_token_jti, access_token_exp)
            elif payload.get("access_jti") and payload.get("access_exp"):
                # Blacklist the access token linked to this refresh token (from payload)
                await UserService.logout_user(payload.get("access_jti"), payload.get("access_exp"))
            
            return TokenRefreshResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token
            )
            
        except JWTError:
            raise ValueError("Invalid or expired refresh token")

    @staticmethod
    async def create_user_by_super_admin(
        db: AsyncSession,
        user_in: UserCreateBySuperAdmin
    ) -> tuple[User, str, str]:
        """
        SUPER_ADMIN creates an ADMIN user for a specific tenant.
        Returns: (User, verification_token, temp_password)
        """
        # Validate tenant exists and is active
        from app.models.tenant import Tenant
        tenant = await db.get(Tenant, user_in.tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")
        if not tenant.is_active:
            raise ValueError("Cannot create user for inactive/deleted tenant")
        
        # Check if email already exists
        query = select(User).where(User.email == user_in.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError("Email already exists")
        
        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        
        # Create temporary password (will be set via email verification)
        temp_password = secrets.token_urlsafe(16)
        
        new_user = User(
            email=user_in.email,
            full_name=user_in.full_name,
            password=get_password_hash(temp_password),
            role=UserRole.ADMIN,
            tenant_id=user_in.tenant_id,
            is_active=True
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        return new_user, verification_token, temp_password

    @staticmethod
    async def create_user_by_admin(
        db: AsyncSession,
        user_in: UserCreateByAdmin,
        admin_tenant_id: uuid.UUID,
        admin_user_id: uuid.UUID
    ) -> tuple[User, str, str]:
        """
        ADMIN creates a USER within their own tenant with KYC details.
        Returns: (User, verification_token, temp_password)
        """
        # Check if email already exists
        query = select(User).where(User.email == user_in.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError("Email already exists")
        
        # Check for duplicate phone number in tenant
        from app.models.user_identity import UserIdentity
        phone_query = select(UserIdentity).where(
            and_(
                UserIdentity.phone_number == user_in.phone_number,
                UserIdentity.tenant_id == admin_tenant_id
            )
        )
        phone_result = await db.execute(phone_query)
        if phone_result.scalar_one_or_none():
            raise ValueError("Phone number already exists in this tenant")
        
        # Check for duplicate PAN in tenant
        pan_query = select(UserIdentity).where(
            and_(
                UserIdentity.pan_number == user_in.pan_number,
                UserIdentity.tenant_id == admin_tenant_id
            )
        )
        pan_result = await db.execute(pan_query)
        if pan_result.scalar_one_or_none():
            raise ValueError("PAN number already exists in this tenant")
        
        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        
        # Create temporary password
        temp_password = secrets.token_urlsafe(16)
        
        new_user = User(
            email=user_in.email,
            full_name=user_in.full_name,
            password=get_password_hash(temp_password),
            role=UserRole.USER,
            tenant_id=admin_tenant_id,
            is_active=True
        )
        
        db.add(new_user)
        await db.flush()
        
        # Create UserIdentity with verification info
        user_identity = UserIdentity(
            tenant_id=admin_tenant_id,
            user_id=new_user.id,
            phone_number=user_in.phone_number,
            date_of_birth=user_in.date_of_birth,
            pan_number=user_in.pan_number,
            address_line1=user_in.address_line1,
            address_line2=user_in.address_line2,
            city=user_in.city,
            state=user_in.state,
            postal_code=user_in.postal_code,
            country=user_in.country,
            verified_by=admin_user_id,
            verified_at=datetime.now(timezone.utc)
        )
        
        db.add(user_identity)
        await db.commit()
        await db.refresh(new_user)
        
        return new_user, verification_token, temp_password

    @staticmethod
    async def list_users_for_super_admin(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """List all ADMIN users across all tenants"""
        query = select(User).where(
            User.role == UserRole.ADMIN
        ).offset(skip).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_users_for_admin(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """List all users within a specific tenant"""
        query = select(User).where(
            User.tenant_id == tenant_id
        ).offset(skip).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[User]:
        """Get user by ID with user_identity eagerly loaded"""
        from sqlalchemy.orm import selectinload
        
        query = select(User).where(User.id == user_id).options(
            selectinload(User.user_identity)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        user_update: UserUpdate
    ) -> Optional[User]:
        """Update user details"""
        user = await db.get(User, user_id)
        if not user:
            return None
        
        if user_update.full_name is not None:
            user.full_name = user_update.full_name
        
        if user_update.is_active is not None:
            user.is_active = user_update.is_active
            if user_update.is_active:
                user.deleted_at = None
            else:
                user.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def soft_delete_user(
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[User]:
        """Soft delete a user"""
        user = await db.get(User, user_id)
        if not user:
            return None
        
        if not user.is_active:
            raise ValueError("User is already deleted")
        
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def verify_user_email(db: AsyncSession, token: str) -> bool:
        """Verify user email using token from Redis"""
        from app.database.redis import get_redis
        from app.utils.security import hash_token
        
        hashed_token = hash_token(token)
        redis = await get_redis()
        user_id_str = await redis.get(f"verify_token:{hashed_token}")
        
        if not user_id_str:
            return False
            
        user_id = uuid.UUID(user_id_str)
        user = await db.get(User, user_id)
        
        if not user:
            return False
            
        user.is_email_verified = True
        await db.commit()
        
        # Delete the token after successful verification
        await redis.delete(f"verify_token:{hashed_token}")
        return True

        
    @staticmethod
    async def logout_user(jti: str, exp: int) -> bool:
        """
        Logout user by storing token jti in Redis blacklist
        The blacklist entry will expire when the token itself expires
        """
        from app.database.redis import get_redis
        import time
        
        redis = await get_redis()
        
        # Calculate remaining time for the token
        current_time = int(time.time())
        ttl = exp - current_time
        
        if ttl > 0:
            blacklist_key = f"blacklist:token:{jti}"
            await redis.setex(
                blacklist_key,
                ttl,
                "logged_out"
            )
        
        return True

    @staticmethod
    async def request_password_reset(db: AsyncSession, email: str) -> Optional[tuple[User, str]]:
        """
        Request password reset - sends email only if user is active and email is verified.
        Returns: (User, reset_token) or None if user doesn't meet criteria
        """
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            # Don't reveal if user exists or not
            return None
        
        if not user.is_active:
            # Don't reveal if user is inactive
            return None
        
        if not user.is_email_verified:
            # Don't reveal if email is not verified
            return None
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        
        return user, reset_token


    @staticmethod
    async def reset_password_with_token(db: AsyncSession, token: str, new_password: str) -> bool:
        """
        Reset password using the token from Redis.
        Returns True if successful, False otherwise.
        """
        from app.database.redis import get_redis
        from app.utils.security import hash_token
        
        hashed_token = hash_token(token)
        redis = await get_redis()
        user_id_str = await redis.get(f"reset_token:{hashed_token}")
        
        if not user_id_str:
            return False
        
        user_id = uuid.UUID(user_id_str)
        user = await db.get(User, user_id)
        
        if not user:
            return False
        
        # Update password
        user.password = get_password_hash(new_password)
        await db.commit()
        
        # Delete the token after successful password reset
        await redis.delete(f"reset_token:{hashed_token}")
        
        return True


    @staticmethod
    async def resend_verification_email(db: AsyncSession, email: str) -> Optional[tuple[User, str]]:
        """
        Resend verification email - only if user exists and email is not verified.
        Returns: (User, verification_token) or None if user doesn't meet criteria
        """
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            # Don't reveal if user exists
            return None
        
        if user.is_email_verified:
            # Email already verified
            return None
        
        if not user.is_active:
            # User is inactive
            return None
        
        # Generate new verification token
        verification_token = secrets.token_urlsafe(32)
        
        return user, verification_token