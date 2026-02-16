from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from uuid import uuid4
from app.config.settings import settings


def create_access_token(data: dict) -> tuple[str, str, int]:
    to_encode = data.copy()

    exp_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + exp_delta
    exp_timestamp = int(expire.timestamp())
    jti = str(uuid4())

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": jti,
            "token_type": "access",
        }
    )

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt, jti, exp_timestamp


def create_refresh_token(
    data: dict, access_jti: str = None, access_exp: int = None
) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid4()),
            "token_type": "refresh",
        }
    )

    if access_jti:
        to_encode["access_jti"] = access_jti
    if access_exp:
        to_encode["access_exp"] = access_exp

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None
