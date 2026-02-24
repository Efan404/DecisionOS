from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from app.core.settings import get_settings
from app.db.repo_auth import AuthRepository

_auth_repo = AuthRepository()


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    role: str


def require_authenticated_user(
    x_app_token: str | None = Header(default=None),
) -> AuthenticatedUser:
    settings = get_settings()
    if settings.auth_disabled:
        return AuthenticatedUser(id="auth-disabled", username="dev", role="admin")

    if x_app_token is None:
        raise _auth_unauthorized("AUTH_UNAUTHORIZED", "Missing token")

    user = _auth_repo.get_user_by_session_token(x_app_token)
    if user is None:
        raise _auth_unauthorized("AUTH_TOKEN_INVALID", "Invalid or expired token")

    return AuthenticatedUser(id=user.id, username=user.username, role=user.role)


def _auth_unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )
