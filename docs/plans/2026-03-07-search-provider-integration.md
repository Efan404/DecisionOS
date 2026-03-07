# Search Provider Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a pluggable search provider layer (Exa / Tavily / HN Algolia) with Settings UI tab, mirroring the existing AI Provider architecture, and wire it into feasibility competitor discovery and news monitoring.

**Architecture:** A `search_gateway` service (mirrors `ai_gateway`) dispatches web search queries to the active configured provider. Search settings are stored in a new `search_settings` DB table (same encrypted JSON pattern as `ai_settings`). The frontend gains a "Search Provider" tab in `/settings` alongside the existing "AI Provider" tab.

**Tech Stack:** Python (httpx, pydantic, sqlite3), FastAPI, Next.js 14 App Router, Zod, Tailwind CSS

---

## Background & Context

### First-Principles Analysis

The core problem: competitor analysis in feasibility plans is LLM-generated from training data — potentially stale or hallucinated. The fix: inject real-time web search results into the feasibility prompt context.

**Why NOT a standalone Research Agent:**
- Search is a tool/means, not a user-facing workflow step
- Results only have value when fused with specific analysis (competitor evaluation, market sizing)
- An independent agent would require its own scheduling, state, UI trigger — YAGNI
- The `ai_gateway` pattern (stateless service, called inline by nodes) is already proven in this codebase

**Correct pattern:** `search_gateway` as a stateless service, called inside `_plan_generator_node` in `feasibility_subgraph.py` and `_fetch_news` in `news_monitor.py`.

### Architecture Diagram

```
Settings UI
  └─ /settings page (tabbed: AI Provider | Search Provider)
       └─ SearchSettingsPage component
            ↕ GET/PATCH /settings/search
            ↕ POST /settings/search/test

SQLite search_settings table
  └─ config_json: SearchSettingsPayload (encrypted api_key)
  └─ repo_search.py: SearchSettingsRepository (same pattern as repo_ai.py)

search_gateway.py
  └─ get_active_search_provider() → SearchProviderConfig
  └─ search(query, max_results) → list[SearchResult]
       ├─ kind="exa"       → _search_exa()    (httpx POST to exa.ai)
       ├─ kind="tavily"    → _search_tavily() (httpx POST to tavily.ai)
       └─ kind="hn_algolia"→ _search_hn()     (existing hn_client.py)

Callers:
  feasibility_subgraph.py  → search competitor names before plan generation
  news_monitor.py          → search news via active provider instead of HN hardcode
```

### Key Files to Touch

| File | Action | Notes |
|------|--------|-------|
| `backend/app/db/models.py` | Modify | Add `search_settings` table CREATE statement |
| `backend/app/schemas/search_settings.py` | Create | SearchProviderConfig, SearchSettingsPayload, etc. |
| `backend/app/db/repo_search.py` | Create | Mirror of repo_ai.py |
| `backend/app/core/search_gateway.py` | Create | Mirror of ai_gateway.py but for search |
| `backend/app/routes/search_settings.py` | Create | Mirror of routes/ai_settings.py |
| `backend/app/main.py` | Modify | Register search_settings router |
| `backend/app/agents/graphs/feasibility_subgraph.py` | Modify | Inject search results into plan prompt |
| `backend/app/agents/graphs/proactive/news_monitor.py` | Modify | Use search_gateway instead of hardcoded HN |
| `frontend/lib/schemas.ts` | Modify | Add SearchProviderConfig, SearchSettings types |
| `frontend/lib/api.ts` | Modify | Add getSearchSettings, patchSearchSettings, testSearchProvider |
| `frontend/components/settings/SearchSettingsPage.tsx` | Create | Mirror of AISettingsPage.tsx |
| `frontend/app/settings/page.tsx` | Modify | Add tab switcher: AI Provider | Search Provider |

---

## Task 1: Backend Schema & DB Table

**Files:**
- Create: `backend/app/schemas/search_settings.py`
- Modify: `backend/app/db/models.py`

**Step 1: Create the Pydantic schema**

```python
# backend/app/schemas/search_settings.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator

SearchProviderKind = Literal["exa", "tavily", "hn_algolia"]


class SearchProviderConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SearchProviderKind
    api_key: str | None = None
    enabled: bool = True
    max_results: int = Field(default=10, ge=1, le=50)


class SearchSettingsPayload(BaseModel):
    providers: list[SearchProviderConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_providers(self) -> SearchSettingsPayload:
        ids = [p.id for p in self.providers]
        if len(ids) != len(set(ids)):
            raise ValueError("Provider IDs must be unique")
        enabled_count = sum(1 for p in self.providers if p.enabled)
        if enabled_count > 1:
            raise ValueError("At most one search provider may be enabled at a time")
        return self


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
    sample_results: int  # number of results returned in test query
```

**Step 2: Add DB table to models.py**

In `backend/app/db/models.py`, append to `SCHEMA_STATEMENTS`:

```python
"""
CREATE TABLE IF NOT EXISTS search_settings (
    id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""",
```

**Step 3: Run tests to confirm schema parses**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
DECISIONOS_CHROMA_PATH="" PYTHONPATH=backend uv run --python backend/.venv/bin/python python -c "from app.schemas.search_settings import SearchSettingsPayload; print('OK')"
```
Expected: `OK`

**Step 4: Commit**
```bash
git add backend/app/schemas/search_settings.py backend/app/db/models.py
git commit -m "feat(search): add search_settings schema and DB table"
```

---

## Task 2: Backend Repository & search_gateway

**Files:**
- Create: `backend/app/db/repo_search.py`
- Create: `backend/app/core/search_gateway.py`

**Step 1: Create repo_search.py (mirror of repo_ai.py)**

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
_MASK_SENTINEL = "****"


@dataclass(frozen=True)
class SearchSettingsRecord:
    id: str
    config: SearchSettingsPayload
    created_at: str
    updated_at: str


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
        """
        INSERT INTO search_settings (id, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (DEFAULT_SEARCH_SETTINGS_ID, json.dumps({"providers": []}, ensure_ascii=False), now, now),
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
    for provider in raw.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key and not is_encrypted(api_key):
            provider["api_key"] = encrypt_text(plaintext=api_key, secret_key=secret_key)
    return raw


def _decrypt_payload(payload: SearchSettingsPayload, *, secret_key: str) -> SearchSettingsPayload:
    raw = payload.model_dump(mode="python")
    for provider in raw.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key:
            provider["api_key"] = decrypt_text(payload=api_key, secret_key=secret_key)
    return SearchSettingsPayload.model_validate(raw)


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

**Step 2: Create search_gateway.py**

```python
# backend/app/core/search_gateway.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.db.repo_search import SearchSettingsRepository
from app.schemas.search_settings import SearchProviderConfig

logger = logging.getLogger(__name__)
_settings_repo = SearchSettingsRepository()
_DEFAULT_TIMEOUT = 15.0


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float | None = None
    published_at: str | None = None


def get_active_search_provider() -> SearchProviderConfig | None:
    """Return the enabled search provider, or None if none configured."""
    settings = _settings_repo.get_settings().config
    enabled = [p for p in settings.providers if p.enabled]
    return enabled[0] if enabled else None


def search(query: str, *, max_results: int = 10) -> list[SearchResult]:
    """Search using the active provider. Falls back to HN Algolia if none configured."""
    provider = get_active_search_provider()
    if provider is None:
        logger.info("search: no provider configured, falling back to HN Algolia")
        return _search_hn(query, max_results=max_results)

    logger.info("search: query=%r provider=%s kind=%s", query, provider.id, provider.kind)
    try:
        if provider.kind == "exa":
            return _search_exa(query, api_key=provider.api_key, max_results=max_results)
        elif provider.kind == "tavily":
            return _search_tavily(query, api_key=provider.api_key, max_results=max_results)
        else:  # hn_algolia
            return _search_hn(query, max_results=max_results)
    except Exception as exc:
        logger.warning("search: provider=%s FAILED: %s — falling back to HN", provider.id, exc)
        return _search_hn(query, max_results=max_results)


def test_search_provider(provider: SearchProviderConfig) -> tuple[bool, int, str, int]:
    """Test a search provider. Returns (ok, latency_ms, message, sample_results_count)."""
    started = time.perf_counter()
    try:
        if provider.kind == "exa":
            results = _search_exa("AI product management tool", api_key=provider.api_key, max_results=3)
        elif provider.kind == "tavily":
            results = _search_tavily("AI product management tool", api_key=provider.api_key, max_results=3)
        else:
            results = _search_hn("AI product", max_results=3)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return True, elapsed_ms, f"Connection successful, got {len(results)} results", len(results)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, elapsed_ms, str(exc), 0


def _search_exa(query: str, *, api_key: str | None, max_results: int) -> list[SearchResult]:
    """Search via Exa neural search API."""
    if not api_key:
        raise ValueError("Exa requires an API key")
    resp = httpx.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "query": query,
            "numResults": max_results,
            "useAutoprompt": True,
            "type": "neural",
            "contents": {"text": {"maxCharacters": 500}},
        },
        timeout=_DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", []):
        results.append(SearchResult(
            title=item.get("title") or "",
            url=item.get("url") or "",
            snippet=(item.get("text") or item.get("summary") or "")[:500],
            score=item.get("score"),
            published_at=item.get("publishedDate"),
        ))
    return results


def _search_tavily(query: str, *, api_key: str | None, max_results: int) -> list[SearchResult]:
    """Search via Tavily search API."""
    if not api_key:
        raise ValueError("Tavily requires an API key")
    resp = httpx.post(
        "https://api.tavily.com/search",
        headers={"Content-Type": "application/json"},
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        },
        timeout=_DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", []):
        results.append(SearchResult(
            title=item.get("title") or "",
            url=item.get("url") or "",
            snippet=(item.get("content") or "")[:500],
            score=item.get("score"),
            published_at=item.get("published_date"),
        ))
    return results


def _search_hn(query: str, *, max_results: int) -> list[SearchResult]:
    """Fallback: search HN via Algolia (no API key required)."""
    from app.core.hn_client import search_hn_stories
    stories = search_hn_stories(query, limit=max_results)
    return [
        SearchResult(
            title=s.title,
            url=s.url or f"https://news.ycombinator.com/item?id={s.id}",
            snippet=f"HN story with {s.points} points",
            published_at=s.created_at,
        )
        for s in stories
    ]
```

**Step 3: Commit**
```bash
git add backend/app/db/repo_search.py backend/app/core/search_gateway.py
git commit -m "feat(search): add search repository and search_gateway service"
```

---

## Task 3: Backend Routes & DB Bootstrap

**Files:**
- Create: `backend/app/routes/search_settings.py`
- Modify: `backend/app/main.py` (register router)
- Modify: `backend/app/db/bootstrap.py` (call ensure_default_search_settings)

**Step 1: Create routes/search_settings.py**

```python
# backend/app/routes/search_settings.py
from __future__ import annotations

from fastapi import APIRouter

from app.core.search_gateway import test_search_provider
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
async def test_search_provider_endpoint(payload: TestSearchProviderRequest) -> TestSearchProviderResponse:
    ok, latency_ms, message, sample_results = test_search_provider(payload.provider)
    return TestSearchProviderResponse(ok=ok, latency_ms=latency_ms, message=message, sample_results=sample_results)
```

**Step 2: Register router in main.py**

Find the section where `ai_settings.router` is included and add:
```python
from app.routes.search_settings import router as search_settings_router
app.include_router(search_settings_router)
```

**Step 3: Bootstrap default search settings**

In `backend/app/db/bootstrap.py`, find where `ensure_default_ai_settings` is called and add alongside it:
```python
from app.db.repo_search import ensure_default_search_settings
ensure_default_search_settings(connection)
```

**Step 4: Verify routes load**
```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
DECISIONOS_CHROMA_PATH="" PYTHONPATH=backend uv run --python backend/.venv/bin/python python -c \
  "from app.routes.search_settings import router; print([r.path for r in router.routes])"
```
Expected: `['/settings/search', '/settings/search', '/settings/search/test']`

**Step 5: Commit**
```bash
git add backend/app/routes/search_settings.py backend/app/main.py backend/app/db/bootstrap.py
git commit -m "feat(search): add search settings API routes and bootstrap"
```

---

## Task 4: Wire search_gateway into Feasibility & News Monitor

**Files:**
- Modify: `backend/app/agents/graphs/feasibility_subgraph.py`
- Modify: `backend/app/agents/graphs/proactive/news_monitor.py`

**Step 1: Inject competitor search into feasibility plan generator**

In `_plan_generator_node` in `feasibility_subgraph.py`, before the `ai_gateway.generate_structured` call for each archetype, add a search step:

```python
from app.core.search_gateway import search as web_search

# Inside the for loop, before the ai_gateway call:
# Search for real competitors
search_query = f"{idea_seed} competitor alternative product"
search_results = web_search(search_query, max_results=5)
if search_results:
    competitor_context = "\n".join(
        f"- {r.title}: {r.url} — {r.snippet[:200]}"
        for r in search_results[:5]
    )
    prompt += f"\n\n## Real Competitor Evidence (from web search)\nUse these real products as competitors in your analysis:\n{competitor_context}"

thoughts.append({
    "agent": "plan_generator",
    "action": f"searched_competitors_plan_{i+1}",
    "detail": f"Found {len(search_results)} competitor results from web search",
    "timestamp": utc_now_iso(),
})
```

**Step 2: Update news monitor to use search_gateway**

In `news_monitor.py`, replace the `fetch_stories_for_topics` call in `_fetch_news` with:

```python
from app.core.search_gateway import search as web_search

# Replace the existing stories = fetch_stories_for_topics(...) block with:
all_results = []
for topic in topics:
    results = web_search(topic, max_results=5)
    all_results.extend(results)

# Deduplicate by URL
seen_urls: set[str] = set()
deduped = []
for r in all_results:
    if r.url not in seen_urls:
        seen_urls.add(r.url)
        deduped.append(r)

vs = get_vector_store()
stored = 0
for result in deduped:
    if result.title and result.url:
        news_id = f"search-{hash(result.url) & 0xFFFFFF}"
        vs.add_news_item(
            news_id=news_id,
            title=result.title,
            content=f"{result.title}. {result.snippet}. URL: {result.url}",
        )
        stored += 1
```

**Step 3: Commit**
```bash
git add backend/app/agents/graphs/feasibility_subgraph.py backend/app/agents/graphs/proactive/news_monitor.py
git commit -m "feat(search): wire search_gateway into feasibility and news monitor"
```

---

## Task 5: Frontend Types & API Client

**Files:**
- Modify: `frontend/lib/schemas.ts`
- Modify: `frontend/lib/api.ts`

**Step 1: Add types to schemas.ts**

Append to `frontend/lib/schemas.ts`:

```typescript
// Search Provider Settings
export const searchProviderKindSchema = z.enum(['exa', 'tavily', 'hn_algolia'])

export const searchProviderConfigSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  kind: searchProviderKindSchema,
  api_key: z.string().optional(),
  enabled: z.boolean().default(true),
  max_results: z.number().int().min(1).max(50).default(10),
})

export const searchSettingsSchema = z.object({
  id: z.string().min(1),
  providers: z.array(searchProviderConfigSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
})

export const patchSearchSettingsRequestSchema = z.object({
  providers: z.array(searchProviderConfigSchema),
})

export const testSearchProviderRequestSchema = z.object({
  provider: searchProviderConfigSchema,
})

export const testSearchProviderResponseSchema = z.object({
  ok: z.boolean(),
  latency_ms: z.number().int().nonnegative(),
  message: z.string().min(1),
  sample_results: z.number().int().nonnegative(),
})

export type SearchProviderKind = z.infer<typeof searchProviderKindSchema>
export type SearchProviderConfig = z.infer<typeof searchProviderConfigSchema>
export type SearchSettings = z.infer<typeof searchSettingsSchema>
export type PatchSearchSettingsRequest = z.infer<typeof patchSearchSettingsRequestSchema>
export type TestSearchProviderRequest = z.infer<typeof testSearchProviderRequestSchema>
export type TestSearchProviderResponse = z.infer<typeof testSearchProviderResponseSchema>
```

**Step 2: Add API functions to api.ts**

Append to `frontend/lib/api.ts`:

```typescript
// ── Search Settings ───────────────────────────────────────────────────────────

import type {
  SearchSettings,
  PatchSearchSettingsRequest,
  TestSearchProviderRequest,
  TestSearchProviderResponse,
} from './schemas'

export const getSearchSettings = async (): Promise<SearchSettings> => {
  return await jsonGet<SearchSettings>('/settings/search')
}

export const patchSearchSettings = async (
  payload: PatchSearchSettingsRequest
): Promise<SearchSettings> => {
  return await jsonPatch<PatchSearchSettingsRequest, SearchSettings>('/settings/search', payload)
}

export const testSearchProvider = async (
  payload: TestSearchProviderRequest
): Promise<TestSearchProviderResponse> => {
  return await jsonPost<TestSearchProviderRequest, TestSearchProviderResponse>(
    '/settings/search/test',
    payload
  )
}
```

**Step 3: Commit**
```bash
git add frontend/lib/schemas.ts frontend/lib/api.ts
git commit -m "feat(search): add search settings frontend types and API client"
```

---

## Task 6: SearchSettingsPage Component

**Files:**
- Create: `frontend/components/settings/SearchSettingsPage.tsx`

Design matches AISettingsPage exactly — same dark/lime color scheme, same card layout. Key differences:
- No `kind` selector dropdown showing "OpenAI Compatible / Anthropic"
- Instead shows "Exa / Tavily / HN Algolia (free)" as kind options
- No `base_url`, `temperature`, `timeout_seconds` fields
- Has `max_results` field (number, 1–50)
- Test response shows `sample_results` count
- "HN Algolia" provider shown as free/no-key-needed with a note

```tsx
'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { getSearchSettings, patchSearchSettings, testSearchProvider } from '../../lib/api'
import type { SearchProviderConfig, SearchProviderKind } from '../../lib/schemas'

const KIND_LABELS: Record<SearchProviderKind, string> = {
  exa: 'Exa (Neural Search)',
  tavily: 'Tavily',
  hn_algolia: 'HN Algolia (Free, no key)',
}

const DEFAULT_PROVIDER: SearchProviderConfig = {
  id: '',
  name: '',
  kind: 'exa',
  api_key: '',
  enabled: false,
  max_results: 10,
}

export function SearchSettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [providers, setProviders] = useState<SearchProviderConfig[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, string>>({})
  const [testingIds, setTestingIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const run = async () => {
      try {
        const settings = await getSearchSettings()
        setProviders(settings.providers.map((p) => ({ ...p, api_key: p.api_key ?? '' })))
        setUpdatedAt(settings.updated_at)
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to load search settings.')
      } finally {
        setLoading(false)
      }
    }
    void run()
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
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save search settings.')
    } finally {
      setSaving(false)
    }
  }

  const onTestProvider = async (provider: SearchProviderConfig) => {
    const key = provider.id.trim() || '(temp)'
    setTestingIds((prev) => ({ ...prev, [key]: true }))
    setTestResults((prev) => ({ ...prev, [key]: '' }))
    try {
      const result = await testSearchProvider({ provider })
      const label = result.ok ? 'OK' : 'FAILED'
      setTestResults((prev) => ({
        ...prev,
        [key]: `${label} · ${result.latency_ms}ms · ${result.message}`,
      }))
      if (result.ok) toast.success(`Provider ${key} returned ${result.sample_results} results.`)
      else toast.error(`Provider ${key} test failed.`)
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Test failed.'
      setTestResults((prev) => ({ ...prev, [key]: `FAILED · ${msg}` }))
      toast.error(msg)
    } finally {
      setTestingIds((prev) => ({ ...prev, [key]: false }))
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <section className="rounded-2xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-[#1e1e1e]">Search Settings</h1>
            <p className="mt-1 text-sm text-[#1e1e1e]/50">
              Configure your search provider for competitor discovery and market intelligence.
              HN Algolia is always available as a free fallback.
            </p>
          </div>
          <div className="text-xs text-[#1e1e1e]/35">
            {updatedAt ? `Updated: ${updatedAt}` : 'Not saved yet'}
          </div>
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-[#1e1e1e]/40">Loading search settings...</p>
        ) : (
          <>
            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-[0.15em] text-[#1e1e1e]/50 uppercase">
                  Providers
                </h2>
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
                  No providers configured. HN Algolia will be used as a free fallback.
                </p>
              )}

              <div className="space-y-3">
                {providers.map((provider, index) => {
                  const isActive = provider.enabled
                  const testKey = provider.id.trim() || '(temp)'
                  return (
                    <article
                      key={`${provider.id}-${index}`}
                      className="rounded-xl border-2 p-4 transition-colors"
                      style={{
                        borderColor: isActive ? '#b9eb10' : '#1e1e1e1a',
                        background: isActive ? '#1e1e1e' : '#ffffff',
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
                            style={{ color: isActive ? '#ffffff' : '#1e1e1e' }}
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
                            onClick={() => void onTestProvider(provider)}
                            disabled={Boolean(testingIds[testKey])}
                            className="rounded-lg border border-[#1e1e1e]/15 px-3 py-1.5 text-xs font-medium transition disabled:opacity-60"
                            style={{
                              background: isActive ? '#ffffff15' : '#f5f5f5',
                              color: isActive ? '#ffffff' : '#1e1e1e99',
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
                            label: 'API Key (not required for HN Algolia)',
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
                        ].map(({ label, key, type, value }) => (
                          <label key={key} className="text-sm">
                            <span
                              className="mb-1 block"
                              style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
                            >
                              {label}
                            </span>
                            <input
                              type={type}
                              min={key === 'max_results' ? 1 : undefined}
                              max={key === 'max_results' ? 50 : undefined}
                              value={value}
                              onChange={(e) =>
                                updateProvider(index, {
                                  [key]:
                                    type === 'number'
                                      ? Number(e.currentTarget.value) || 10
                                      : e.currentTarget.value,
                                })
                              }
                              className="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-2"
                              style={{
                                background: isActive ? '#ffffff0f' : '#f5f5f5',
                                borderColor: isActive ? '#ffffff22' : '#1e1e1e18',
                                color: isActive ? '#ffffff' : '#1e1e1e',
                              }}
                            />
                          </label>
                        ))}
                        <label className="text-sm">
                          <span
                            className="mb-1 block"
                            style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
                          >
                            Provider Kind
                          </span>
                          <select
                            value={provider.kind}
                            onChange={(e) =>
                              updateProvider(index, { kind: e.currentTarget.value as SearchProviderKind })
                            }
                            className="w-full rounded-xl border px-3 py-2 text-sm outline-none"
                            style={{
                              background: isActive ? '#ffffff0f' : '#f5f5f5',
                              borderColor: isActive ? '#ffffff22' : '#1e1e1e18',
                              color: isActive ? '#ffffff' : '#1e1e1e',
                            }}
                          >
                            {Object.entries(KIND_LABELS).map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                        </label>
                      </div>

                      {testResults[testKey] && (
                        <p
                          className="mt-3 text-xs"
                          style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
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
    </main>
  )
}
```

**Step 3: Commit**
```bash
git add frontend/components/settings/SearchSettingsPage.tsx
git commit -m "feat(search): add SearchSettingsPage component"
```

---

## Task 7: Settings Page Tab Switcher

**Files:**
- Modify: `frontend/app/settings/page.tsx`

Replace the current single-component render with a tabbed layout:

```tsx
'use client'

import { useState } from 'react'
import { AISettingsPage } from '../../components/settings/AISettingsPage'
import { SearchSettingsPage } from '../../components/settings/SearchSettingsPage'

type Tab = 'ai' | 'search'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('ai')

  return (
    <div>
      {/* Tab bar */}
      <div className="mx-auto max-w-6xl px-4 pt-6 sm:px-6">
        <nav className="flex gap-1 rounded-xl border border-[#1e1e1e]/10 bg-[#f5f5f5] p-1">
          {(
            [
              { id: 'ai', label: 'AI Provider' },
              { id: 'search', label: 'Search Provider' },
            ] as { id: Tab; label: string }[]
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className="flex-1 rounded-lg px-4 py-2 text-sm font-medium transition"
              style={{
                background: activeTab === tab.id ? '#1e1e1e' : 'transparent',
                color: activeTab === tab.id ? '#b9eb10' : '#1e1e1e66',
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'ai' ? <AISettingsPage /> : <SearchSettingsPage />}
    </div>
  )
}
```

Note: `AISettingsPage` and `SearchSettingsPage` both render their own `<main>` wrapper, so the tab bar sits above.

**Step 2: Commit**
```bash
git add frontend/app/settings/page.tsx
git commit -m "feat(search): add AI/Search tab switcher to Settings page"
```

---

## Final Verification

```bash
# 1. Backend starts without errors
cd /Users/efan404/Codes/indie_dev/pm-cursor
pnpm dev:api

# 2. Search endpoints accessible
curl -s http://127.0.0.1:8000/settings/search | python3 -m json.tool

# 3. Frontend compiles
pnpm dev:web

# 4. Navigate to http://127.0.0.1:3000/settings
# Should show two tabs: "AI Provider" | "Search Provider"
# Search Provider tab shows empty state with fallback message
# Add Exa/Tavily provider, enter API key, click Test → should return results
```

---

## Notes & Constraints

- **API keys always encrypted** in DB using same `secret_crypto.py` as AI settings
- **HN Algolia always available** as zero-config fallback — search never hard-fails
- **Exa/Tavily fail-open** — if active provider errors, falls back to HN silently (logged as warning)
- **No new DB migration needed** — table created by `bootstrap.py` on first run
- **`httpx` already in requirements.txt** — no new dependencies needed
- **Competitor search in feasibility is best-effort** — if search returns nothing, plan generation continues without it
