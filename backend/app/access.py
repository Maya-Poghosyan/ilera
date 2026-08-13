"""Case-level authorization.

Every case-scoped route takes its `case_id` from the request, so the id alone must not be
authority to read a household's data. A case is reachable if it is still unowned — intake runs
before the account exists, and its creator is the only one holding the id — or if the caller is
the account that claimed it.

Denials are 404, not 403: a 403 would confirm the case exists to someone probing ids.
"""

from typing import Optional

from fastapi import Depends, HTTPException

from . import store
from .auth import User, get_optional_user

CASE_NOT_FOUND = HTTPException(status_code=404, detail="case not found")


def authorize_case(case_id: str, user: Optional[User]) -> None:
    """Raise unless `user` may act on `case_id`. For case ids that arrive in a request body."""
    owner = store.get_case_owner(case_id)
    if owner is None or (user is not None and owner == user.id):
        return
    raise CASE_NOT_FOUND


async def require_case_access(
    case_id: str, user: Optional[User] = Depends(get_optional_user)
) -> str:
    """Dependency for routes with a `case_id` path or query parameter."""
    authorize_case(case_id, user)
    return case_id
