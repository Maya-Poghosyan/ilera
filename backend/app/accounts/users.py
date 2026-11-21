"""The account record, its storage, and password hashing."""

from typing import Optional

import bcrypt
from pydantic import BaseModel

from app.core import db


class User(BaseModel):
    id: str
    name: str
    email: str
    hashed_password: str
    phone: str = ""
    created_at: str = ""
    email_verified: bool


_COLUMNS = "id, name, email, hashed_password, phone, created_at, email_verified"


def _row_to_user(row) -> User:
    return User(id=row[0], name=row[1], email=row[2], hashed_password=row[3], phone=row[4],
                created_at=row[5], email_verified=row[6])


def save_user(user: User) -> None:
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
            (user.id, user.name, user.email.lower(), user.hashed_password, user.phone,
             user.created_at, user.email_verified),
        )


def get_user_by_id(user_id: str) -> Optional[User]:
    with db.connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> Optional[User]:
    with db.connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM users WHERE email = %s", (email.strip().lower(),)
        ).fetchone()
    return _row_to_user(row) if row else None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())
