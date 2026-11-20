"""Account endpoints: signup with email verification, password + emailed-code login, profile."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.accounts import codes, mail
from app.accounts.sessions import create_token, get_current_user
from app.accounts.users import User, get_user_by_email, get_user_by_id, hash_password, save_user, verify_password
from app.cases import store

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    return UserPublic(id=user.id, name=user.name, email=user.email, phone=user.phone,
                      case_id=store.get_case_id_for_user(user.id), created_at=user.created_at)


def _claim(case_id: str, user: User) -> bool:
    """Take ownership of an anonymous case and stamp the account's contact details onto it.
    False if the case is gone or already belongs to somebody else."""
    if not store.claim_case(case_id, user.id):
        return False
    store.apply_contact(case_id, name=user.name, email=user.email, phone=user.phone)
    return True


class SignupRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=6)
    # Government forms need the caregiver's phone number; signup, after the strategy has been
    # read, is where it is asked for.
    phone: str = ""
    # The case whose strategy the caller just read, claimed as part of creating the account.
    case_id: Optional[str] = None

    @field_validator("name", "email")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("is required")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyOtpRequest(BaseModel):
    email: str
    code: str


class UpdateMeRequest(BaseModel):
    name: Optional[str] = None
    # The case the caller finished anonymously, to claim now that they have an account.
    case_id: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class SignupResponse(BaseModel):
    message: str


@router.post("/signup", response_model=SignupResponse, status_code=202)
def signup(req: SignupRequest) -> SignupResponse:
    existing = get_user_by_email(req.email)
    if existing is not None and existing.email_verified:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if existing is None:
        existing = User(id=str(uuid.uuid4()), name=req.name, email=req.email.lower(),
                        hashed_password=hash_password(req.password), phone=req.phone,
                        created_at=datetime.now(timezone.utc).isoformat(), email_verified=False)
        save_user(existing)
        # Claim the case now so the anonymous case and the new account are linked before email
        # verification. A stale or foreign case id is not worth failing account creation over.
        if req.case_id:
            _claim(req.case_id, existing)
    # New account, or an unverified duplicate signing up again: (re)send the link.
    mail.send_verification_link(existing.email, codes.issue_verification_token(existing.id))
    return SignupResponse(message="Check your email to verify your account")


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(req: VerifyEmailRequest) -> AuthResponse:
    user_id = codes.consume_verification_token(req.token)
    user = get_user_by_id(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.email_verified = True
    save_user(user)
    return AuthResponse(token=create_token(user.id), user=_public(user))


@router.post("/login", response_model=SignupResponse, status_code=202)
def login(req: LoginRequest) -> SignupResponse:
    user = get_user_by_email(req.email)
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email address before signing in")
    mail.send_login_code(user.email, codes.issue_login_code(user.id))
    return SignupResponse(message="Check your email for a login code")


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(req: VerifyOtpRequest) -> AuthResponse:
    user = get_user_by_email(req.email)
    try:
        valid = user is not None and codes.check_login_code(user.id, req.code.strip())
    except codes.LoginCodeRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid code")
    return AuthResponse(token=create_token(user.id), user=_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return _public(user)


@router.patch("/me", response_model=UserPublic)
def update_me(body: UpdateMeRequest, user: User = Depends(get_current_user)) -> UserPublic:
    """Rename the account, and/or claim the case whose intake was completed anonymously."""
    if body.name is not None:
        user.name = body.name
        save_user(user)
    if body.case_id and not _claim(body.case_id, user):
        # Unowned cases are claimable; anything else is either gone or somebody's already.
        raise HTTPException(status_code=404, detail="case not found")
    return _public(user)
