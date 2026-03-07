# Market Intelligence Push System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-layer market intelligence system: Layer 1 pushes raw market signals (news, GitHub, web) as notifications; Layer 2 lets users trigger deep LLM-powered insight reports per idea, delivered via a new `/insights` page, clickable notifications, and email with action links.

**Architecture:** `search_gateway` (new stateless service, mirrors `ai_gateway`) wraps Exa / Tavily / HN Algolia behind a unified interface, stored in a new `search_settings` DB table. Layer 1 upgrades the existing `signal_monitor` proactive agent to use `search_gateway` and push `market_signal` notifications. Layer 2 adds a new SSE endpoint `/ideas/{id}/agents/market-insight` that runs an LLM analysis of linked signals for an idea and stores the result. A new `/insights` page surfaces both layers; `NotificationBell` notifications become clickable with `action_url`; email template gains a "View Insight" link.

**Tech Stack:** Python (stdlib `urllib.request`, `httpx` already installed), FastAPI, SQLite, LangGraph, Next.js 14 App Router, TypeScript, Tailwind CSS, Zod, APScheduler (existing)

---

## Existing Code — Critical Context

Read these files before touching anything:

| File                                                     | What it does                                                                                      |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `backend/app/core/ai_gateway.py`                         | Pattern to mirror for `search_gateway` — `_post_json`, `_get_active_provider`, retry logic        |
| `backend/app/db/repo_ai.py`                              | Pattern to mirror for `repo_search` — `get_settings`, `update_settings`, encrypt/decrypt          |
| `backend/app/routes/ai_settings.py`                      | Pattern to mirror for `routes/search_settings.py`                                                 |
| `backend/app/schemas/ai_settings.py`                     | Pattern to mirror for `schemas/search_settings.py`                                                |
| `backend/app/core/scheduler.py`                          | Where to add `market_insight_agent`; current 4 agents                                             |
| `backend/app/agents/graphs/proactive/signal_monitor.py`  | Agent to upgrade — calls `fetch_stories_for_topics`, needs `search_gateway` instead               |
| `backend/app/db/models.py`                               | All CREATE TABLE statements — add `search_settings`, `market_insight`, alter `notification` CHECK |
| `backend/app/db/repo_notifications.py`                   | `create()` method, `exists_*` dedup helpers — add `exists_market_signal`                          |
| `backend/app/core/email.py`                              | `send_notification_email()` — add optional `action_url` param                                     |
| `frontend/components/notifications/NotificationBell.tsx` | Notification UI — make title clickable if `action_url` present in metadata                        |
| `frontend/components/settings/AISettingsPage.tsx`        | UI pattern to mirror for `SearchSettingsPage`                                                     |
| `frontend/app/settings/page.tsx`                         | Currently `<AISettingsPage />` — wrap in tab switcher                                             |
| `frontend/app/layout.tsx`                                | Nav — add Insights link                                                                           |
| `frontend/lib/api.ts`                                    | API client — add search settings + market insight endpoints                                       |

---

## DB Schema Changes (read `backend/app/db/models.py` and `backend/app/db/bootstrap.py` before starting)

### New table: `search_settings`

```sql
CREATE TABLE IF NOT EXISTS search_settings (
    id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### New table: `market_insight`

```sql
CREATE TABLE IF NOT EXISTS market_insight (
    id TEXT PRIMARY KEY,
    idea_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    decision_impact TEXT NOT NULL,
    recommended_actions TEXT NOT NULL DEFAULT '[]',
    signal_count INTEGER NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_insight_idea
ON market_insight(idea_id, generated_at DESC);
```

### Alter `notification` CHECK constraint

The current CHECK is: `type IN ('news_match', 'cross_idea_insight', 'pattern_learned')`
Must expand to include `'market_signal'` and `'market_insight'`.

SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT. The migration path is to add the new types via ALTER TABLE with a trigger or simply update the CHECK via a schema migration. **Use the same guard pattern as `bootstrap.py`** — detect old constraint and recreate the table if needed (see Task 1 for exact approach).

---

## Task 1: DB schema — search_settings + market_insight + notification type expansion

**Files:**

- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/bootstrap.py`
- Test: `backend/tests/test_db_schema.py` (create if not exists)

**Step 1: Read bootstrap.py to understand the migration guard pattern**

```bash
cat backend/app/db/bootstrap.py
```

Look for `_column_exists()` and how ALTER TABLE migrations are guarded.

**Step 2: Write the failing test**

```python
# backend/tests/test_db_schema.py
import sqlite3
import pytest
from app.db.bootstrap import initialize_database
from app.db.engine import db_session

def test_search_settings_table_exists():
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_settings'"
        ).fetchone()
    assert row is not None

def test_market_insight_table_exists():
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_insight'"
        ).fetchone()
    assert row is not None

def test_notification_accepts_market_signal_type():
    initialize_database()
    with db_session() as conn:
        # Should not raise
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('test-ms', 'default', 'market_signal', 'Test', 'Body', '{}', '2026-01-01T00:00:00Z')"
        )
        conn.execute("DELETE FROM notification WHERE id='test-ms'")

def test_notification_accepts_market_insight_type():
    initialize_database()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('test-mi', 'default', 'market_insight', 'Test', 'Body', '{}', '2026-01-01T00:00:00Z')"
        )
        conn.execute("DELETE FROM notification WHERE id='test-mi'")
```

**Step 3: Run test to verify failure**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_db_schema.py -v
```

Expected: FAIL — tables don't exist, notification type check fails

**Step 4: Add new tables to models.py**

In `backend/app/db/models.py`, append to `SCHEMA_STATEMENTS` tuple (before the closing `):`):

```python
    """
    CREATE TABLE IF NOT EXISTS search_settings (
        id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS market_insight (
        id TEXT PRIMARY KEY,
        idea_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
        summary TEXT NOT NULL,
        decision_impact TEXT NOT NULL,
        recommended_actions TEXT NOT NULL DEFAULT '[]',
        signal_count INTEGER NOT NULL DEFAULT 0,
        generated_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_insight_idea
    ON market_insight(idea_id, generated_at DESC);
    """,
```

**Step 5: Expand notification type CHECK**

The `notification` table has a hardcoded CHECK constraint. SQLite cannot ALTER a CHECK — you must recreate the table. Add this migration to `models.py` SCHEMA_STATEMENTS (it runs after the original CREATE TABLE):

```python
    # Migration: expand notification type CHECK to include market_signal and market_insight.
    # SQLite cannot ALTER a CHECK constraint, so we recreate the table with the new constraint.
    # The guard in bootstrap.py runs each statement wrapped in try/except — this is safe to run
    # on fresh DBs (notification already has the right CHECK) because CREATE TABLE IF NOT EXISTS
    # won't conflict.
    """
    CREATE TABLE IF NOT EXISTS notification_v2 (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        type TEXT NOT NULL CHECK (type IN (
            'news_match', 'cross_idea_insight', 'pattern_learned',
            'market_signal', 'market_insight'
        )),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        read_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
```

Then in `bootstrap.py`, add a migration step after `_run_schema_statements()`:

```python
def _migrate_notification_types(conn: sqlite3.Connection) -> None:
    """Migrate notification table to support market_signal and market_insight types.

    SQLite cannot ALTER a CHECK constraint, so we:
    1. Check if notification_v2 exists (migration already done)
    2. If not, copy all rows from notification to notification_v2
    3. Drop old notification table
    4. Rename notification_v2 to notification
    """
    # Check if notification_v2 exists (migration pending)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='notification_v2'"
    ).fetchone()
    if row is None:
        return  # migration already done or not needed

    # Check if old notification table exists
    old_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='notification'"
    ).fetchone()
    if old_row is not None:
        # Copy existing data (only rows with compatible types)
        conn.execute(
            "INSERT OR IGNORE INTO notification_v2 "
            "SELECT * FROM notification WHERE type IN "
            "('news_match', 'cross_idea_insight', 'pattern_learned')"
        )
        conn.execute("DROP TABLE notification")

    conn.execute("ALTER TABLE notification_v2 RENAME TO notification")
```

Call `_migrate_notification_types(conn)` in `initialize_database()` after `_run_schema_statements()`.

**Step 6: Run test to verify pass**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_db_schema.py -v
```

Expected: all PASS

**Step 7: Commit**

```bash
git add backend/app/db/models.py backend/app/db/bootstrap.py backend/tests/test_db_schema.py
git commit -m "feat(db): add search_settings, market_insight tables; expand notification types"
```

---

## Task 2: search_gateway backend service + repo_search

**Files:**

- Create: `backend/app/schemas/search_settings.py`
- Create: `backend/app/db/repo_search.py`
- Create: `backend/app/core/search_gateway.py`
- Test: `backend/tests/test_search_gateway.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_search_gateway.py
import pytest
from unittest.mock import patch, MagicMock
from app.schemas.search_settings import SearchProviderConfig, SearchProviderKind
from app.core.search_gateway import search, SearchResult

def test_search_result_has_required_fields():
    r = SearchResult(title="Test", url="https://example.com", snippet="desc", source="exa")
    assert r.title == "Test"
    assert r.url == "https://example.com"

def test_search_raises_when_no_provider_configured(tmp_path, monkeypatch):
    """search() raises RuntimeError when no provider is enabled."""
    from app.db.repo_search import SearchSettingsRepository
    with patch.object(SearchSettingsRepository, 'get_settings') as mock_get:
        mock_settings = MagicMock()
        mock_settings.config.providers = []
        mock_get.return_value = mock_settings
        with pytest.raises(RuntimeError, match="No search provider"):
            search("test query")

def test_search_hn_algolia_fallback(monkeypatch):
    """hn_algolia kind uses HN Algolia client and returns SearchResult list."""
    from app.core.search_gateway import _search_hn_algolia
    from app.core.hn_client import HNStory
    fake_stories = [
        HNStory(id="1", title="AI tools for devs", url="https://example.com", points=100, created_at="2026-01-01"),
    ]
    with patch("app.core.search_gateway.search_hn_stories", return_value=fake_stories):
        results = _search_hn_algolia("AI tools", max_results=5)
    assert len(results) == 1
    assert results[0].title == "AI tools for devs"
    assert results[0].source == "hn_algolia"
```

**Step 2: Run to verify failure**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_search_gateway.py -v
```

Expected: ImportError — modules don't exist yet

**Step 3: Create schemas/search_settings.py**

```python
# backend/app/schemas/search_settings.py
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

SearchProviderKind = Literal["exa", "tavily", "hn_algolia"]


class SearchProviderConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SearchProviderKind
    api_key: str | None = None
    enabled: bool = True
    max_results: int = Field(default=5, ge=1, le=20)
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)


class SearchSettingsPayload(BaseModel):
    providers: list[SearchProviderConfig] = Field(default_factory=list)


class SearchSettingsDetail(SearchSettingsPayload):
    id: str
    created_at: str
    updated_at: str


class TestSearchProviderRequest(BaseModel):
    provider: SearchProviderConfig


class TestSearchProviderResponse(BaseModel):
    ok: bool
    latency_ms: int
    message: str
    sample_results: list[dict] = Field(default_factory=list)
```

**Step 4: Create db/repo_search.py**

Mirror `repo_ai.py` exactly, replacing AI with Search:

```python
# backend/app/db/repo_search.py
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import cast

from app.core.secret_crypto import decrypt_text, encrypt_text, is_encrypted
from app.core.settings import get_settings
from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.schemas.search_settings import SearchSettingsDetail, SearchSettingsPayload

DEFAULT_SEARCH_SETTINGS_ID = "default"


@dataclass(frozen=True)
class SearchSettingsRecord:
    id: str
    config: SearchSettingsPayload
    created_at: str
    updated_at: str


def default_search_settings_payload() -> dict[str, object]:
    return {"providers": []}


class SearchSettingsRepository:
    def get_settings(self) -> SearchSettingsRecord:
        secret_key = get_settings().secret_key
        with db_session() as connection:
            row = _select_settings_row(connection)
            if row is None:
                _insert_default_settings(connection)
                row = _select_settings_row(connection)
                assert row is not None
            return _row_to_record(row, secret_key=secret_key)

    def update_settings(self, payload: SearchSettingsPayload) -> SearchSettingsRecord:
        now = utc_now_iso()
        secret_key = get_settings().secret_key
        encrypted_payload = _encrypt_payload(payload, secret_key=secret_key)
        config_json = json.dumps(encrypted_payload, ensure_ascii=False)
        with db_session() as connection:
            connection.execute(
                "UPDATE search_settings SET config_json = ?, updated_at = ? WHERE id = ?",
                (config_json, now, DEFAULT_SEARCH_SETTINGS_ID),
            )
            row = _select_settings_row(connection)
            assert row is not None
            return _row_to_record(row, secret_key=secret_key)


def ensure_default_search_settings(connection: sqlite3.Connection) -> None:
    now = utc_now_iso()
    connection.execute(
        "INSERT INTO search_settings (id, config_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
        (DEFAULT_SEARCH_SETTINGS_ID, json.dumps(default_search_settings_payload()), now, now),
    )


def _insert_default_settings(connection: sqlite3.Connection) -> None:
    ensure_default_search_settings(connection)


def _select_settings_row(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            "SELECT * FROM search_settings WHERE id = ?", (DEFAULT_SEARCH_SETTINGS_ID,)
        ).fetchone(),
    )


def _row_to_record(row: sqlite3.Row, *, secret_key: str) -> SearchSettingsRecord:
    raw_payload = SearchSettingsPayload.model_validate(json.loads(str(row["config_json"])))
    payload = _decrypt_payload(raw_payload, secret_key=secret_key)
    return SearchSettingsRecord(
        id=str(row["id"]),
        config=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _encrypt_payload(payload: SearchSettingsPayload, *, secret_key: str) -> dict[str, object]:
    raw = payload.model_dump(mode="python")
    for provider in raw.get("providers", []):
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key and not is_encrypted(api_key):
            provider["api_key"] = encrypt_text(plaintext=api_key, secret_key=secret_key)
    return raw


def _decrypt_payload(payload: SearchSettingsPayload, *, secret_key: str) -> SearchSettingsPayload:
    raw = payload.model_dump(mode="python")
    for provider in raw.get("providers", []):
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key:
            provider["api_key"] = decrypt_text(payload=api_key, secret_key=secret_key)
    return SearchSettingsPayload.model_validate(raw)


_MASK_SENTINEL = "****"


def _mask_api_key(key: str | None) -> str | None:
    if not key:
        return key
    if len(key) <= 12:
        return _MASK_SENTINEL
    return f"{key[:4]}{_MASK_SENTINEL}{key[-4:]}"


def to_schema(record: SearchSettingsRecord) -> SearchSettingsDetail:
    masked_providers = [
        p.model_copy(update={"api_key": _mask_api_key(p.api_key)})
        for p in record.config.providers
    ]
    return SearchSettingsDetail(
        id=record.id,
        providers=masked_providers,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
```

**Step 5: Create core/search_gateway.py**

```python
# backend/app/core/search_gateway.py
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from urllib import request

from app.db.repo_search import SearchSettingsRepository
from app.schemas.search_settings import SearchProviderConfig

logger = logging.getLogger(__name__)

_settings_repo = SearchSettingsRepository()

_POST_JSON_MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str  # "exa" | "tavily" | "hn_algolia"
    published_date: str | None = None
    score: float | None = None


def _get_active_provider() -> SearchProviderConfig:
    settings = _settings_repo.get_settings().config
    enabled = [p for p in settings.providers if p.enabled]
    if not enabled:
        raise RuntimeError(
            "No search provider configured. Go to Settings → Search Provider to add one."
        )
    return enabled[0]


def search(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search using the active configured provider. Falls back to HN Algolia if none configured."""
    try:
        provider = _get_active_provider()
    except RuntimeError:
        # Graceful fallback: use HN Algolia (free, no key required)
        logger.info("search_gateway: no provider configured, falling back to HN Algolia")
        return _search_hn_algolia(query, max_results=max_results)

    logger.info("search_gateway.search provider=%s kind=%s query=%r", provider.id, provider.kind, query)
    if provider.kind == "exa":
        return _search_exa(provider, query, max_results=max_results)
    if provider.kind == "tavily":
        return _search_tavily(provider, query, max_results=max_results)
    if provider.kind == "hn_algolia":
        return _search_hn_algolia(query, max_results=max_results)
    raise RuntimeError(f"Unsupported search provider kind: {provider.kind}")


def _search_exa(provider: SearchProviderConfig, query: str, max_results: int) -> list[SearchResult]:
    """Call Exa neural search API."""
    body = {
        "query": query,
        "numResults": max_results,
        "contents": {"text": {"maxCharacters": 200}},
        "type": "neural",
    }
    try:
        data = _post_json(
            url="https://api.exa.ai/search",
            body=body,
            api_key=provider.api_key,
            timeout_seconds=provider.timeout_seconds,
            auth_header="Authorization",
            auth_prefix="Bearer ",
        )
        results = []
        for item in (data.get("results") or [])[:max_results]:
            results.append(SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str((item.get("text") or item.get("summary") or ""))[:300],
                source="exa",
                published_date=item.get("publishedDate"),
                score=item.get("score"),
            ))
        return results
    except Exception as exc:
        logger.warning("search_gateway.exa.failed query=%r exc=%s", query, exc)
        return []


def _search_tavily(provider: SearchProviderConfig, query: str, max_results: int) -> list[SearchResult]:
    """Call Tavily search API."""
    body = {
        "api_key": provider.api_key or "",
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        data = _post_json(
            url="https://api.tavily.com/search",
            body=body,
            api_key=None,  # Tavily uses body api_key, not header
            timeout_seconds=provider.timeout_seconds,
        )
        results = []
        for item in (data.get("results") or [])[:max_results]:
            results.append(SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or "")[:300],
                source="tavily",
                published_date=item.get("published_date"),
                score=item.get("score"),
            ))
        return results
    except Exception as exc:
        logger.warning("search_gateway.tavily.failed query=%r exc=%s", query, exc)
        return []


def _search_hn_algolia(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search HN via Algolia — free, no API key required."""
    from app.core.hn_client import search_hn_stories
    stories = search_hn_stories(query=query, limit=max_results)
    return [
        SearchResult(
            title=s.title,
            url=s.url or f"https://news.ycombinator.com/item?id={s.id}",
            snippet=f"HN story · {s.points} points",
            source="hn_algolia",
            published_date=s.created_at,
            score=None,
        )
        for s in stories
    ]


def test_provider_connection(provider: SearchProviderConfig) -> tuple[bool, int, str, list[dict]]:
    """Test a search provider. Returns (ok, latency_ms, message, sample_results)."""
    started = time.perf_counter()
    try:
        if provider.kind == "hn_algolia":
            results = _search_hn_algolia("AI product", max_results=2)
        elif provider.kind == "exa":
            results = _search_exa(provider, "AI product", max_results=2)
        elif provider.kind == "tavily":
            results = _search_tavily(provider, "AI product", max_results=2)
        else:
            raise RuntimeError(f"Unknown kind: {provider.kind}")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        sample = [{"title": r.title, "url": r.url} for r in results]
        return True, elapsed_ms, f"OK — {len(results)} results returned", sample
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, elapsed_ms, str(exc), []


def _post_json(
    *,
    url: str,
    body: dict[str, object],
    api_key: str | None,
    timeout_seconds: float,
    auth_header: str = "Authorization",
    auth_prefix: str = "Bearer ",
) -> dict[str, object]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers[auth_header] = f"{auth_prefix}{api_key}"
    req = request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read(_POST_JSON_MAX_RESPONSE_BYTES).decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response shape from {url}")
    return data  # type: ignore[return-value]
```

**Step 6: Run tests to verify pass**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_search_gateway.py -v
```

Expected: all PASS

**Step 7: Commit**

```bash
git add backend/app/schemas/search_settings.py backend/app/db/repo_search.py backend/app/core/search_gateway.py backend/tests/test_search_gateway.py
git commit -m "feat(search): add search_gateway, repo_search, SearchProviderConfig schemas"
```

---

## Task 3: Search Settings API routes

**Files:**

- Create: `backend/app/routes/search_settings.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_search_settings_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_search_settings_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONOS_CHROMA_PATH", "")
    monkeypatch.setenv("DECISIONOS_DB_PATH", str(tmp_path / "test.db"))
    from app.db.bootstrap import initialize_database
    initialize_database()
    return TestClient(create_app())

def test_get_search_settings_returns_empty_providers(client):
    resp = client.get("/settings/search")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)

def test_patch_search_settings_saves_provider(client):
    payload = {
        "providers": [{
            "id": "hn1",
            "name": "HN Algolia",
            "kind": "hn_algolia",
            "enabled": True,
            "max_results": 5,
            "timeout_seconds": 10.0,
        }]
    }
    resp = client.patch("/settings/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["providers"][0]["id"] == "hn1"
```

**Step 2: Run to verify failure**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_search_settings_api.py -v
```

Expected: FAIL — route not found

**Step 3: Create routes/search_settings.py**

```python
# backend/app/routes/search_settings.py
from __future__ import annotations

from fastapi import APIRouter

from app.core.search_gateway import test_provider_connection
from app.db.repo_search import SearchSettingsRepository, _MASK_SENTINEL, to_schema
from app.schemas.search_settings import (
    SearchSettingsDetail,
    SearchSettingsPayload,
    TestSearchProviderRequest,
    TestSearchProviderResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])
_repo = SearchSettingsRepository()


@router.get("/search", response_model=SearchSettingsDetail)
async def get_search_settings() -> SearchSettingsDetail:
    return to_schema(_repo.get_settings())


@router.patch("/search", response_model=SearchSettingsDetail)
async def patch_search_settings(payload: SearchSettingsPayload) -> SearchSettingsDetail:
    existing = _repo.get_settings()
    existing_keys = {p.id: p.api_key for p in existing.config.providers}
    for provider in payload.providers:
        if provider.api_key and _MASK_SENTINEL in provider.api_key:
            provider.api_key = existing_keys.get(provider.id)
    return to_schema(_repo.update_settings(payload))


@router.post("/search/test", response_model=TestSearchProviderResponse)
async def test_search_provider(payload: TestSearchProviderRequest) -> TestSearchProviderResponse:
    ok, latency_ms, message, sample_results = test_provider_connection(payload.provider)
    return TestSearchProviderResponse(
        ok=ok, latency_ms=latency_ms, message=message, sample_results=sample_results
    )
```

**Step 4: Wire into main.py**

In `backend/app/main.py`, add after the existing `ai_settings_router` import:

```python
from app.routes.search_settings import router as search_settings_router
```

And in `create_app()`, add after `app.include_router(ai_settings_router, ...)`:

```python
app.include_router(search_settings_router, dependencies=[Depends(require_authenticated_user)])
```

**Step 5: Run tests to verify pass**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/test_search_settings_api.py -v
```

Expected: all PASS

**Step 6: Commit**

```bash
git add backend/app/routes/search_settings.py backend/app/main.py backend/tests/test_search_settings_api.py
git commit -m "feat(api): add search settings CRUD and test endpoints"
```

---

## Task 4: Upgrade signal_monitor to use search_gateway + push notifications

**Files:**

- Modify: `backend/app/agents/graphs/proactive/signal_monitor.py`
- Modify: `backend/app/db/repo_notifications.py`
- Modify: `backend/app/core/scheduler.py`

**Context:** Current `signal_monitor.py` calls `fetch_stories_for_topics()` (HN only) and silently stores `MarketSignal` rows but never creates notifications. We need to:

1. Replace HN-only fetch with `search_gateway.search()` (which auto-falls-back to HN if no provider configured)
2. Add a `_push_signal_notifications` node that creates `market_signal` type notifications for high-severity signals
3. Add dedup helper to `repo_notifications.py`
4. Wire the upgraded agent into `scheduler.py` to actually create notifications (currently it's run but results are ignored)

**Step 1: Add dedup helper to repo_notifications.py**

Add this method to `NotificationRepository` class:

```python
def exists_market_signal(self, signal_id: str) -> bool:
    """Return True if a market_signal notification already exists for this signal_id."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM notification "
            "WHERE type = 'market_signal' "
            "AND json_extract(metadata_json, '$.signal_id') = ? LIMIT 1",
            (signal_id,),
        ).fetchone()
    return row is not None
```

**Step 2: Upgrade signal_monitor.py**

Replace the `_fetch_and_create_signals` node — change `fetch_stories_for_topics` to `search_gateway.search`:

```python
# At top of file, replace:
from app.core.hn_client import fetch_stories_for_topics
# With:
from app.core.search_gateway import search as search_web

# In _fetch_and_create_signals, replace the topics/stories block:
    # Build search queries from idea summaries (broader than just first 4 words)
    queries: list[str] = []
    for s in summaries[:5]:
        words = s["summary"].split()[:6]
        if words:
            queries.append(" ".join(words))
    if not queries:
        queries = ["AI startup product market"]

    # Use search_gateway (falls back to HN Algolia if no provider configured)
    from app.core.search_gateway import SearchResult
    all_results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for query in queries:
        for result in search_web(query, max_results=5):
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                all_results.append(result)
```

Then adapt the signal creation loop to use `SearchResult` fields:

```python
    for result in all_results:
        url = result.url
        title = result.title or "Untitled"

        if sig_repo.signal_exists_for_url(workspace_id, url):
            continue

        try:
            evidence = comp_repo.create_evidence_source(
                source_type="news",
                url=url,
                title=title,
                snippet=result.snippet[:200] if result.snippet else None,
                confidence=result.score,
            )
        except Exception:
            logger.warning("signal_monitor: failed evidence_source for %s", url, exc_info=True)
            continue

        # Severity from source score or snippet length as proxy
        score = result.score or 0.0
        severity = "high" if score > 0.8 else ("medium" if score > 0.5 else "low")

        try:
            signal = sig_repo.create_signal(
                workspace_id=workspace_id,
                signal_type="market_news",
                title=title,
                summary=result.snippet or title,
                severity=severity,
                evidence_source_id=evidence.id,
                payload_json={
                    "url": url,
                    "source": result.source,
                    "score": result.score,
                    "published_date": result.published_date,
                },
            )
        except Exception:
            logger.warning("signal_monitor: failed signal for %s", url, exc_info=True)
            continue

        vs.add_market_signal_chunk(
            chunk_id=f"signal-{signal.id}",
            text=f"{title}. {result.snippet or ''}. {url}",
            metadata={
                "entity_type": "market_signal_summary",
                "entity_id": signal.id,
                "workspace_id": workspace_id,
                "source_type": result.source,
                "created_at": utc_now_iso(),
                "confidence": result.score,
            },
        )

        signals_created.append({
            "signal_id": signal.id,
            "evidence_source_id": evidence.id,
            "title": title,
            "url": url,
            "signal_type": "market_news",
            "severity": severity,
        })
```

Add a new node `_push_signal_notifications` after `_link_signals_to_ideas_and_competitors`:

```python
def _push_signal_notifications(state: SignalMonitorState) -> dict:
    """Create market_signal notifications for high/medium severity signals linked to ideas."""
    from app.db.repo_notifications import NotificationRepository
    notif_repo = NotificationRepository()
    sig_repo = MarketSignalRepository()

    signals_created = state.get("signals_created", [])
    links_created = state.get("links_created", [])

    # Build set of signal_ids that were linked to at least one idea
    linked_signal_ids = {
        link["entity_id"] for link in links_created
        if link.get("entity_type") == "signal"
    }

    notifications_created = 0
    for sig_info in signals_created:
        signal_id = sig_info["signal_id"]
        severity = sig_info.get("severity", "low")

        # Only push medium/high signals that matched an idea
        if severity == "low" or signal_id not in linked_signal_ids:
            continue

        # Dedup
        if notif_repo.exists_market_signal(signal_id):
            continue

        notif_repo.create(
            type="market_signal",
            title=f"Market Signal: {sig_info['title'][:60]}",
            body=f"New {severity}-relevance market signal detected that matches your ideas.",
            metadata={
                "signal_id": signal_id,
                "url": sig_info.get("url", ""),
                "severity": severity,
                "action_url": "/insights",
            },
        )
        notifications_created += 1

    return {
        "agent_thoughts": [{
            "agent": "signal_monitor",
            "action": "pushed_notifications",
            "detail": f"Created {notifications_created} market_signal notifications",
            "timestamp": utc_now_iso(),
        }],
    }
```

Wire the new node into `build_signal_monitor_graph()`:

```python
def build_signal_monitor_graph():
    graph = StateGraph(SignalMonitorState)
    graph.add_node("load_ideas", _load_ideas)
    graph.add_node("fetch_and_create_signals", _fetch_and_create_signals)
    graph.add_node("link_signals", _link_signals_to_ideas_and_competitors)
    graph.add_node("push_notifications", _push_signal_notifications)
    graph.add_edge(START, "load_ideas")
    graph.add_edge("load_ideas", "fetch_and_create_signals")
    graph.add_edge("fetch_and_create_signals", "link_signals")
    graph.add_edge("link_signals", "push_notifications")
    graph.add_edge("push_notifications", END)
    return graph.compile()
```

**Step 3: Update scheduler.py to capture signal_monitor notifications**

In `run_proactive_agents`, replace the silent signal monitor block with:

```python
    # -- Signal monitor (market intelligence layer) ----------------------------
    try:
        from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
        graph = build_signal_monitor_graph()
        signal_result = await loop.run_in_executor(
            None,
            partial(graph.invoke, {
                "workspace_id": "default",
                "idea_summaries": [],
                "signals_created": [],
                "links_created": [],
                "agent_thoughts": [],
            }),
        )
        # signal_monitor now creates its own notifications internally via _push_signal_notifications
        # We collect them here for email dispatch
        for notif in _notif_repo.list_by_type("market_signal", limit=10):
            # Only email notifications created in last 10 minutes (fresh ones)
            from app.core.time import utc_now_iso
            import datetime
            created = datetime.datetime.fromisoformat(notif.created_at.replace("Z", "+00:00"))
            age_minutes = (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() / 60
            if age_minutes < 10 and notif not in created_notifications:
                created_notifications.append(notif)
        logger.info("scheduler.signal_monitor.done")
    except Exception:
        logger.warning("scheduler.signal_monitor.failed", exc_info=True)
```

**Step 4: Manual test**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. python -c "
from app.db.bootstrap import initialize_database
initialize_database()
from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
g = build_signal_monitor_graph()
result = g.invoke({'workspace_id': 'default', 'idea_summaries': [], 'signals_created': [], 'links_created': [], 'agent_thoughts': []})
print('signals_created:', len(result['signals_created']))
print('agent_thoughts:', [t['action'] for t in result['agent_thoughts']])
"
```

Expected: runs without error, prints signal counts

**Step 5: Commit**

```bash
git add backend/app/agents/graphs/proactive/signal_monitor.py backend/app/db/repo_notifications.py backend/app/core/scheduler.py
git commit -m "feat(proactive): upgrade signal_monitor to use search_gateway, push market_signal notifications"
```

---

## Task 5: market_insight repo + SSE endpoint

**Files:**

- Create: `backend/app/db/repo_market_insights.py`
- Create: `backend/app/routes/market_insight.py`
- Modify: `backend/app/main.py`

**Context:** Users click "Analyze" on the `/insights` page, which POSTs to `/ideas/{idea_id}/agents/market-insight`. The backend:

1. Loads idea context + linked market signals for that idea
2. Calls LLM (`generate_structured`) with a prompt asking for decision-impact analysis
3. Stores the result in `market_insight` table
4. Creates a `market_insight` notification
5. Returns SSE events: `progress`, `done`, `error`

**Step 1: Create repo_market_insights.py**

```python
# backend/app/db/repo_market_insights.py
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class MarketInsightRecord:
    id: str
    idea_id: str
    summary: str
    decision_impact: str
    recommended_actions: list[str]
    signal_count: int
    generated_at: str


class MarketInsightRepository:

    def create(
        self,
        idea_id: str,
        summary: str,
        decision_impact: str,
        recommended_actions: list[str],
        signal_count: int,
    ) -> MarketInsightRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "INSERT INTO market_insight "
                "(id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, idea_id, summary, decision_impact,
                 json.dumps(recommended_actions, ensure_ascii=False), signal_count, now),
            )
        return MarketInsightRecord(
            id=record_id, idea_id=idea_id, summary=summary,
            decision_impact=decision_impact, recommended_actions=recommended_actions,
            signal_count=signal_count, generated_at=now,
        )

    def list_for_idea(self, idea_id: str, limit: int = 10) -> list[MarketInsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at "
                "FROM market_insight WHERE idea_id = ? ORDER BY generated_at DESC LIMIT ?",
                (idea_id, limit),
            ).fetchall()
        return [
            MarketInsightRecord(
                id=str(r["id"]), idea_id=str(r["idea_id"]), summary=str(r["summary"]),
                decision_impact=str(r["decision_impact"]),
                recommended_actions=json.loads(str(r["recommended_actions"])),
                signal_count=int(r["signal_count"]), generated_at=str(r["generated_at"]),
            )
            for r in rows
        ]

    def list_all(self, limit: int = 50) -> list[MarketInsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at "
                "FROM market_insight ORDER BY generated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            MarketInsightRecord(
                id=str(r["id"]), idea_id=str(r["idea_id"]), summary=str(r["summary"]),
                decision_impact=str(r["decision_impact"]),
                recommended_actions=json.loads(str(r["recommended_actions"])),
                signal_count=int(r["signal_count"]), generated_at=str(r["generated_at"]),
            )
            for r in rows
        ]
```

**Step 2: Create routes/market_insight.py**

```python
# backend/app/routes/market_insight.py
from __future__ import annotations

import json
import logging
from functools import partial

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.ai_gateway import generate_structured
from app.db.repo_ideas import IdeaRepository
from app.db.repo_market_insights import MarketInsightRepository
from app.db.repo_market_signals import MarketSignalRepository
from app.db.repo_notifications import NotificationRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ideas", tags=["market-insight"])

_idea_repo = IdeaRepository()
_insight_repo = MarketInsightRepository()
_signal_repo = MarketSignalRepository()
_notif_repo = NotificationRepository()


class MarketInsightOutput(BaseModel):
    summary: str
    decision_impact: str
    recommended_actions: list[str]


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _generate_market_insight_stream(idea_id: str):
    yield _sse("progress", {"pct": 10, "msg": "Loading idea context..."})

    # Load idea
    idea = _idea_repo.get_idea(idea_id)
    if not idea:
        yield _sse("error", {"message": "Idea not found"})
        return

    yield _sse("progress", {"pct": 30, "msg": "Loading linked market signals..."})

    # Load linked signals for this idea
    signal_links = _signal_repo.list_signals_for_idea(idea_id)
    signals_text_parts = []
    for link in signal_links[:10]:  # cap at 10 signals
        signal = _signal_repo.get_signal(link.entity_id)
        if signal:
            signals_text_parts.append(
                f"- [{signal.signal_type}] {signal.title}: {signal.summary} (severity: {signal.severity})"
            )

    if not signals_text_parts:
        signals_text = "No market signals have been detected yet for this idea."
    else:
        signals_text = "\n".join(signals_text_parts)

    yield _sse("progress", {"pct": 50, "msg": "Analyzing market signals with AI..."})

    idea_context = getattr(idea, 'idea_seed', '') or idea.title
    prompt = f"""You are a product strategist analyzing market signals for an idea.

Idea: {idea.title}
Context: {idea_context}

Recent Market Signals:
{signals_text}

Analyze these signals and provide:
1. A summary of the current market landscape relevant to this idea
2. The decision impact: how do these signals affect this idea's direction?
3. 2-4 specific recommended actions the founder should take based on these signals

Be concise, specific, and actionable. Focus on what matters for decision-making."""

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            partial(
                generate_structured,
                task="opportunity",
                user_prompt=prompt,
                schema_model=MarketInsightOutput,
            ),
        )
    except Exception as exc:
        logger.warning("market_insight.generate_failed idea_id=%s exc=%s", idea_id, exc)
        yield _sse("error", {"message": f"AI analysis failed: {exc}"})
        return

    yield _sse("progress", {"pct": 80, "msg": "Saving insight..."})

    # Store insight
    record = _insight_repo.create(
        idea_id=idea_id,
        summary=output.summary,
        decision_impact=output.decision_impact,
        recommended_actions=output.recommended_actions,
        signal_count=len(signal_links),
    )

    # Push notification
    _notif_repo.create(
        type="market_insight",
        title=f"Market insight ready: {idea.title[:50]}",
        body=output.summary[:200],
        metadata={
            "idea_id": idea_id,
            "insight_id": record.id,
            "action_url": f"/insights?idea_id={idea_id}",
        },
    )

    yield _sse("progress", {"pct": 100, "msg": "Done"})
    yield _sse("done", {
        "insight_id": record.id,
        "summary": output.summary,
        "decision_impact": output.decision_impact,
        "recommended_actions": output.recommended_actions,
        "signal_count": record.signal_count,
        "generated_at": record.generated_at,
    })


@router.post("/{idea_id}/agents/market-insight/stream")
async def stream_market_insight(idea_id: str) -> StreamingResponse:
    return StreamingResponse(
        _generate_market_insight_stream(idea_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{idea_id}/insights")
async def list_market_insights(idea_id: str) -> dict:
    insights = _insight_repo.list_for_idea(idea_id)
    return {
        "insights": [
            {
                "id": r.id,
                "summary": r.summary,
                "decision_impact": r.decision_impact,
                "recommended_actions": r.recommended_actions,
                "signal_count": r.signal_count,
                "generated_at": r.generated_at,
            }
            for r in insights
        ]
    }
```

**Step 3: Add global insights list endpoint**

In `backend/app/routes/insights.py` (already exists — read it first), add:

```python
# Add this route to the existing insights router
from app.db.repo_market_insights import MarketInsightRepository as _InsightRepo

_mi_repo = _InsightRepo()

@router.get("/market-insights")
async def list_all_market_insights() -> dict:
    insights = _mi_repo.list_all(limit=50)
    return {
        "insights": [
            {
                "id": r.id,
                "idea_id": r.idea_id,
                "summary": r.summary,
                "decision_impact": r.decision_impact,
                "recommended_actions": r.recommended_actions,
                "signal_count": r.signal_count,
                "generated_at": r.generated_at,
            }
            for r in insights
        ]
    }
```

**Step 4: Wire into main.py**

```python
from app.routes.market_insight import router as market_insight_router
# In create_app():
app.include_router(market_insight_router, dependencies=[Depends(require_authenticated_user)])
```

**Step 5: Manual test**

```bash
# Start backend, then:
curl -X POST http://localhost:8000/ideas/<some-idea-id>/agents/market-insight/stream \
  -H "Authorization: Bearer <token>" \
  -N
```

Expected: SSE stream with progress events and final `done` event

**Step 6: Commit**

```bash
git add backend/app/db/repo_market_insights.py backend/app/routes/market_insight.py backend/app/routes/insights.py backend/app/main.py
git commit -m "feat(backend): add market_insight SSE endpoint, repo, and global list route"
```

---

## Task 6: email.py — add action_url link

**Files:**

- Modify: `backend/app/core/email.py`

**Step 1: Read current email.py** (already read — see context above)

**Step 2: Add action_url support**

Modify `send_notification_email` to accept optional `action_url`:

```python
def send_notification_email(*, to: str, notification: NotificationRecord) -> bool:
    if not _SMTP_HOST:
        logger.debug("email.send skipped — SMTP_HOST not configured")
        return False

    safe_title = html.escape(notification.title)
    safe_body = html.escape(notification.body)
    safe_type = html.escape(notification.type)

    # Extract action_url from metadata if present
    try:
        meta = json.loads(notification.metadata_json)
        action_url = meta.get("action_url", "")
    except Exception:
        action_url = ""

    subject = f"[DecisionOS] {notification.title}"

    action_button = ""
    if action_url:
        full_url = f"http://localhost:3000{action_url}"
        safe_url = html.escape(full_url)
        action_button = f"""
<p>
  <a href="{safe_url}" style="display:inline-block;background:#b9eb10;color:#1e1e1e;font-weight:bold;
     padding:10px 20px;border-radius:8px;text-decoration:none;font-family:sans-serif;">
    View Insight →
  </a>
</p>"""

    body_html = f"""
<html><body style="font-family:sans-serif;color:#1e1e1e;">
<h2 style="color:#1e1e1e;">{safe_title}</h2>
<p style="color:#444;">{safe_body}</p>
{action_button}
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
<p style="color:#888;font-size:12px;">
  Notification type: {safe_type}<br>
  Manage preferences in your
  <a href="http://localhost:3000/profile" style="color:#888;">Profile settings</a>.
</p>
</body></html>"""

    # Need json import at top of file — add if not present
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(notification.body, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    # ... rest of send logic unchanged
```

Also add `import json` at the top of `email.py` if not present.

**Step 3: Commit**

```bash
git add backend/app/core/email.py
git commit -m "feat(email): add action_url button to notification emails"
```

---

## Task 7: Frontend — API client additions

**Files:**

- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/schemas.ts` (or create search types inline)

**Step 1: Read current api.ts and schemas.ts**

```bash
cat frontend/lib/api.ts | head -100
cat frontend/lib/schemas.ts | grep -A5 "AI\|ai_settings"
```

**Step 2: Add to api.ts**

Add these functions (follow the existing pattern for `getAiSettings`, `patchAiSettings`, etc.):

```typescript
// ── Search Settings ──────────────────────────────────────────────────────────

export type SearchProviderKind = 'exa' | 'tavily' | 'hn_algolia'

export interface SearchProviderConfig {
  id: string
  name: string
  kind: SearchProviderKind
  api_key?: string | null
  enabled: boolean
  max_results: number
  timeout_seconds: number
}

export interface SearchSettingsDetail {
  id: string
  providers: SearchProviderConfig[]
  created_at: string
  updated_at: string
}

export interface TestSearchProviderResponse {
  ok: boolean
  latency_ms: number
  message: string
  sample_results: Array<{ title: string; url: string }>
}

export async function getSearchSettings(): Promise<SearchSettingsDetail> {
  return apiFetch<SearchSettingsDetail>('/settings/search')
}

export async function patchSearchSettings(payload: {
  providers: SearchProviderConfig[]
}): Promise<SearchSettingsDetail> {
  return apiFetch<SearchSettingsDetail>('/settings/search', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function testSearchProvider(payload: {
  provider: SearchProviderConfig
}): Promise<TestSearchProviderResponse> {
  return apiFetch<TestSearchProviderResponse>('/settings/search/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ── Market Insights ──────────────────────────────────────────────────────────

export interface MarketInsightRecord {
  id: string
  idea_id?: string
  summary: string
  decision_impact: string
  recommended_actions: string[]
  signal_count: number
  generated_at: string
}

export async function listMarketInsights(ideaId?: string): Promise<MarketInsightRecord[]> {
  if (ideaId) {
    const data = await apiFetch<{ insights: MarketInsightRecord[] }>(`/ideas/${ideaId}/insights`)
    return data.insights
  }
  const data = await apiFetch<{ insights: MarketInsightRecord[] }>('/insights/market-insights')
  return data.insights
}
```

**Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): add search settings and market insight API client functions"
```

---

## Task 8: Frontend — Search Provider Settings tab

**Files:**

- Create: `frontend/components/settings/SearchSettingsPage.tsx`
- Modify: `frontend/app/settings/page.tsx`

**Step 1: Create SearchSettingsPage.tsx**

Mirror `AISettingsPage.tsx` but for search providers. Simpler — fewer fields:

```tsx
'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  getSearchSettings,
  patchSearchSettings,
  testSearchProvider,
  type SearchProviderConfig,
  type SearchProviderKind,
} from '../../lib/api'

const DEFAULT_PROVIDER: SearchProviderConfig = {
  id: '',
  name: '',
  kind: 'hn_algolia',
  api_key: '',
  enabled: false,
  max_results: 5,
  timeout_seconds: 15,
}

export function SearchSettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [providers, setProviders] = useState<SearchProviderConfig[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, string>>({})
  const [testingIds, setTestingIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    void (async () => {
      try {
        const settings = await getSearchSettings()
        setProviders(settings.providers.map((p) => ({ ...p, api_key: p.api_key ?? '' })))
        setUpdatedAt(settings.updated_at)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to load search settings.')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const updateProvider = (index: number, patch: Partial<SearchProviderConfig>) => {
    setProviders((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)))
  }

  const setEnabledProvider = (index: number) => {
    setProviders((prev) => prev.map((p, i) => ({ ...p, enabled: i === index })))
  }

  const addProvider = () => {
    const suffix = providers.length + 1
    setProviders((prev) => [
      ...prev,
      { ...DEFAULT_PROVIDER, id: `search_${suffix}`, name: `Search ${suffix}` },
    ])
  }

  const removeProvider = (index: number) => {
    setProviders((prev) => prev.filter((_, i) => i !== index))
  }

  const onSave = async () => {
    const cleaned = providers.map((p) => ({
      ...p,
      id: p.id.trim(),
      name: p.name.trim(),
      api_key: p.api_key?.trim() || undefined,
    }))
    if (cleaned.some((p) => !p.id || !p.name)) {
      toast.error('Each provider must have an id and name.')
      return
    }
    setSaving(true)
    try {
      const saved = await patchSearchSettings({ providers: cleaned })
      setUpdatedAt(saved.updated_at)
      toast.success('Search settings saved.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save.')
    } finally {
      setSaving(false)
    }
  }

  const onTest = async (provider: SearchProviderConfig) => {
    const key = provider.id || '(temp)'
    setTestingIds((prev) => ({ ...prev, [key]: true }))
    setTestResults((prev) => ({ ...prev, [key]: '' }))
    try {
      const result = await testSearchProvider({
        provider: {
          ...provider,
          id: provider.id.trim(),
          name: provider.name.trim(),
          api_key: provider.api_key?.trim() || undefined,
        },
      })
      const label = result.ok ? 'OK' : 'FAILED'
      const samples = result.sample_results
        .slice(0, 2)
        .map((r) => r.title)
        .join(', ')
      setTestResults((prev) => ({
        ...prev,
        [key]: `${label} · ${result.latency_ms}ms${samples ? ` · "${samples}"` : ''}`,
      }))
      result.ok ? toast.success('Search provider reachable.') : toast.error('Provider test failed.')
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [key]: `FAILED · ${err instanceof Error ? err.message : 'Unknown error'}`,
      }))
    } finally {
      setTestingIds((prev) => ({ ...prev, [key]: false }))
    }
  }

  return (
    <section className="rounded-2xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-[#1e1e1e]">Search Provider</h2>
          <p className="mt-1 text-sm text-[#1e1e1e]/50">
            Powers market signal discovery. HN Algolia is free — no key required. Exa/Tavily give
            richer results.
          </p>
        </div>
        <span className="text-xs text-[#1e1e1e]/35">
          {updatedAt ? `Updated: ${updatedAt}` : 'Not saved yet'}
        </span>
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-[#1e1e1e]/40">Loading...</p>
      ) : (
        <>
          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-[0.15em] text-[#1e1e1e]/50">
                Providers
              </h3>
              <button
                type="button"
                onClick={addProvider}
                className="rounded-xl border border-[#1e1e1e]/15 bg-white px-3 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
              >
                Add Provider
              </button>
            </div>

            {providers.length === 0 && (
              <p className="rounded-xl border border-dashed border-[#1e1e1e]/15 p-4 text-sm text-[#1e1e1e]/40">
                No search providers. Add one or leave empty to use HN Algolia automatically.
              </p>
            )}

            <div className="space-y-3">
              {providers.map((provider, index) => {
                const isActive = provider.enabled
                const key = `${provider.id}-${index}`
                const testKey = provider.id.trim() || '(temp)'
                return (
                  <article
                    key={key}
                    className="rounded-xl border-2 p-4 transition-colors"
                    style={{
                      borderColor: isActive ? '#b9eb10' : '#1e1e1e1a',
                      background: isActive ? '#1e1e1e' : '#fff',
                    }}
                  >
                    <div className="mb-3 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className="rounded-full px-2.5 py-0.5 text-xs font-bold"
                          style={{
                            background: isActive ? '#b9eb10' : '#1e1e1e0f',
                            color: isActive ? '#1e1e1e' : '#1e1e1e66',
                          }}
                        >
                          {isActive ? 'Active' : 'Inactive'}
                        </span>
                        <span
                          className="text-sm font-medium"
                          style={{ color: isActive ? '#fff' : '#1e1e1e' }}
                        >
                          {provider.name || '(unnamed)'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {!isActive && (
                          <button
                            type="button"
                            onClick={() => setEnabledProvider(index)}
                            className="rounded-lg border border-[#b9eb10] bg-[#b9eb10]/10 px-3 py-1.5 text-xs font-medium text-[#4a7300] transition hover:bg-[#b9eb10]/20"
                          >
                            Set Active
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => void onTest(provider)}
                          disabled={Boolean(testingIds[testKey])}
                          className="rounded-lg border border-[#1e1e1e]/15 px-3 py-1.5 text-xs font-medium transition disabled:opacity-60"
                          style={{
                            background: isActive ? '#ffffff15' : '#f5f5f5',
                            color: isActive ? '#fff' : '#1e1e1e99',
                          }}
                        >
                          {testingIds[testKey] ? 'Testing...' : 'Test'}
                        </button>
                        <button
                          type="button"
                          onClick={() => removeProvider(index)}
                          className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-100"
                        >
                          Remove
                        </button>
                      </div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      {[
                        { label: 'Provider ID', key: 'id', type: 'text', value: provider.id },
                        { label: 'Display Name', key: 'name', type: 'text', value: provider.name },
                        {
                          label: 'API Key',
                          key: 'api_key',
                          type: 'password',
                          value: provider.api_key ?? '',
                        },
                        {
                          label: 'Max Results',
                          key: 'max_results',
                          type: 'number',
                          value: provider.max_results,
                        },
                        {
                          label: 'Timeout (s)',
                          key: 'timeout_seconds',
                          type: 'number',
                          value: provider.timeout_seconds,
                        },
                      ].map(({ label, key: fieldKey, type, value }) => (
                        <label key={fieldKey} className="text-sm">
                          <span
                            className="mb-1 block"
                            style={{ color: isActive ? '#fff8' : '#1e1e1e66' }}
                          >
                            {label}
                          </span>
                          <input
                            type={type}
                            value={value}
                            min={
                              fieldKey === 'max_results'
                                ? 1
                                : fieldKey === 'timeout_seconds'
                                  ? 1
                                  : undefined
                            }
                            max={
                              fieldKey === 'max_results'
                                ? 20
                                : fieldKey === 'timeout_seconds'
                                  ? 60
                                  : undefined
                            }
                            onChange={(e) =>
                              updateProvider(index, {
                                [fieldKey]:
                                  type === 'number'
                                    ? Number(e.currentTarget.value) || 5
                                    : e.currentTarget.value,
                              })
                            }
                            className="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-2"
                            style={{
                              background: isActive ? '#ffffff0f' : '#f5f5f5',
                              borderColor: isActive ? '#fff2' : '#1e1e1e18',
                              color: isActive ? '#fff' : '#1e1e1e',
                            }}
                          />
                        </label>
                      ))}
                      <label className="text-sm">
                        <span
                          className="mb-1 block"
                          style={{ color: isActive ? '#fff8' : '#1e1e1e66' }}
                        >
                          Provider Kind
                        </span>
                        <select
                          value={provider.kind}
                          onChange={(e) =>
                            updateProvider(index, {
                              kind: e.currentTarget.value as SearchProviderKind,
                            })
                          }
                          className="w-full rounded-xl border px-3 py-2 text-sm outline-none"
                          style={{
                            background: isActive ? '#ffffff0f' : '#f5f5f5',
                            borderColor: isActive ? '#fff2' : '#1e1e1e18',
                            color: isActive ? '#fff' : '#1e1e1e',
                          }}
                        >
                          <option value="hn_algolia">HN Algolia (free)</option>
                          <option value="exa">Exa</option>
                          <option value="tavily">Tavily</option>
                        </select>
                      </label>
                    </div>

                    {testResults[testKey] && (
                      <p
                        className="mt-3 text-xs"
                        style={{ color: isActive ? '#fff8' : '#1e1e1e66' }}
                      >
                        {testResults[testKey]}
                      </p>
                    )}
                  </article>
                )
              })}
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving}
              className="rounded-xl bg-[#1e1e1e] px-5 py-2.5 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:opacity-60"
            >
              {saving ? 'Saving...' : 'Save Search Settings'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
```

**Step 2: Modify frontend/app/settings/page.tsx — wrap in tab switcher**

```tsx
'use client'

import { useState } from 'react'
import { AISettingsPage } from '../../components/settings/AISettingsPage'
import { SearchSettingsPage } from '../../components/settings/SearchSettingsPage'

type SettingsTab = 'ai' | 'search'

export default function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>('ai')

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      {/* Tab bar */}
      <div className="mb-6 flex w-fit gap-1 rounded-xl border border-[#1e1e1e]/10 bg-white p-1 shadow-sm">
        {(
          [
            { key: 'ai', label: 'AI Provider' },
            { key: 'search', label: 'Search Provider' },
          ] as { key: SettingsTab; label: string }[]
        ).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={[
              'rounded-lg px-4 py-2 text-sm font-medium transition',
              tab === key
                ? 'bg-[#1e1e1e] text-[#b9eb10]'
                : 'text-[#1e1e1e]/60 hover:text-[#1e1e1e]',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'ai' ? <AISettingsPage /> : <SearchSettingsPage />}
    </main>
  )
}
```

Note: `AISettingsPage` currently renders its own `<main>` wrapper — you'll need to strip the outer `<main>` from `AISettingsPage` so it renders as a section inside this page's `<main>`. Change `AISettingsPage` to return `<section ...>` instead of `<main ...>`.

**Step 3: Commit**

```bash
git add frontend/components/settings/SearchSettingsPage.tsx frontend/app/settings/page.tsx frontend/components/settings/AISettingsPage.tsx
git commit -m "feat(frontend): add Search Provider settings tab alongside AI Provider"
```

---

## Task 9: Frontend — /insights page

**Files:**

- Create: `frontend/app/insights/page.tsx`
- Create: `frontend/components/insights/InsightsPage.tsx`
- Modify: `frontend/components/layout/AppShell.tsx` (add nav link)

**Step 1: Read AppShell.tsx to understand nav link pattern**

```bash
cat frontend/components/layout/AppShell.tsx | grep -A5 "href\|nav\|Link"
```

**Step 2: Create InsightsPage.tsx**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import { listMarketInsights, type MarketInsightRecord } from '../../lib/api'
import { useIdeasStore } from '../../lib/ideas-store'
import { streamPost } from '../../lib/sse'

export function InsightsPage() {
  const ideas = useIdeasStore((s) => s.ideas)
  const [insights, setInsights] = useState<MarketInsightRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState<string | null>(null) // idea_id being analyzed
  const [selectedIdeaId, setSelectedIdeaId] = useState<string | null>(null)
  const searchParams = useSearchParams()

  const focusIdeaId = searchParams.get('idea_id')

  useEffect(() => {
    if (focusIdeaId) setSelectedIdeaId(focusIdeaId)
  }, [focusIdeaId])

  const loadInsights = async (ideaId?: string) => {
    try {
      const data = await listMarketInsights(ideaId ?? selectedIdeaId ?? undefined)
      setInsights(data)
    } catch (err) {
      toast.error('Failed to load insights.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadInsights()
  }, [selectedIdeaId])

  const handleAnalyze = async (ideaId: string) => {
    if (analyzing) return
    setAnalyzing(ideaId)
    try {
      await streamPost(
        `/ideas/${ideaId}/agents/market-insight/stream`,
        {},
        {
          onDone: () => void loadInsights(ideaId),
        }
      )
      toast.success('Market insight generated.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Analysis failed.')
    } finally {
      setAnalyzing(null)
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#1e1e1e]">Market Insights</h1>
          <p className="mt-0.5 text-sm text-[#1e1e1e]/50">
            AI-powered analysis of market signals for your ideas.
          </p>
        </div>
      </div>

      {/* Idea selector */}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setSelectedIdeaId(null)
            void loadInsights(undefined)
          }}
          className={[
            'rounded-lg border px-3 py-1.5 text-xs font-medium transition',
            !selectedIdeaId
              ? 'border-[#b9eb10] bg-[#1e1e1e] text-[#b9eb10]'
              : 'border-[#1e1e1e]/15 bg-white text-[#1e1e1e]/60 hover:border-[#1e1e1e]/30',
          ].join(' ')}
        >
          All Ideas
        </button>
        {ideas.map((idea) => (
          <button
            key={idea.id}
            type="button"
            onClick={() => setSelectedIdeaId(idea.id)}
            className={[
              'rounded-lg border px-3 py-1.5 text-xs font-medium transition',
              selectedIdeaId === idea.id
                ? 'border-[#b9eb10] bg-[#1e1e1e] text-[#b9eb10]'
                : 'border-[#1e1e1e]/15 bg-white text-[#1e1e1e]/60 hover:border-[#1e1e1e]/30',
            ].join(' ')}
          >
            {idea.title}
          </button>
        ))}
      </div>

      {/* Analyze button (only when idea selected) */}
      {selectedIdeaId && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => void handleAnalyze(selectedIdeaId)}
            disabled={!!analyzing}
            className="rounded-xl bg-[#1e1e1e] px-4 py-2 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:opacity-50"
          >
            {analyzing === selectedIdeaId ? 'Analyzing...' : 'Analyze Market Signals'}
          </button>
        </div>
      )}

      {/* Insights list */}
      <div className="mt-6 space-y-4">
        {loading ? (
          <p className="text-sm text-[#1e1e1e]/40">Loading insights...</p>
        ) : insights.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#1e1e1e]/15 p-10 text-center">
            <p className="text-sm text-[#1e1e1e]/40">
              {selectedIdeaId
                ? 'No insights yet. Click "Analyze Market Signals" to generate one.'
                : 'No insights yet. Select an idea and run an analysis.'}
            </p>
          </div>
        ) : (
          insights.map((insight) => {
            const idea = ideas.find((i) => i.id === insight.idea_id)
            return (
              <article
                key={insight.id}
                className="rounded-xl border border-[#1e1e1e]/10 bg-white p-5 shadow-sm"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    {idea && (
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#1e1e1e]/40">
                        {idea.title}
                      </p>
                    )}
                    <p className="text-sm leading-relaxed text-[#1e1e1e]/80">{insight.summary}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="rounded-md bg-[#b9eb10]/20 px-2 py-0.5 text-[11px] font-medium text-[#4a7300]">
                      {insight.signal_count} signals
                    </span>
                    <span className="text-[11px] text-[#1e1e1e]/30">
                      {insight.generated_at.slice(0, 10)}
                    </span>
                  </div>
                </div>

                <div className="border-[#1e1e1e]/8 mt-3 rounded-lg border bg-[#f5f5f5] p-3">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-[#1e1e1e]/40">
                    Decision Impact
                  </p>
                  <p className="text-sm text-[#1e1e1e]/70">{insight.decision_impact}</p>
                </div>

                {insight.recommended_actions.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#1e1e1e]/40">
                      Recommended Actions
                    </p>
                    <ul className="space-y-1">
                      {insight.recommended_actions.map((action, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-[#1e1e1e]/70">
                          <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[#b9eb10] text-[9px] font-bold text-[#1e1e1e]">
                            {i + 1}
                          </span>
                          {action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </article>
            )
          })
        )}
      </div>
    </main>
  )
}
```

**Step 3: Create app/insights/page.tsx**

```tsx
import { InsightsPage } from '../../components/insights/InsightsPage'

export default function Page() {
  return <InsightsPage />
}
```

**Step 4: Add Insights nav link to AppShell**

Read `frontend/components/layout/AppShell.tsx` first, then add a nav link for `/insights` following the same pattern as existing nav links (Settings, Profile, etc.).

**Step 5: Commit**

```bash
git add frontend/app/insights/page.tsx frontend/components/insights/InsightsPage.tsx frontend/components/layout/AppShell.tsx
git commit -m "feat(frontend): add /insights page for market intelligence reports"
```

---

## Task 10: Frontend — clickable notifications

**Files:**

- Modify: `frontend/components/notifications/NotificationBell.tsx`

**Context:** Currently notifications are plain text with only a dismiss button. When `notification.metadata.action_url` is present, the title should become a clickable link that navigates to that URL and dismisses the notification.

**Step 1: Read current NotificationBell.tsx** (already read — see context above)

**Step 2: Modify the notification list item**

The metadata is returned as `metadata_json` from the API but the frontend `Notification` type has it as `metadata`. Check `frontend/lib/api.ts` for the exact field name.

Replace the static notification item with:

```tsx
notifications.map((n) => {
  const isDismissing = dismissingIds.has(n.id)
  // Parse action_url from metadata
  let actionUrl: string | null = null
  try {
    const meta = typeof n.metadata === 'string' ? JSON.parse(n.metadata) : (n.metadata ?? {})
    if (typeof meta.action_url === 'string' && meta.action_url) {
      actionUrl = meta.action_url
    }
  } catch {
    // ignore
  }

  return (
    <li
      key={n.id}
      className={`flex items-start gap-3 px-4 py-3 transition-opacity ${isDismissing ? 'opacity-50' : ''}`}
    >
      <div className="min-w-0 flex-1">
        {actionUrl ? (
          <a
            href={actionUrl}
            onClick={() => void handleDismiss(n.id)}
            className="text-xs font-medium leading-snug text-[#1e1e1e] transition-colors hover:text-[#b9eb10] hover:underline"
          >
            {n.title}
          </a>
        ) : (
          <p className="text-xs font-medium leading-snug text-[#1e1e1e]">{n.title}</p>
        )}
        <p className="mt-0.5 text-[11px] leading-snug text-[#1e1e1e]/50">{n.body}</p>
      </div>
      <button
        type="button"
        onClick={() => void handleDismiss(n.id)}
        disabled={isDismissing}
        aria-label="Dismiss notification"
        className="mt-0.5 shrink-0 text-[#1e1e1e]/30 transition hover:text-[#1e1e1e]/60 disabled:opacity-40"
      >
        <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
          <path
            d="M2 2l8 8M10 2L2 10"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </li>
  )
})
```

**Step 3: Verify the `Notification` type has metadata**

Check `frontend/lib/api.ts` for the `Notification` interface. It should have a `metadata` field. If it's typed as `Record<string, unknown>` or `object`, the `JSON.parse` fallback in the code above handles it safely.

**Step 4: Commit**

```bash
git add frontend/components/notifications/NotificationBell.tsx
git commit -m "feat(frontend): make notifications clickable when action_url is present"
```

---

## Task 11: Cleanup — remove CompetitorCard UI components

**Files:**

- Modify: `frontend/components/feasibility/FeasibilityPage.tsx` (already done in this session)
- Delete: `frontend/components/evidence/MarketEvidencePanel.tsx`
- Delete: `frontend/components/evidence/CompetitorCardList.tsx`
- Modify: `frontend/components/prd/PrdPage.tsx` (remove any MarketEvidencePanel import)
- Check: `frontend/components/evidence/__tests__/evidence-components.test.tsx`

**Step 1: Check for remaining usages**

```bash
grep -r "MarketEvidencePanel\|CompetitorCardList\|CompetitorCard" frontend/ --include="*.tsx" --include="*.ts" -l
```

**Step 2: Remove from PrdPage.tsx if present**

```bash
cat frontend/components/prd/PrdPage.tsx | grep -n "MarketEvidence\|CompetitorCard"
```

If found, remove the import and usage. Do NOT remove the whole file.

**Step 3: Delete the evidence component files**

```bash
rm frontend/components/evidence/MarketEvidencePanel.tsx
rm frontend/components/evidence/CompetitorCardList.tsx
```

**Step 4: Handle test file**

```bash
cat frontend/components/evidence/__tests__/evidence-components.test.tsx
```

If it only tests the deleted components, delete the test file too:

```bash
rm frontend/components/evidence/__tests__/evidence-components.test.tsx
```

If it tests other things, edit to remove only the deleted component tests.

**Step 5: Run frontend lint/type check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Fix any import errors from the deletions.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat(cleanup): remove CompetitorCard UI — market intelligence is now push-only via /insights"
```

---

## Testing the Full Flow

After all tasks:

**1. Backend unit tests:**

```bash
cd backend && DECISIONOS_CHROMA_PATH="" PYTHONPATH=. pytest tests/ -v --ignore=tests/test_auth_api.py --ignore=tests/test_auth_repo.py
```

**2. Start services:**

```bash
# Terminal 1:
cd backend && uvicorn app.main:app --reload --port 8000
# Terminal 2:
cd frontend && npm run dev
```

**3. Settings tab check:**

- Navigate to `/settings` → should see "AI Provider" and "Search Provider" tabs
- Click Search Provider → add an HN Algolia provider → click Test → should return 2 sample results

**4. Market signal flow:**

```bash
# Manually trigger the proactive agents:
curl -X POST http://localhost:8000/insights/trigger -H "Authorization: Bearer <token>"
```

Check `/insights` page — should see market signal notifications in bell icon

**5. Market insight flow:**

- On `/insights` page, select an idea → click "Analyze Market Signals"
- Should see SSE progress → insight card appears
- Bell icon should show new `market_insight` notification with clickable title

**6. Email (optional, requires SMTP config):**

- Set SMTP env vars
- Trigger proactive agents
- Check email inbox — notification emails should have "View Insight →" button

---

## Known Constraints

- **Pre-existing failing tests**: `test_auth_api.py::test_login_success_returns_access_token` and `test_auth_repo.py::test_authenticate_persists_utc_millis_timestamps_for_session` — these fail independently of our changes, do not fix them.
- **notification CHECK migration**: The table recreation in Task 1 must run inside a transaction. Use `conn.execute("BEGIN")` / `conn.commit()` if not already in the bootstrap transaction context.
- **`streamPost` in InsightsPage**: The existing `streamPost` utility in `frontend/lib/sse.ts` accepts `onDone` — verify its signature before calling in Task 9 to ensure compatibility.
- **HN Algolia free tier**: No rate limiting worries for low-volume usage, but avoid calling with more than 10 queries per scheduler run.
