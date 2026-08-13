"""Authentication: signup, login, JWT tokens, and user persistence."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from . import db, store
from .config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class User(BaseModel):
    id: str
    name: str
    email: str
    hashed_password: str
    created_at: str = ""


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    # Derived from cases.owner_user_id rather than stored on the user, so there is one
    # answer to who owns a case.
    case_id: Optional[str] = None
    created_at: str = ""


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        name=user.name,
        email=user.email,
        case_id=store.get_case_id_for_user(user.id),
        created_at=user.created_at,
    )


# ---------------------------------------------------------------------------
# Persistence (Postgres when available, else in-memory)
# ---------------------------------------------------------------------------

_memory: dict[str, User] = {}

_COLUMNS = "id, name, email, hashed_password, created_at"


def _row_to_user(row) -> User:
    return User(
        id=row[0],
        name=row[1],
        email=row[2],
        hashed_password=row[3],
        created_at=row[4],
    )


def _save_user(user: User) -> None:
    if not db.available():
        _memory[user.id] = user
        return
    with db.connection() as conn:
        conn.execute(
            f"""
            INSERT INTO users ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                hashed_password = EXCLUDED.hashed_password
            """,
            (
                user.id,
                user.name,
                user.email.lower(),
                user.hashed_password,
                user.created_at,
            ),
        )


def _get_user_by_id(user_id: str) -> Optional[User]:
    if not db.available():
        return _memory.get(user_id)
    with db.connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def _get_user_by_email(email: str) -> Optional[User]:
    if not db.available():
        target = email.strip().lower()
        return next((u for u in _memory.values() if u.email.lower() == target), None)
    with db.connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM users WHERE email = %s", (email.strip().lower(),)
        ).fetchone()
    return _row_to_user(row) if row else None


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _create_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> Optional[str]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Dependency: get current user from Bearer token
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = _decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising."""
    if credentials is None:
        return None
    user_id = _decode_token(credentials.credentials)
    if user_id is None:
        return None
    return _get_user_by_id(user_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(req: SignupRequest) -> AuthResponse:
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not req.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = _get_user_by_email(req.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        id=str(uuid.uuid4()),
        name=req.name.strip(),
        email=req.email.strip().lower(),
        hashed_password=_hash_password(req.password),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _save_user(user)

    return AuthResponse(token=_create_token(user.id), user=_public(user))


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest) -> AuthResponse:
    user = _get_user_by_email(req.email)
    if user is None or not _verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return AuthResponse(token=_create_token(user.id), user=_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return _public(user)


class UpdateMeRequest(BaseModel):
    name: Optional[str] = None
    # The case the caller finished anonymously, to claim now that they have an account.
    case_id: Optional[str] = None


@router.patch("/me", response_model=UserPublic)
def update_me(
    body: UpdateMeRequest,
    user: User = Depends(get_current_user),
) -> UserPublic:
    """Rename the account, and/or claim the case whose intake was completed anonymously."""
    if body.name is not None:
        user.name = body.name
        _save_user(user)
    if body.case_id and not store.claim_case(body.case_id, user.id):
        # Unowned cases are claimable; anything else is either gone or somebody's already.
        raise HTTPException(status_code=404, detail="case not found")
    return _public(user)
