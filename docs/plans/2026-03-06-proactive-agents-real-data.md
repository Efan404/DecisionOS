# Proactive Agents — Real Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace mock data in all three proactive agents (News Monitor, Cross-Idea Analyzer, User Pattern Learner) with real data sources. News Monitor connects to Hacker News Algolia API (free, no key required). Cross-Idea Analyzer populates the vector store from real idea content written to DB. User Pattern Learner is already addressed in `2026-03-06-decision-patterns-real-data.md` — this plan does not duplicate that.

**Architecture:**

- **News Monitor**: On each scheduler run, fetch top HN stories, embed them into ChromaDB `news_items` collection, then match against `idea_summaries` by cosine similarity. Only create notifications for ideas where similarity > threshold (0.35). Deduplicate by storing `news_id` in notification metadata.
- **Cross-Idea Analyzer**: The vector store's `idea_summaries` collection is populated whenever an idea completes the Opportunity stage (already done via `memory_writer_node`). The analyzer uses the existing `match_news_to_ideas`-style search. The gap is that idea seeds aren't being written to the vector store when ideas are created — fix by hooking into idea creation and stage transitions.
- **Scheduler**: Change from 6-hour fixed interval to smarter triggering: run on startup (with 60s delay) and then every 6 hours.

**Tech Stack:** Python 3.12, `httpx` (already in requirements for async HTTP), ChromaDB (already installed), APScheduler (already installed), FastAPI.

**Key files:**

- `backend/app/agents/graphs/proactive/news_monitor.py`
- `backend/app/agents/graphs/proactive/cross_idea_analyzer.py`
- `backend/app/agents/memory/vector_store.py`
- `backend/app/core/scheduler.py`
- `backend/app/routes/ideas.py` — hook idea creation → vector store
- `backend/app/routes/insights.py` — trigger endpoints for manual testing

---

## Task 1: Verify httpx is available

**Files:**

- Read: `backend/requirements.txt`

**Step 1: Check httpx**

```bash
grep httpx backend/requirements.txt
```

If not present, add it:

```bash
echo "httpx>=0.27.0" >> backend/requirements.txt
cd backend && UV_CACHE_DIR=../.uv-cache uv pip install httpx
```

**Step 2: Verify import**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -c "import httpx; print('httpx', httpx.__version__)"
```

Expected: prints version string.

**Step 3: Commit if requirements changed**

```bash
git add backend/requirements.txt
git commit -m "chore: ensure httpx in requirements for HN API calls"
```

---

## Task 2: Add HackerNews data fetcher utility

**Files:**

- Create: `backend/app/core/hn_client.py`

Hacker News Algolia search API: `https://hn.algolia.com/api/v1/search?query=<term>&tags=story&hitsPerPage=10`
No API key needed. Returns `hits` with `objectID`, `title`, `url`, `points`, `created_at`.

**Step 1: Write the client**

```python
# backend/app/core/hn_client.py
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class HNStory:
    id: str          # objectID from Algolia
    title: str
    url: str | None
    points: int
    created_at: str


def fetch_top_stories(query: str, limit: int = 10) -> list[HNStory]:
    """Fetch HN stories matching a query via Algolia search.

    Returns empty list on any network/parse error (fail-open).
    """
    try:
        resp = httpx.get(
            HN_ALGOLIA_URL,
            params={"query": query, "tags": "story", "hitsPerPage": limit},
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        stories = []
        for hit in data.get("hits", []):
            stories.append(HNStory(
                id=str(hit.get("objectID", "")),
                title=str(hit.get("title", "")),
                url=hit.get("url"),
                points=int(hit.get("points") or 0),
                created_at=str(hit.get("created_at", "")),
            ))
        return stories
    except Exception as exc:
        logger.warning("hn_client.fetch_failed query=%r exc=%s", query, exc)
        return []


def fetch_top_tech_stories(limit: int = 20) -> list[HNStory]:
    """Fetch recent HN tech stories (broad query for news monitor baseline)."""
    return fetch_top_stories(query="product startup AI developer", limit=limit)
```

**Step 2: Write a test**

```python
# backend/tests/test_hn_client.py
from unittest.mock import patch, MagicMock
from app.core.hn_client import fetch_top_stories, HNStory


def test_fetch_top_stories_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "hits": [
            {"objectID": "123", "title": "AI Startup", "url": "https://example.com",
             "points": 100, "created_at": "2026-01-01"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("app.core.hn_client.httpx.get", return_value=mock_response):
        stories = fetch_top_stories("AI startup")

    assert len(stories) == 1
    assert isinstance(stories[0], HNStory)
    assert stories[0].id == "123"
    assert stories[0].title == "AI Startup"


def test_fetch_returns_empty_on_network_error():
    with patch("app.core.hn_client.httpx.get", side_effect=Exception("network down")):
        stories = fetch_top_stories("anything")
    assert stories == []
```

**Step 3: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_hn_client.py -v --tb=short
```

Expected: both tests pass.

**Step 4: Commit**

```bash
git add backend/app/core/hn_client.py backend/tests/test_hn_client.py
git commit -m "feat(proactive): add HackerNews Algolia client utility"
```

---

## Task 3: Rewrite News Monitor to use real HN stories

**Files:**

- Modify: `backend/app/agents/graphs/proactive/news_monitor.py`

**Step 1: Read the current file**

```bash
cat backend/app/agents/graphs/proactive/news_monitor.py
```

**Step 2: Rewrite the graph**

```python
# backend/app/agents/graphs/proactive/news_monitor.py
from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core import ai_gateway
from app.core.hn_client import fetch_top_tech_stories, fetch_top_stories
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store


SIMILARITY_THRESHOLD = 0.35  # cosine distance below this = relevant match


class NewsMonitorState(TypedDict):
    user_id: str
    idea_ids: list[str]
    notifications: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _fetch_news(state: NewsMonitorState) -> dict[str, object]:
    """Fetch recent HN stories and store them in the vector store."""
    stories = fetch_top_tech_stories(limit=20)

    vs = get_vector_store()
    stored = 0
    for story in stories:
        if story.title and story.id:
            vs.add_news_item(
                news_id=f"hn-{story.id}",
                title=story.title,
                content=f"{story.title}. Points: {story.points}. URL: {story.url or ''}",
            )
            stored += 1

    thought = {
        "agent": "news_fetcher",
        "action": "fetched_news",
        "detail": f"Fetched {len(stories)} HN stories, stored {stored} in vector store",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _match_news_to_ideas(state: NewsMonitorState) -> dict[str, object]:
    """Find idea↔news matches above similarity threshold using vector search."""
    vs = get_vector_store()

    # Get all stored ideas
    idea_data = vs._ideas.get(include=["documents", "metadatas"])
    idea_ids = idea_data.get("ids") or []
    idea_docs = idea_data.get("documents") or []

    if not idea_ids:
        return {
            "notifications": [],
            "agent_thoughts": [{
                "agent": "news_matcher",
                "action": "no_ideas",
                "detail": "No ideas in vector store yet — skip matching",
                "timestamp": utc_now_iso(),
            }],
        }

    # Get recent news items
    news_data = vs._news.get(include=["documents", "metadatas"])
    news_ids = news_data.get("ids") or []
    news_docs = news_data.get("documents") or []

    notifications = []
    matched_pairs: set[tuple[str, str]] = set()

    for news_id, news_doc in zip(news_ids[:20], news_docs[:20]):
        # Search ideas most similar to this news item
        if vs._ideas.count() == 0:
            continue
        results = vs._ideas.query(
            query_texts=[news_doc],
            n_results=min(3, vs._ideas.count()),
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idea_id, dist in zip(ids, distances):
            # ChromaDB cosine distance: 0 = identical, 1 = orthogonal
            if dist < SIMILARITY_THRESHOLD and (news_id, idea_id) not in matched_pairs:
                matched_pairs.add((news_id, idea_id))
                news_title = news_doc.split(".")[0][:80]
                notifications.append({
                    "news_id": news_id,
                    "news_title": news_title,
                    "idea_id": idea_id,
                    "distance": round(dist, 3),
                    "insight": (
                        f"Recent HN story '{news_title}' is relevant to your idea "
                        f"(similarity score: {round(1 - dist, 2):.0%})."
                    ),
                })

    thought = {
        "agent": "news_matcher",
        "action": "matched_news",
        "detail": f"Found {len(notifications)} relevant news↔idea matches above threshold",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": notifications, "agent_thoughts": [thought]}


def build_news_monitor_graph():
    graph = StateGraph(NewsMonitorState)
    graph.add_node("fetch_news", _fetch_news)
    graph.add_node("match_news_to_ideas", _match_news_to_ideas)
    graph.add_edge(START, "fetch_news")
    graph.add_edge("fetch_news", "match_news_to_ideas")
    graph.add_edge("match_news_to_ideas", END)
    return graph.compile()
```

**Step 3: Run existing proactive agent tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_proactive_agents.py -v --tb=short
```

Expected: tests pass (they use LLM mock mode, not real HN).

**Step 4: Commit**

```bash
git add backend/app/agents/graphs/proactive/news_monitor.py
git commit -m "feat(proactive): news_monitor fetches real HN stories and matches by vector similarity"
```

---

## Task 4: Populate vector store when ideas are created / updated

**Files:**

- Modify: `backend/app/routes/ideas.py`

The cross-idea analyzer only works if ideas are in the vector store. Currently `memory_writer_node` writes ideas when an Opportunity agent runs — but newly created ideas have no vector entry until the Opportunity stage completes.

**Step 1: Read ideas.py route**

```bash
grep -n "create_idea\|POST\|def " backend/app/routes/ideas.py | head -20
```

**Step 2: Add vector store writes on idea creation and title update**

In the `POST /ideas` (create) handler, after `_repo.create_idea(...)`:

```python
from app.agents.memory.vector_store import get_vector_store as _get_vs

# After creating the idea:
try:
    _get_vs().add_idea_summary(
        idea_id=idea.id,
        summary=f"{idea.title}. {idea.idea_seed or ''}".strip(". "),
    )
except Exception:
    pass  # Vector store failure must never break idea creation
```

In the `PATCH /ideas/{idea_id}` (update) handler, after `_repo.update_idea(...)`, if title or idea_seed changed:

```python
try:
    _get_vs().add_idea_summary(
        idea_id=updated.id,
        summary=f"{updated.title}. {updated.idea_seed or ''}".strip(". "),
    )
except Exception:
    pass
```

**Step 3: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_api_ideas_and_agents.py -v --tb=short -q 2>&1 | tail -15
```

Expected: all pass.

**Step 4: Commit**

```bash
git add backend/app/routes/ideas.py
git commit -m "feat(proactive): populate vector store on idea create/update for cross-idea analysis"
```

---

## Task 5: Improve Cross-Idea Analyzer to use richer content

**Files:**

- Modify: `backend/app/agents/graphs/proactive/cross_idea_analyzer.py`

**Step 1: Read current file**

```bash
cat backend/app/agents/graphs/proactive/cross_idea_analyzer.py
```

**Step 2: Rewrite to use vector similarity + AI insight generation**

```python
# backend/app/agents/graphs/proactive/cross_idea_analyzer.py
from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core import ai_gateway
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store

SIMILARITY_THRESHOLD = 0.40  # cosine distance: lower = more similar


class CrossIdeaState(TypedDict):
    user_id: str
    idea_summaries: list[dict]
    insights: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _load_ideas(state: CrossIdeaState) -> dict[str, object]:
    """Load all ideas from the vector store."""
    vs = get_vector_store()
    data = vs._ideas.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []

    summaries = [
        {"idea_id": id_, "summary": doc}
        for id_, doc in zip(ids, docs)
        if doc and doc.strip()
    ]
    thought = {
        "agent": "idea_loader",
        "action": "loaded_ideas",
        "detail": f"Loaded {len(summaries)} idea summaries from vector store",
        "timestamp": utc_now_iso(),
    }
    return {"idea_summaries": summaries, "agent_thoughts": [thought]}


def _find_similar_pairs(state: CrossIdeaState) -> dict[str, object]:
    """Find pairs of ideas with high vector similarity."""
    summaries = state.get("idea_summaries", [])
    if len(summaries) < 2:
        return {
            "insights": [],
            "agent_thoughts": [{
                "agent": "similarity_finder",
                "action": "insufficient_ideas",
                "detail": f"Only {len(summaries)} ideas — need ≥2 for cross-analysis",
                "timestamp": utc_now_iso(),
            }],
        }

    vs = get_vector_store()
    insights = []
    seen_pairs: set[frozenset[str]] = set()

    for entry in summaries:
        idea_a_id = entry["idea_id"]
        summary_a = entry["summary"]

        # Search for similar ideas (exclude self)
        count = vs._ideas.count()
        if count < 2:
            continue
        results = vs._ideas.query(
            query_texts=[summary_a],
            n_results=min(3, count),
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idea_b_id, dist in zip(ids, distances):
            if idea_b_id == idea_a_id:
                continue
            pair = frozenset({idea_a_id, idea_b_id})
            if pair in seen_pairs:
                continue
            if dist < SIMILARITY_THRESHOLD:
                seen_pairs.add(pair)
                summary_b = next(
                    (s["summary"] for s in summaries if s["idea_id"] == idea_b_id),
                    idea_b_id,
                )
                # Use LLM to generate a specific insight about the relationship
                try:
                    analysis = ai_gateway.generate_text(
                        task="opportunity",
                        user_prompt=(
                            f"Two product ideas appear related:\n"
                            f"Idea A: {summary_a[:150]}\n"
                            f"Idea B: {summary_b[:150]}\n\n"
                            "In 1-2 sentences, explain the strategic overlap or synergy. "
                            "Be specific — mention actual product features, not generic statements."
                        ),
                    )
                except Exception:
                    analysis = f"Ideas share a similarity score of {round(1 - dist, 2):.0%}."

                insights.append({
                    "idea_a_id": idea_a_id,
                    "idea_b_id": idea_b_id,
                    "similarity_distance": round(dist, 3),
                    "analysis": analysis.strip(),
                })

    thought = {
        "agent": "similarity_finder",
        "action": "found_pairs",
        "detail": f"Found {len(insights)} cross-idea relationships above threshold",
        "timestamp": utc_now_iso(),
    }
    return {"insights": insights, "agent_thoughts": [thought]}


def build_cross_idea_graph():
    graph = StateGraph(CrossIdeaState)
    graph.add_node("load_ideas", _load_ideas)
    graph.add_node("find_similar_pairs", _find_similar_pairs)
    graph.add_edge(START, "load_ideas")
    graph.add_edge("load_ideas", "find_similar_pairs")
    graph.add_edge("find_similar_pairs", END)
    return graph.compile()
```

**Step 3: Update insights route trigger to use the new graph signature**

In `backend/app/routes/insights.py`, the `trigger_cross_idea_analysis` endpoint no longer needs to pre-load ideas (the graph does it internally):

```python
@router.post("/cross-idea-analysis")
async def trigger_cross_idea_analysis():
    """Trigger cross-idea analysis agent."""
    from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
    from app.db.repo_notifications import NotificationRepository

    notif_repo = NotificationRepository()
    graph = build_cross_idea_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [],
        "insights": [],
        "agent_thoughts": [],
    })

    created = []
    for insight in result.get("insights", []):
        record = notif_repo.create(
            type="cross_idea_insight",
            title=f"Related ideas: {insight.get('idea_a_id', '')[:8]} ↔ {insight.get('idea_b_id', '')[:8]}",
            body=insight.get("analysis", "These ideas share common themes."),
            metadata=insight,
        )
        created.append(record.id)

    return {
        "notifications_created": len(created),
        "insights": result.get("insights", []),
        "agent_thoughts": result.get("agent_thoughts", []),
    }
```

**Step 4: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_proactive_agents.py -v --tb=short
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/agents/graphs/proactive/cross_idea_analyzer.py backend/app/routes/insights.py
git commit -m "feat(proactive): cross-idea analyzer uses vector similarity + AI insight generation"
```

---

## Task 6: Update scheduler — deduplicate notifications

**Files:**

- Modify: `backend/app/core/scheduler.py`

**Step 1: Read scheduler.py**

```bash
cat backend/app/core/scheduler.py
```

**Step 2: Add deduplication — skip creating notifications for news_ids already in DB**

In `run_proactive_agents`, before creating a news notification, check if one already exists for that `news_id`:

```python
# In the news monitor section inside run_proactive_agents:
for notif in result.get("notifications", []):
    news_id = notif.get("news_id", "")
    # Deduplicate: skip if we already have a notification for this news+idea pair
    if news_id and _notif_repo.exists_for_metadata_key("news_id", news_id):
        continue
    record = _notif_repo.create(
        type="news_match",
        title=f"News: {notif.get('news_title', 'Untitled')}",
        body=notif.get("insight", "Relevant news detected."),
        metadata=notif,
    )
    created_notifications.append(record)
```

**Step 3: Add `exists_for_metadata_key` to NotificationRepository**

In `backend/app/db/repo_notifications.py`, add:

```python
def exists_for_metadata_key(self, key: str, value: str) -> bool:
    """Return True if any notification has metadata_json containing {key: value}."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM notification
            WHERE json_extract(metadata_json, '$.' || ?) = ?
            LIMIT 1
            """,
            (key, value),
        ).fetchone()
    return row is not None
```

**Step 4: Add startup delay to scheduler**

In `create_scheduler()`:

```python
def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Run once 60 seconds after startup (let the app fully initialize)
    scheduler.add_job(
        run_proactive_agents,
        trigger="date",
        run_date=None,  # will be set dynamically in start_scheduler
        id="proactive_agents_startup",
        replace_existing=True,
        kwargs={"trigger_type": "startup"},
    )
    # Then every 6 hours
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

In `app/main.py` (or wherever the scheduler is started), set the startup run time:

```python
from datetime import datetime, timezone, timedelta

scheduler = create_scheduler()
# Patch the startup job to run 60s from now
startup_job = scheduler.get_job("proactive_agents_startup")
if startup_job:
    startup_job.modify(
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60)
    )
scheduler.start()
```

**Step 5: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/app/core/scheduler.py backend/app/db/repo_notifications.py
git commit -m "feat(proactive): add notification deduplication and startup delay to scheduler"
```

---

## Task 7: End-to-end smoke test for proactive agents

**Step 1: Start backend with real LLM_MODE**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  LLM_MODE=auto \
  UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  uvicorn app.main:app --reload --port 8000
```

**Step 2: Trigger news scan manually**

```bash
curl -s -X POST http://localhost:8000/insights/news-scan \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

Expected: returns `{ "notifications_created": N, "agent_thoughts": [...] }` where agent thoughts mention real HN stories.

**Step 3: Create two ideas and trigger cross-idea analysis**

```bash
# After creating two ideas via the UI:
curl -s -X POST http://localhost:8000/insights/cross-idea-analysis \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

Expected: returns insights with real similarity scores (not zero).

**Step 4: Check notifications appear in the bell dropdown**

Navigate to `http://localhost:3000` — the bell icon should show new notifications.

**Step 5: Commit final**

```bash
git add -A
git commit -m "feat(proactive): complete real-data proactive agents (HN news, vector similarity, dedup)"
```
