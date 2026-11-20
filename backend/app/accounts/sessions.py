"""Session tokens (JWT) and the FastAPI dependencies that turn one into a User."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.accounts.users import User, get_user_by_id
from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    return get_settings().jwt_secret


def create_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": user_id, "exp": expire}, _secret(), algorithm=settings.jwt_algorithm)


def _user_from(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[User]:
    if credentials is None:
        return None
    try:
        user_id = jwt.decode(credentials.credentials, _secret(),
                             algorithms=[get_settings().jwt_algorithm]).get("sub")
    except JWTError:
        return None
    return get_user_by_id(user_id) if user_id else None


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> User:
    user = _user_from(credentials)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Optional[User]:
    return _user_from(credentials)
