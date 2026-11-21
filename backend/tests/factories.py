"""Real records in the test database: accounts, sessions and cases."""
import uuid

from app.accounts.sessions import create_token
from app.accounts.users import User, save_user
from app.cases import store
from app.cases.models import CaseProfile


def new_user(name: str = "Caregiver") -> User:
    user = User(id=str(uuid.uuid4()), name=name, email=f"{uuid.uuid4().hex}@example.com",
                hashed_password="unused", created_at="2026-01-01T00:00:00+00:00", email_verified=True)
    save_user(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user.id)}"}


def new_case(owner: User | None = None) -> str:
    case_id = f"case-{uuid.uuid4().hex}"
    store.save_profile(CaseProfile(id=case_id))
    if owner is not None:
        assert store.claim_case(case_id, owner.id)
    return case_id
