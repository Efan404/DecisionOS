from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.repo_auth import AuthRepository
from app.schemas.auth import AuthLoginRequest, AuthLoginResponse, AuthUserOut

router = APIRouter(prefix="/auth", tags=["auth"])
_repo = AuthRepository()


@router.post("/login", response_model=AuthLoginResponse)
async def login(payload: AuthLoginRequest) -> AuthLoginResponse:
    result = _repo.authenticate(username=payload.username, password=payload.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "Invalid username or password"},
        )

    return AuthLoginResponse(
        access_token=result.access_token,
        token_type="bearer",
        expires_in=result.expires_in,
        user=AuthUserOut(
            id=result.user.id,
            username=result.user.username,
            role="admin" if result.user.role == "admin" else "user",
        ),
    )


@router.get("/me", response_model=AuthUserOut)
async def get_me(current_user: AuthenticatedUser = Depends(require_authenticated_user)) -> AuthUserOut:
    return AuthUserOut(
        id=current_user.id,
        username=current_user.username,
        role="admin" if current_user.role == "admin" else "user",
    )


@router.post("/logout", status_code=204)
async def logout(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    x_app_token: str | None = Header(default=None),
) -> None:
    _ = current_user
    if x_app_token is None:
        return
    _repo.revoke_session(x_app_token)
