from __future__ import annotations

import json

from fastapi import APIRouter

from app.db.repo_notifications import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["notifications"])
_repo = NotificationRepository()


@router.get("")
def list_notifications(unread_only: bool = False):
    if unread_only:
        records = _repo.list_unread()
    else:
        records = _repo.list_all()
    return {
        "notifications": [
            {
                "id": r.id,
                "type": r.type,
                "title": r.title,
                "body": r.body,
                "metadata": json.loads(r.metadata_json),
                "read_at": r.read_at,
                "created_at": r.created_at,
            }
            for r in records
        ]
    }


@router.post("/{notification_id}/dismiss")
def dismiss_notification(notification_id: str):
    dismissed = _repo.dismiss(notification_id)
    return {"dismissed": dismissed}
