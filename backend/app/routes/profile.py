from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.repo_profile import ProfileRepository

router = APIRouter(prefix="/profile", tags=["profile"])
_repo = ProfileRepository()
_logger = logging.getLogger(__name__)

VALID_NOTIFY_TYPES = {"news_match", "cross_idea_insight", "pattern_learned"}


class ProfileOut(BaseModel):
    username: str
    email: str | None
    notify_enabled: bool
    notify_types: list[str]


class ProfilePatch(BaseModel):
    email: str | None = None
    notify_enabled: bool | None = None
    notify_types: list[str] | None = None


@router.get("", response_model=ProfileOut)
def get_profile(
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> ProfileOut:
    prefs = _repo.get_or_create(current_user.id)
    _logger.info("profile.get user_id=%s", current_user.id)
    return ProfileOut(
        username=current_user.username,
        email=prefs.email,
        notify_enabled=prefs.notify_enabled,
        notify_types=prefs.notify_types,
    )


_PATCH_SENTINEL = object()


@router.patch("", response_model=ProfileOut)
def patch_profile(
    payload: ProfilePatch,
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> ProfileOut:
    # Sanitise notify_types — only allow known values
    notify_types = payload.notify_types
    if notify_types is not None:
        notify_types = [t for t in notify_types if t in VALID_NOTIFY_TYPES]

    # Build kwargs — only pass email if it was explicitly set in the payload
    update_kwargs: dict = {"user_id": current_user.id}
    if payload.email is not None:
        update_kwargs["email"] = payload.email
    if payload.notify_enabled is not None:
        update_kwargs["notify_enabled"] = payload.notify_enabled
    if notify_types is not None:
        update_kwargs["notify_types"] = notify_types

    prefs = _repo.update(**update_kwargs)
    _logger.info(
        "profile.patch user_id=%s email=%s notify_enabled=%s",
        current_user.id, prefs.email, prefs.notify_enabled,
    )
    return ProfileOut(
        username=current_user.username,
        email=prefs.email,
        notify_enabled=prefs.notify_enabled,
        notify_types=prefs.notify_types,
    )
