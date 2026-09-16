"""Authentication: signup, login, JWT tokens, and user persistence."""

import logging
import secrets
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

logger = logging.getLogger("ilera.auth")

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
    phone: str = ""
    created_at: str = ""
    email_verified: bool = True  # True so existing pre-verification rows are not locked out


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    phone: str = ""
    # Derived from cases.owner_user_id rather than stored on the user, so there is one
    # answer to who owns a case.
    case_id: Optional[str] = None
    created_at: str = ""


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        case_id=store.get_case_id_for_user(user.id),
        created_at=user.created_at,
    )


# ---------------------------------------------------------------------------
# Persistence (Postgres when available, else in-memory)
# ---------------------------------------------------------------------------

_memory: dict[str, User] = {}

_COLUMNS = "id, name, email, hashed_password, phone, created_at, email_verified"


def _row_to_user(row) -> User:
    return User(
        id=row[0],
        name=row[1],
        email=row[2],
        hashed_password=row[3],
        phone=row[4],
        created_at=row[5],
        email_verified=row[6],
    )


def _save_user(user: User) -> None:
    if not db.available():
        _memory[user.id] = user
        return
    with db.connection() as conn:
        conn.execute(
            f"""
            INSERT INTO users ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                hashed_password = EXCLUDED.hashed_password,
                phone = EXCLUDED.phone,
                email_verified = EXCLUDED.email_verified
            """,
            (
                user.id,
                user.name,
                user.email.lower(),
                user.hashed_password,
                user.phone,
                user.created_at,
                user.email_verified,
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
# Verification token persistence
# ---------------------------------------------------------------------------

_token_memory: dict[str, dict] = {}  # token -> {user_id, expires_at, used}
_otp_memory: dict[str, dict] = {}   # id -> {user_id, code, expires_at, used, attempts}


def _save_verification_token(token: str, user_id: str, expires_at: datetime) -> None:
    if not db.available():
        _token_memory[token] = {"user_id": user_id, "expires_at": expires_at, "used": False}
        return
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO verification_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )


def _consume_verification_token(token: str) -> Optional[str]:
    """Validate and atomically consume a token. Returns user_id if valid, else None."""
    now = datetime.now(timezone.utc)
    if not db.available():
        entry = _token_memory.get(token)
        if not entry or entry["used"] or entry["expires_at"] < now:
            return None
        entry["used"] = True
        return entry["user_id"]
    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM verification_tokens
            WHERE token = %s AND used = false AND expires_at > %s
            """,
            (token, now),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE verification_tokens SET used = true WHERE token = %s",
            (token,),
        )
    return row[0]


# ---------------------------------------------------------------------------
# Email sending — no PHI in any email, only the verification link
# ---------------------------------------------------------------------------


def _create_otp(user_id: str) -> str:
    """Generate a 6-digit OTP, persist it, and return the code."""
    otp_id = str(uuid.uuid4())
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    if not db.available():
        _otp_memory[otp_id] = {
            "user_id": user_id,
            "code": code,
            "expires_at": expires_at,
            "used": False,
            "attempts": 0,
        }
        return code
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO login_otps (id, user_id, code, expires_at) VALUES (%s, %s, %s, %s)",
            (otp_id, user_id, code, expires_at),
        )
    return code


def _verify_otp(user_id: str, code: str) -> bool:
    """Validate an OTP for a user. Marks it used on success; increments attempts on failure.

    Returns True if valid, False if wrong code, raises HTTPException if expired/locked.
    """
    now = datetime.now(timezone.utc)
    max_attempts = 5

    if not db.available():
        entry = next(
            (e for e in _otp_memory.values()
             if e["user_id"] == user_id and not e["used"] and e["expires_at"] > now),
            None,
        )
        if entry is None:
            raise HTTPException(status_code=400, detail="Code expired. Please sign in again.")
        if entry["attempts"] >= max_attempts:
            raise HTTPException(status_code=400, detail="Too many attempts. Please sign in again.")
        if entry["code"] != code:
            entry["attempts"] += 1
            return False
        entry["used"] = True
        return True

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT id, code, attempts FROM login_otps
            WHERE user_id = %s AND used = false AND expires_at > %s
            ORDER BY expires_at DESC LIMIT 1
            """,
            (user_id, now),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=400, detail="Code expired. Please sign in again.")
        otp_id, stored_code, attempts = row[0], row[1], row[2]
        if attempts >= max_attempts:
            raise HTTPException(status_code=400, detail="Too many attempts. Please sign in again.")
        if stored_code != code:
            conn.execute(
                "UPDATE login_otps SET attempts = attempts + 1 WHERE id = %s", (otp_id,)
            )
            return False
        conn.execute("UPDATE login_otps SET used = true WHERE id = %s", (otp_id,))
    return True


def _send_otp_email(email: str, code: str) -> None:
    settings = get_settings()
    if not settings.acs_email_connection_string:
        logger.info("LOGIN OTP (dev — set ACS_EMAIL_CONNECTION_STRING to send real email): %s", code)
        return
    from azure.communication.email import EmailClient  # lazy import

    client = EmailClient.from_connection_string(settings.acs_email_connection_string)
    client.begin_send({
        "senderAddress": settings.from_email,
        "recipients": {"to": [{"address": email}]},
        "content": {
            "subject": f"{code} is your Ilera login code",
            "html": (
                f"<p>Your Ilera login code is: <strong>{code}</strong></p>"
                "<p>This code expires in 10 minutes and can only be used once.</p>"
                "<p>If you did not attempt to sign in, please change your password immediately.</p>"
            ),
        },
    })


def _send_verification_email(email: str, token: str) -> None:
    settings = get_settings()
    verify_url = f"{settings.app_url}/verify-email?token={token}"
    if not settings.acs_email_connection_string:
        # Dev mode: log the link so developers can click it without ACS configured.
        logger.info(
            "EMAIL VERIFICATION (dev — set ACS_EMAIL_CONNECTION_STRING to send real email): %s",
            verify_url,
        )
        return
    from azure.communication.email import EmailClient  # lazy import

    client = EmailClient.from_connection_string(settings.acs_email_connection_string)
    client.begin_send({
        "senderAddress": settings.from_email,
        "recipients": {"to": [{"address": email}]},
        "content": {
            "subject": "Verify your Ilera account",
            "html": (
                "<p>Thanks for creating an Ilera account.</p>"
                "<p>Click the link below to verify your email address. "
                "This link expires in 1 hour and can only be used once.</p>"
                f'<p><a href="{verify_url}">Verify my email</a></p>'
                "<p>If you did not create an Ilera account, you can safely ignore this email.</p>"
            ),
        },
    })


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
    # Government forms need the caregiver's phone number; signup, after the strategy has been
    # read, is where it is asked for.
    phone: str = ""
    # The case whose strategy the caller just read, claimed as part of creating the account.
    case_id: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class SignupResponse(BaseModel):
    message: str


@router.post("/signup", response_model=SignupResponse, status_code=202)
def signup(req: SignupRequest) -> SignupResponse:
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not req.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = _get_user_by_email(req.email)
    if existing is not None:
        if existing.email_verified:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        # Unverified duplicate: resend the link so the user can finish up.
        token = str(uuid.uuid4())
        _save_verification_token(token, existing.id, datetime.now(timezone.utc) + timedelta(hours=1))
        _send_verification_email(existing.email, token)
        return SignupResponse(message="Check your email to verify your account")

    user = User(
        id=str(uuid.uuid4()),
        name=req.name.strip(),
        email=req.email.strip().lower(),
        hashed_password=_hash_password(req.password),
        phone=req.phone.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
        email_verified=False,
    )
    _save_user(user)
    # Claim the case now so the link between the anonymous case and the new account is
    # established before email verification. A stale or foreign case id is not worth failing
    # account creation over.
    if req.case_id:
        _try_claim(req.case_id, user)

    token = str(uuid.uuid4())
    _save_verification_token(token, user.id, datetime.now(timezone.utc) + timedelta(hours=1))
    _send_verification_email(user.email, token)
    return SignupResponse(message="Check your email to verify your account")


def _try_claim(case_id: str, user: User) -> bool:
    """Take ownership of an anonymous case and stamp the account's contact details onto it.

    False if the case is gone or already belongs to somebody else.
    """
    if not store.claim_case(case_id, user.id):
        return False
    store.apply_contact(case_id, name=user.name, email=user.email, phone=user.phone)
    return True


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(req: VerifyEmailRequest) -> AuthResponse:
    user_id = _consume_verification_token(req.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user = _get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.email_verified = True
    _save_user(user)
    return AuthResponse(token=_create_token(user.id), user=_public(user))


@router.post("/login", response_model=SignupResponse, status_code=202)
def login(req: LoginRequest) -> SignupResponse:
    user = _get_user_by_email(req.email)
    if user is None or not _verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before signing in",
        )
    code = _create_otp(user.id)
    _send_otp_email(user.email, code)
    return SignupResponse(message="Check your email for a login code")


class VerifyOtpRequest(BaseModel):
    email: str
    code: str


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(req: VerifyOtpRequest) -> AuthResponse:
    user = _get_user_by_email(req.email)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid code")
    if not _verify_otp(user.id, req.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid code")
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
    if body.case_id and not _try_claim(body.case_id, user):
        # Unowned cases are claimable; anything else is either gone or somebody's already.
        raise HTTPException(status_code=404, detail="case not found")
    return _public(user)
