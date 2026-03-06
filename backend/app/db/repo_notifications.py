from __future__ import annotations

import json
import uuid

from app.core.time import utc_now_iso
from app.db.engine import db_session


class NotificationRecord:
    __slots__ = ("id", "user_id", "type", "title", "body", "metadata_json", "read_at", "created_at")

    def __init__(self, *, id: str, user_id: str, type: str, title: str, body: str, metadata_json: str, read_at: str | None, created_at: str):
        self.id = id
        self.user_id = user_id
        self.type = type
        self.title = title
        self.body = body
        self.metadata_json = metadata_json
        self.read_at = read_at
        self.created_at = created_at


class NotificationRepository:

    def create(
        self, *, user_id: str = "default", type: str, title: str, body: str, metadata: dict | None = None,
    ) -> NotificationRecord:
        record_id = str(uuid.uuid4())
        now = utc_now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with db_session() as conn:
            conn.execute(
                "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, user_id, type, title, body, meta_json, now),
            )
        return NotificationRecord(
            id=record_id, user_id=user_id, type=type, title=title,
            body=body, metadata_json=meta_json, read_at=None, created_at=now,
        )

    def list_unread(self, user_id: str = "default", limit: int = 20) -> list[NotificationRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, user_id, type, title, body, metadata_json, read_at, created_at FROM notification WHERE user_id = ? AND read_at IS NULL "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [NotificationRecord(id=r[0], user_id=r[1], type=r[2], title=r[3], body=r[4], metadata_json=r[5], read_at=r[6], created_at=r[7]) for r in rows]

    def list_all(self, user_id: str = "default", limit: int = 50) -> list[NotificationRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, user_id, type, title, body, metadata_json, read_at, created_at FROM notification WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [NotificationRecord(id=r[0], user_id=r[1], type=r[2], title=r[3], body=r[4], metadata_json=r[5], read_at=r[6], created_at=r[7]) for r in rows]

    def dismiss(self, notification_id: str) -> bool:
        now = utc_now_iso()
        with db_session() as conn:
            cursor = conn.execute(
                "UPDATE notification SET read_at = ? WHERE id = ? AND read_at IS NULL",
                (now, notification_id),
            )
        return cursor.rowcount > 0
