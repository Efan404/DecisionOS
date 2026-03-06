# User Profile & Email Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/profile` page where users can set their email and control notification preferences, backed by a `user_preferences` DB table, a `GET/PATCH /profile` API, SMTP email delivery, and an APScheduler job that runs proactive agents every 6 hours and emails results.

**Architecture:** New `user_preferences` table (1:1 with `user_account`) stores email + notify settings. Backend adds `app/core/email.py` (smtplib, SMTP-provider-agnostic), `app/db/repo_profile.py`, and `app/routes/profile.py`. APScheduler registered in `create_app()` runs proactive agents on schedule and calls email sender. Frontend adds `app/profile/page.tsx` + `components/profile/ProfilePage.tsx`, and a "Profile" link in AppShell navbar.

**Tech Stack:** Python `smtplib` + `email.mime` (stdlib, no SDK), `apscheduler>=3.10,<4.0` (AsyncIOScheduler), Next.js 14 App Router, existing `sonner` toasts.

---

### Task 1: Add APScheduler dependency

**Files:**

- Modify: `backend/requirements.txt`

**Step 1: Add APScheduler to requirements**

Add this line to `backend/requirements.txt`:

```
apscheduler>=3.10.0,<4.0.0
```

**Step 2: Install**

Run: `cd backend && pip install -r requirements.txt`
Expected: `Successfully installed apscheduler-3.x.x`

**Step 3: Verify import**

Run: `cd backend && python -c "from apscheduler.schedulers.asyncio import AsyncIOScheduler; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add apscheduler dependency"
```

---

### Task 2: DB schema — user_preferences table

**Files:**

- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/bootstrap.py` (no code change needed — `initialize_database` already runs all `SCHEMA_STATEMENTS`)

**Step 1: Write failing test**

Create `backend/tests/test_profile_repo.py`:

```python
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.db.bootstrap import initialize_database

initialize_database()


def test_user_preferences_table_exists():
    from app.db.engine import db_session
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
        ).fetchone()
    assert row is not None, "user_preferences table should exist"
```

Run: `cd backend && python -m pytest tests/test_profile_repo.py::test_user_preferences_table_exists -v`
Expected: FAIL — `AssertionError: user_preferences table should exist`

**Step 2: Add schema statement**

In `backend/app/db/models.py`, append to the `SCHEMA_STATEMENTS` tuple (after the last `""",` before the closing `)`):

```python
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id TEXT PRIMARY KEY REFERENCES user_account(id) ON DELETE CASCADE,
        email TEXT,
        notify_enabled INTEGER NOT NULL DEFAULT 0,
        notify_types TEXT NOT NULL DEFAULT '["news_match","cross_idea_insight","pattern_learned"]',
        updated_at TEXT NOT NULL
    );
    """,
```

**Step 3: Run test**

Run: `cd backend && python -m pytest tests/test_profile_repo.py::test_user_preferences_table_exists -v`
Expected: PASS

**Step 4: Commit**

```bash
git add backend/app/db/models.py backend/tests/test_profile_repo.py
git commit -m "feat(db): add user_preferences table"
```

---

### Task 3: Profile repository

**Files:**

- Create: `backend/app/db/repo_profile.py`
- Modify: `backend/tests/test_profile_repo.py`

**Step 1: Add repo tests**

Append to `backend/tests/test_profile_repo.py`:

```python
def test_get_or_create_preferences_default():
    from app.db.repo_profile import ProfileRepository
    repo = ProfileRepository()
    # Use the seeded admin user id
    from app.db.repo_auth import AuthRepository
    auth = AuthRepository()
    user = auth.get_user_by_username("admin")
    assert user is not None
    prefs = repo.get_or_create(user.id)
    assert prefs.user_id == user.id
    assert prefs.email is None
    assert prefs.notify_enabled is False
    assert "news_match" in prefs.notify_types


def test_update_preferences():
    from app.db.repo_profile import ProfileRepository
    from app.db.repo_auth import AuthRepository
    repo = ProfileRepository()
    auth = AuthRepository()
    user = auth.get_user_by_username("admin")
    assert user is not None
    updated = repo.update(
        user_id=user.id,
        email="test@example.com",
        notify_enabled=True,
        notify_types=["news_match"],
    )
    assert updated.email == "test@example.com"
    assert updated.notify_enabled is True
    assert updated.notify_types == ["news_match"]
```

Run: `cd backend && python -m pytest tests/test_profile_repo.py -v`
Expected: 1 PASS (table test), 2 FAIL (repo not implemented)

**Step 2: Implement repository**

Create `backend/app/db/repo_profile.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass
class UserPreferences:
    user_id: str
    email: str | None
    notify_enabled: bool
    notify_types: list[str]
    updated_at: str


class ProfileRepository:

    def get_or_create(self, user_id: str) -> UserPreferences:
        with db_session() as conn:
            row = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types, updated_at "
                "FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                default_types = json.dumps(["news_match", "cross_idea_insight", "pattern_learned"])
                conn.execute(
                    "INSERT INTO user_preferences (user_id, email, notify_enabled, notify_types, updated_at) "
                    "VALUES (?, NULL, 0, ?, ?)",
                    (user_id, default_types, now),
                )
                return UserPreferences(
                    user_id=user_id,
                    email=None,
                    notify_enabled=False,
                    notify_types=["news_match", "cross_idea_insight", "pattern_learned"],
                    updated_at=now,
                )
        return self._row_to_prefs(row)

    def update(
        self,
        *,
        user_id: str,
        email: str | None = ...,  # type: ignore[assignment]
        notify_enabled: bool | None = None,
        notify_types: list[str] | None = None,
    ) -> UserPreferences:
        prefs = self.get_or_create(user_id)
        new_email = prefs.email if email is ... else email  # type: ignore[comparison-overlap]
        new_enabled = prefs.notify_enabled if notify_enabled is None else notify_enabled
        new_types = prefs.notify_types if notify_types is None else notify_types
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "UPDATE user_preferences SET email = ?, notify_enabled = ?, notify_types = ?, updated_at = ? "
                "WHERE user_id = ?",
                (new_email, 1 if new_enabled else 0, json.dumps(new_types), now, user_id),
            )
        return UserPreferences(
            user_id=user_id,
            email=new_email,
            notify_enabled=new_enabled,
            notify_types=new_types,
            updated_at=now,
        )

    def list_notifiable(self, notification_type: str) -> list[UserPreferences]:
        """Return all users with notify_enabled=1 and notification_type in their notify_types."""
        with db_session() as conn:
            rows = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types, updated_at "
                "FROM user_preferences WHERE notify_enabled = 1 AND email IS NOT NULL",
            ).fetchall()
        return [
            self._row_to_prefs(r)
            for r in rows
            if notification_type in json.loads(r[3])
        ]

    @staticmethod
    def _row_to_prefs(row: tuple) -> UserPreferences:  # type: ignore[type-arg]
        return UserPreferences(
            user_id=row[0],
            email=row[1],
            notify_enabled=bool(row[2]),
            notify_types=json.loads(row[3]),
            updated_at=row[4],
        )
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_profile_repo.py -v`
Expected: All 3 PASS

**Step 4: Commit**

```bash
git add backend/app/db/repo_profile.py backend/tests/test_profile_repo.py
git commit -m "feat(db): add ProfileRepository with get_or_create, update, list_notifiable"
```

---

### Task 4: SMTP email sender

**Files:**

- Create: `backend/app/core/email.py`
- Create: `backend/tests/test_email.py`

**Step 1: Write failing test**

Create `backend/tests/test_email.py`:

```python
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import MagicMock, patch


def test_send_skips_when_no_smtp_config(monkeypatch):
    """send_notification_email returns False and does not raise when SMTP is not configured."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    from app.core import email as email_mod
    import importlib
    importlib.reload(email_mod)
    from app.db.repo_notifications import NotificationRecord
    from app.core.time import utc_now_iso
    notif = NotificationRecord(
        id="n1", user_id="u1", type="news_match",
        title="Test", body="Body", metadata_json="{}",
        read_at=None, created_at=utc_now_iso(),
    )
    result = email_mod.send_notification_email(to="user@example.com", notification=notif)
    assert result is False


def test_send_calls_smtp_when_configured(monkeypatch):
    """send_notification_email calls smtplib.SMTP when SMTP_HOST is set."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    from app.core import email as email_mod
    import importlib
    importlib.reload(email_mod)
    from app.db.repo_notifications import NotificationRecord
    from app.core.time import utc_now_iso
    notif = NotificationRecord(
        id="n1", user_id="u1", type="news_match",
        title="Test title", body="Test body", metadata_json="{}",
        read_at=None, created_at=utc_now_iso(),
    )
    mock_smtp_instance = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", mock_smtp_cls):
        result = email_mod.send_notification_email(to="user@example.com", notification=notif)
    assert result is True
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "pass")
    mock_smtp_instance.sendmail.assert_called_once()
```

Run: `cd backend && python -m pytest tests/test_email.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

**Step 2: Implement email sender**

Create `backend/app/core/email.py`:

```python
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.db.repo_notifications import NotificationRecord

logger = logging.getLogger(__name__)

_SMTP_HOST = os.environ.get("SMTP_HOST", "")
_SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
_SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
_SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@decisionos.app")


def send_notification_email(*, to: str, notification: NotificationRecord) -> bool:
    """Send a single notification email via SMTP. Returns True on success, False otherwise.

    Configuration via env vars:
        SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM

    Compatible with any SMTP provider (Resend, Gmail, SendGrid, self-hosted).
    For Resend: SMTP_HOST=smtp.resend.com, SMTP_USERNAME=resend, SMTP_PASSWORD=<api_key>
    """
    if not _SMTP_HOST:
        logger.debug("email.send skipped — SMTP_HOST not configured")
        return False

    subject = f"[DecisionOS] {notification.title}"
    body_html = f"""
<html><body>
<h2>{notification.title}</h2>
<p>{notification.body}</p>
<hr>
<p style="color:#888;font-size:12px;">
  Notification type: {notification.type}<br>
  You can manage your notification preferences in your
  <a href="http://localhost:3000/profile">Profile settings</a>.
</p>
</body></html>
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(notification.body, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(_SMTP_USERNAME, _SMTP_PASSWORD)
            smtp.sendmail(_SMTP_FROM, to, msg.as_string())
        logger.info("email.sent to=%s notification_id=%s", to, notification.id)
        return True
    except Exception:
        logger.warning("email.send_failed to=%s notification_id=%s", to, notification.id, exc_info=True)
        return False
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_email.py -v`
Expected: Both PASS

**Step 4: Commit**

```bash
git add backend/app/core/email.py backend/tests/test_email.py
git commit -m "feat(core): add SMTP email sender, provider-agnostic via env vars"
```

---

### Task 5: Profile API route

**Files:**

- Create: `backend/app/routes/profile.py`
- Modify: `backend/app/main.py`

**Step 1: Write failing test**

Create `backend/tests/test_profile_route.py`:

```python
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _auth_header():
    resp = client.post("/auth/login", json={"username": "admin", "password": "AIHackathon20250225!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_profile():
    headers = _auth_header()
    resp = client.get("/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "username" in data
    assert "email" in data
    assert "notify_enabled" in data
    assert "notify_types" in data


def test_patch_profile_email():
    headers = _auth_header()
    resp = client.patch("/profile", json={"email": "admin@example.com"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"


def test_patch_profile_notifications():
    headers = _auth_header()
    resp = client.patch(
        "/profile",
        json={"notify_enabled": True, "notify_types": ["news_match"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["notify_enabled"] is True
    assert resp.json()["notify_types"] == ["news_match"]
```

Run: `cd backend && python -m pytest tests/test_profile_route.py -v`
Expected: All FAIL — 404 Not Found

**Step 2: Implement profile route**

Create `backend/app/routes/profile.py`:

```python
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

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


@router.patch("", response_model=ProfileOut)
def patch_profile(
    payload: ProfilePatch,
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> ProfileOut:
    # Sanitise notify_types — only allow known values
    notify_types = payload.notify_types
    if notify_types is not None:
        notify_types = [t for t in notify_types if t in VALID_NOTIFY_TYPES]

    prefs = _repo.update(
        user_id=current_user.id,
        email=payload.email if payload.email is not None else ...,  # type: ignore[arg-type]
        notify_enabled=payload.notify_enabled,
        notify_types=notify_types,
    )
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
```

**Step 3: Register router in main.py**

In `backend/app/main.py`, add the import:

```python
from app.routes.profile import router as profile_router
```

And in `create_app()`, after `app.include_router(insights_router, ...)`:

```python
    app.include_router(profile_router, dependencies=protected_dependencies)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_profile_route.py -v`
Expected: All 3 PASS

**Step 5: Commit**

```bash
git add backend/app/routes/profile.py backend/app/main.py backend/tests/test_profile_route.py
git commit -m "feat(api): add GET/PATCH /profile endpoint"
```

---

### Task 6: APScheduler — proactive agents + email dispatch

**Files:**

- Create: `backend/app/core/scheduler.py`
- Modify: `backend/app/main.py`

**Step 1: Implement scheduler module**

Create `backend/app/core/scheduler.py`:

```python
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.email import send_notification_email
from app.db.repo_notifications import NotificationRepository
from app.db.repo_profile import ProfileRepository

logger = logging.getLogger(__name__)

_notif_repo = NotificationRepository()
_profile_repo = ProfileRepository()


async def run_proactive_agents(trigger_type: str = "scheduled") -> None:
    """Run all proactive agents and email results to opted-in users.

    trigger_type: "scheduled" (APScheduler) or "event" (future event-driven trigger).
    """
    logger.info("scheduler.proactive_agents.start trigger=%s", trigger_type)

    from app.agents.memory.vector_store import get_vector_store
    from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
    from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph

    vs = get_vector_store()
    created_notifications: list = []

    # ── News monitor ─────────────────────────────────────────────────────────
    try:
        graph = build_news_monitor_graph()
        result = graph.invoke({
            "user_id": "default",
            "idea_ids": [],
            "notifications": [],
            "agent_thoughts": [],
        })
        for notif in result.get("notifications", []):
            record = _notif_repo.create(
                type="news_match",
                title=f"News: {notif.get('news_title', 'Untitled')}",
                body=notif.get("insight", "Relevant news detected."),
                metadata=notif,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.news_monitor.failed", exc_info=True)

    # ── Cross-idea analyzer ───────────────────────────────────────────────────
    try:
        all_ideas = vs._ideas.get(include=["documents", "metadatas"])
        summaries = [
            {"idea_id": id_, "summary": doc}
            for id_, doc in zip(all_ideas["ids"], all_ideas["documents"])
        ]
        graph = build_cross_idea_graph()
        result = graph.invoke({
            "user_id": "default",
            "idea_summaries": summaries,
            "insights": [],
            "agent_thoughts": [],
        })
        for insight in result.get("insights", []):
            record = _notif_repo.create(
                type="cross_idea_insight",
                title=f"Ideas '{insight.get('idea_a_id', '')}' and '{insight.get('idea_b_id', '')}' are related",
                body=insight.get("analysis", "These ideas share common themes."),
                metadata=insight,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.cross_idea.failed", exc_info=True)

    # ── User pattern learner ─────────────────────────────────────────────────
    try:
        graph = build_pattern_learner_graph()
        result = graph.invoke({
            "user_id": "default",
            "decision_history": [],
            "learned_preferences": {},
            "agent_thoughts": [],
        })
        prefs = result.get("learned_preferences", {})
        if prefs:
            record = _notif_repo.create(
                type="pattern_learned",
                title="Updated your preference profile",
                body=f"Learned patterns: {', '.join(f'{k}: {v}' for k, v in list(prefs.items())[:3])}",
                metadata={"preferences": prefs},
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.pattern_learner.failed", exc_info=True)

    logger.info("scheduler.proactive_agents.done notifications_created=%d", len(created_notifications))

    # ── Email dispatch ────────────────────────────────────────────────────────
    for record in created_notifications:
        try:
            notifiable_users = _profile_repo.list_notifiable(record.type)
            for user_prefs in notifiable_users:
                if user_prefs.email:
                    send_notification_email(to=user_prefs.email, notification=record)
        except Exception:
            logger.warning("scheduler.email_dispatch.failed notification_id=%s", record.id, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance. Does not start it."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_proactive_agents,
        trigger="interval",
        hours=6,
        id="proactive_agents",
        replace_existing=True,
        kwargs={"trigger_type": "scheduled"},
    )
    return scheduler
```

**Step 2: Register scheduler in main.py**

In `backend/app/main.py`, add import:

```python
from app.core.scheduler import create_scheduler
```

In `create_app()`, after the last `app.include_router(...)` line and before `return app`, add:

```python
    scheduler = create_scheduler()

    @app.on_event("startup")
    async def start_scheduler() -> None:
        scheduler.start()
        logger.info("scheduler.started")

    @app.on_event("shutdown")
    async def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")
```

Also add `logger = logging.getLogger(__name__)` near the top of `main.py` if not already present.

**Step 3: Verify app starts without error**

Run: `cd backend && python -c "from app.main import app; print('OK')"`
Expected: `OK` (no import errors)

**Step 4: Commit**

```bash
git add backend/app/core/scheduler.py backend/app/main.py
git commit -m "feat(scheduler): add APScheduler proactive agents job with email dispatch"
```

---

### Task 7: Frontend — API client functions

**Files:**

- Modify: `frontend/lib/api.ts`

**Step 1: Add profile API functions**

Append to `frontend/lib/api.ts`:

```typescript
// ── Profile ──────────────────────────────────────────────────────────────────

export type UserProfile = {
  username: string
  email: string | null
  notify_enabled: boolean
  notify_types: string[]
}

export type PatchProfileRequest = {
  email?: string | null
  notify_enabled?: boolean
  notify_types?: string[]
}

export const getProfile = async (): Promise<UserProfile> => {
  const response = await fetch(buildApiUrl('/profile'), {
    headers: withAuthHeaders(),
  })
  if (!response.ok)
    throw new ApiError(response.status, 'PROFILE_FETCH_FAILED', 'Failed to fetch profile')
  return response.json() as Promise<UserProfile>
}

export const patchProfile = async (payload: PatchProfileRequest): Promise<UserProfile> => {
  const response = await fetch(buildApiUrl('/profile'), {
    method: 'PATCH',
    headers: withAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (!response.ok)
    throw new ApiError(response.status, 'PROFILE_UPDATE_FAILED', 'Failed to update profile')
  return response.json() as Promise<UserProfile>
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api-client): add getProfile and patchProfile functions"
```

---

### Task 8: Frontend — ProfilePage component

**Files:**

- Create: `frontend/components/profile/ProfilePage.tsx`

**Step 1: Create component**

Create `frontend/components/profile/ProfilePage.tsx`:

```tsx
'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { ApiError, getProfile, patchProfile, type UserProfile } from '../../lib/api'

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  news_match: 'News matches',
  cross_idea_insight: 'Cross-idea insights',
  pattern_learned: 'Pattern updates',
}

const ALL_NOTIFY_TYPES = ['news_match', 'cross_idea_insight', 'pattern_learned']

export function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Account section state
  const [email, setEmail] = useState('')
  const [accountSaving, setAccountSaving] = useState(false)
  const [accountError, setAccountError] = useState<string | null>(null)

  // Notifications section state
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyTypes, setNotifyTypes] = useState<string[]>(ALL_NOTIFY_TYPES)
  const [notifSaving, setNotifSaving] = useState(false)
  const [notifError, setNotifError] = useState<string | null>(null)

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p)
        setEmail(p.email ?? '')
        setNotifyEnabled(p.notify_enabled)
        setNotifyTypes(p.notify_types)
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Failed to load profile'
        setLoadError(msg)
      })
  }, [])

  const handleSaveAccount = async () => {
    setAccountSaving(true)
    setAccountError(null)
    try {
      const updated = await patchProfile({ email: email.trim() || null })
      setProfile(updated)
      toast.success('Email saved')
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Save failed'
      setAccountError(msg)
      toast.error(msg)
    } finally {
      setAccountSaving(false)
    }
  }

  const handleSaveNotifications = async () => {
    setNotifSaving(true)
    setNotifError(null)
    try {
      const updated = await patchProfile({
        notify_enabled: notifyEnabled,
        notify_types: notifyTypes,
      })
      setProfile(updated)
      toast.success('Notification preferences saved')
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Save failed'
      setNotifError(msg)
      toast.error(msg)
    } finally {
      setNotifSaving(false)
    }
  }

  const toggleNotifyType = (type: string) => {
    setNotifyTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  if (loadError) {
    return (
      <main>
        <section className="mx-auto mt-8 max-w-2xl px-6">
          <p className="text-sm text-red-600">{loadError}</p>
        </section>
      </main>
    )
  }

  return (
    <main>
      <section className="mx-auto mt-8 w-full max-w-2xl space-y-6 px-6 pb-16">
        <h1 className="text-lg font-bold tracking-tight text-slate-900">Profile</h1>

        {/* Account section */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Account</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Username</label>
              <input
                type="text"
                value={profile?.username ?? ''}
                disabled
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-400"
              />
            </div>
            <div>
              <label htmlFor="email" className="mb-1 block text-xs font-medium text-slate-600">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-slate-400 focus:outline-none"
              />
            </div>
            {accountError ? <p className="text-xs text-red-600">{accountError}</p> : null}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveAccount}
                disabled={accountSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {accountSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>

        {/* Notifications section */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Notifications</h2>
          <div className="space-y-4">
            {/* Master toggle */}
            <label className="flex cursor-pointer items-center justify-between">
              <span className="text-sm text-slate-700">Enable email notifications</span>
              <button
                type="button"
                role="switch"
                aria-checked={notifyEnabled}
                onClick={() => setNotifyEnabled((v) => !v)}
                className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
                  notifyEnabled ? 'bg-slate-900' : 'bg-slate-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    notifyEnabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            {/* Per-type checkboxes */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-500">Notify me about:</p>
              {ALL_NOTIFY_TYPES.map((type) => (
                <label
                  key={type}
                  className={`flex cursor-pointer items-center gap-3 ${!notifyEnabled ? 'opacity-40' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={notifyTypes.includes(type)}
                    onChange={() => toggleNotifyType(type)}
                    disabled={!notifyEnabled}
                    className="h-4 w-4 rounded border-slate-300 accent-slate-900"
                  />
                  <span className="text-sm text-slate-700">{NOTIFY_TYPE_LABELS[type]}</span>
                </label>
              ))}
            </div>

            {notifError ? <p className="text-xs text-red-600">{notifError}</p> : null}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveNotifications}
                disabled={notifSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {notifSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/components/profile/ProfilePage.tsx
git commit -m "feat(ui): add ProfilePage component with account and notification sections"
```

---

### Task 9: Frontend — Profile route + navbar link

**Files:**

- Create: `frontend/app/profile/page.tsx`
- Modify: `frontend/components/layout/AppShell.tsx`

**Step 1: Create page route**

Create `frontend/app/profile/page.tsx`:

```tsx
import { ProfilePage } from '../../components/profile/ProfilePage'

export default function ProfileRoute() {
  return <ProfilePage />
}
```

**Step 2: Add Profile link in AppShell navbar**

In `frontend/components/layout/AppShell.tsx`, find the navbar right-side section (around line 303). The current code shows the username as a plain `<span>`. Replace:

```tsx
<span className="hidden text-xs text-[#1e1e1e]/40 sm:block">{authSession.username}</span>
```

With:

```tsx
<Link
  href="/profile"
  className="hidden text-xs text-[#1e1e1e]/40 transition hover:text-[#1e1e1e]/70 sm:block"
>
  {authSession.username}
</Link>
```

**Step 3: Verify app builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/app/profile/page.tsx frontend/components/layout/AppShell.tsx
git commit -m "feat(ui): add /profile route and navbar username link"
```

---

### Task 10: End-to-end smoke test

**Step 1: Start backend**

Run: `cd backend && uvicorn app.main:app --reload`
Expected: Server starts, logs `scheduler.started`

**Step 2: Start frontend**

Run: `cd frontend && npm run dev`

**Step 3: Manual verification checklist**

- [ ] Click username in navbar → navigates to `/profile`
- [ ] Profile page loads with username (read-only) and empty email
- [ ] Enter an email, click Save → toast "Email saved", field retains value on reload
- [ ] Toggle "Enable email notifications" → checkboxes become enabled
- [ ] Uncheck one notification type, click Save → toast "Notification preferences saved"
- [ ] Reload page → preferences persist correctly
- [ ] `GET /profile` via curl returns correct JSON

**Step 4: Verify env-less email gracefully skips**

With `SMTP_HOST` unset, trigger a proactive agent manually:

```bash
curl -X POST http://localhost:8000/insights/news-scan \
  -H "Authorization: Bearer <token>"
```

Expected: Returns JSON, no crash, backend logs `email.send skipped — SMTP_HOST not configured`

**Step 5: Final commit if any fixes needed**

```bash
git add -p
git commit -m "fix: profile page smoke test fixes"
```
