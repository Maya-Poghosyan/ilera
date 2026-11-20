"""Single-use secrets sent by email: signup verification links and 6-digit login codes."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core import db

VERIFICATION_TTL = timedelta(hours=1)
LOGIN_CODE_TTL = timedelta(minutes=10)
MAX_LOGIN_CODE_ATTEMPTS = 5


class LoginCodeRejected(Exception):
    """The login code can no longer be used; the message is safe to show the caller."""


def issue_verification_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO verification_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, datetime.now(timezone.utc) + VERIFICATION_TTL),
        )
    return token


def consume_verification_token(token: str) -> Optional[str]:
    """The token's user id, marking it used; None if unknown, used or expired."""
    with db.connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM verification_tokens WHERE token = %s AND used = false AND expires_at > %s",
            (token, datetime.now(timezone.utc)),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE verification_tokens SET used = true WHERE token = %s", (token,))
    return row[0]


def issue_login_code(user_id: str) -> str:
    code = f"{secrets.randbelow(1000000):06d}"
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO login_otps (id, user_id, code, expires_at) VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), user_id, code, datetime.now(timezone.utc) + LOGIN_CODE_TTL),
        )
    return code


def check_login_code(user_id: str, code: str) -> bool:
    """True and consumed when the code matches; False (counting the attempt) when it doesn't.
    Raises LoginCodeRejected when no live code exists or it has had too many attempts."""
    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT id, code, attempts FROM login_otps
            WHERE user_id = %s AND used = false AND expires_at > %s
            ORDER BY expires_at DESC LIMIT 1
            """,
            (user_id, datetime.now(timezone.utc)),
        ).fetchone()
        if row is None:
            raise LoginCodeRejected("Code expired. Please sign in again.")
        otp_id, stored_code, attempts = row
        if attempts >= MAX_LOGIN_CODE_ATTEMPTS:
            raise LoginCodeRejected("Too many attempts. Please sign in again.")
        if stored_code != code:
            conn.execute("UPDATE login_otps SET attempts = attempts + 1 WHERE id = %s", (otp_id,))
            return False
        conn.execute("UPDATE login_otps SET used = true WHERE id = %s", (otp_id,))
    return True
