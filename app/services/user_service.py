from typing import Optional, List, Union
import uuid
import secrets
import time
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from jose import JWTError, jwt

from app.utils.pagination import Paginator, Page

from app.models.user import User
from app.models.tenant import Tenant
from app.models.account_type import AccountType
from app.models.user_identity import UserIdentity
from app.models.enums import UserRole
from app.schemas.user import (
    UserCreateBySuperAdmin, 
    UserCreateByAdmin, 
    UserUpdate,
    UserDetailResponse,
    UserSelfResponse
)
from app.schemas.auth import UserLoginRequest, UserLoginResponse, TokenRefreshResponse
from app.utils.security import get_password_hash, verify_password, hash_token
from app.utils.jwt import create_access_token, create_refresh_token
from app.config.settings import settings
from app.database.redis import get_redis
from app.services.account_service import AccountService
from app.schemas.account import AccountCreateByAdmin


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
            
        if not user.is_email_verified:
            raise ValueError("Email not verified. Please verify your email to login.")
            
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
            
            if not user.is_email_verified:
                raise ValueError("Email not verified. Please verify your email to login.")
            
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
        # Validate tenant exists and is active
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
        # Check if email already exists
        query = select(User).where(User.email == user_in.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError("Email already exists")
        
        # Check for duplicate phone number in tenant
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
        
        # Validate account type exists for this tenant
        account_type_obj = await db.get(AccountType, user_in.account_type_id)
        
        if not account_type_obj:
            raise ValueError("Account type not found")
        
        if account_type_obj.tenant_id != admin_tenant_id:
            raise ValueError("Account type does not belong to this tenant")

        # Create bank account for the user
        account_in = AccountCreateByAdmin(
            user_id=new_user.id,
            account_type_id=user_in.account_type_id
        )
        await AccountService.create_account(
            db, account_in, new_user.id, admin_tenant_id
        )
        
        await db.commit()
        await db.refresh(new_user)
        
        return new_user, verification_token, temp_password

    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_in: Union[UserCreateBySuperAdmin, UserCreateByAdmin],
        current_user: User
    ) -> tuple[User, str, str]:
        if current_user.role == UserRole.SUPER_ADMIN:
            if not isinstance(user_in, UserCreateBySuperAdmin):
                raise ValueError("SUPER_ADMIN must provide tenant_id")
            return await UserService.create_user_by_super_admin(db, user_in)
        
        elif current_user.role == UserRole.ADMIN:
            if isinstance(user_in, UserCreateBySuperAdmin):
                raise ValueError("ADMIN cannot specify tenant_id")
            return await UserService.create_user_by_admin(
                db, user_in, current_user.tenant_id, current_user.id
            )
        else:
            raise ValueError("Unauthorized to create users")


    @staticmethod
    def get_users_query(current_user: User):
        if current_user.role == UserRole.SUPER_ADMIN:
            return select(User).where(User.role == UserRole.ADMIN)
        else:  # ADMIN
            return select(User).where(User.tenant_id == current_user.tenant_id)

    @staticmethod
    async def list_users(
        db: AsyncSession,
        current_user: User,
        paginator: Paginator
    ) -> Page:
        query = UserService.get_users_query(current_user)
        return await paginator.paginate(db, query)

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[User]:
        
        query = select(User).where(User.id == user_id).options(
            selectinload(User.user_identity)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_with_permissions(
        db: AsyncSession, 
        user_id: uuid.UUID, 
        current_user: User
    ) -> Union[UserDetailResponse, UserSelfResponse]:
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("User not found")
        
        if current_user.role == UserRole.SUPER_ADMIN:
            if user.role != UserRole.ADMIN:
                raise PermissionError("SUPER_ADMIN can only view ADMIN users")
            return UserDetailResponse.model_validate(user)
        
        elif current_user.role == UserRole.ADMIN:
            if user.tenant_id != current_user.tenant_id:
                raise PermissionError("Cannot view users from other tenants")
            return UserDetailResponse.model_validate(user)
        
        else:  # USER
            if user.id != current_user.id:
                raise PermissionError("You can only view your own profile")
            return UserSelfResponse.model_validate(user)

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        user_update: UserUpdate
    ) -> Optional[User]:
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
    async def update_user_with_permissions(
        db: AsyncSession,
        user_id: uuid.UUID,
        user_update: UserUpdate,
        current_user: User
    ) -> User:
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("User not found")
        
        if current_user.role == UserRole.SUPER_ADMIN:
            if user.role != UserRole.ADMIN:
                raise PermissionError("SUPER_ADMIN can only update ADMIN users")
        else: # ADMIN
            if user.tenant_id != current_user.tenant_id:
                raise PermissionError("Cannot update users from other tenants")
        
        return await UserService.update_user(db, user_id, user_update)

    @staticmethod
    async def soft_delete_user_with_permissions(
        db: AsyncSession,
        user_id: uuid.UUID,
        current_user: User
    ):
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("User not found")
        
        if current_user.role == UserRole.SUPER_ADMIN:
            if user.role != UserRole.ADMIN:
                raise PermissionError("SUPER_ADMIN can only delete ADMIN users")
        else: # ADMIN
            if user.tenant_id != current_user.tenant_id:
                raise PermissionError("Cannot delete users from other tenants")
        
        return await UserService.soft_delete_user(db, user_id)

    @staticmethod
    async def soft_delete_user(
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[User]:
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
    async def blacklist_token(token: str) -> bool:
        from jose import jwt, JWTError
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp")
            
            if jti and exp:
                return await UserService.logout_user(jti, exp)
        except JWTError:
            pass
        return False

    @staticmethod
    async def logout_user(jti: str, exp: int) -> bool:
        
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