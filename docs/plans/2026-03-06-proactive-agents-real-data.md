# Proactive Agents — Real Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace mock data in all three proactive agents (News Monitor, Cross-Idea Analyzer, User Pattern Learner) with real data sources. News Monitor connects to Hacker News Algolia API (free, no key required). Cross-Idea Analyzer populates the vector store from real idea content written to DB. User Pattern Learner is already addressed in `2026-03-06-decision-patterns-real-data.md` — this plan does not duplicate that.

**Architecture:**

- **Source of truth is SQLite, not ChromaDB.** Notifications, ideas, and all structured data live in SQLite. ChromaDB is purely a semantic matching cache — it holds embeddings to find which ideas are relevant to news items, not to store authoritative data. If ChromaDB is wiped, only the matching accuracy is temporarily lost; no user data is lost.
- **News Monitor**: On each scheduler run, fetch HN stories **matching keywords from idea titles** (not a generic "top stories" feed — the Algolia API is a keyword search, not a trending feed). Embed each story into ChromaDB `news_items` collection, then match against `idea_summaries` by cosine similarity. Only create notifications where distance < threshold (0.35). Deduplicate using a composite key `(type, idea_id, news_id)` — check for an existing notification with matching `type="news_match"`, `metadata.idea_id`, and `metadata.news_id` before inserting.
- **Cross-Idea Analyzer**: Vector store is populated when ideas are created/updated (see Task 4). Dedup uses a sorted pair key: `sorted([idea_a_id, idea_b_id])` stored in notification metadata; skip inserting if both IDs already appear together in a prior `type="cross_idea_insight"` notification.
- **Scheduler**: The startup job must use `trigger="date", run_date=datetime.now(tz) + timedelta(seconds=60)` — **do not set `run_date=None`** (that fires immediately, before app is ready). The 6-hour recurring job uses `trigger="interval"`.
- **ChromaDB persistence**: ChromaDB is configured via `DECISIONOS_CHROMA_PATH` env var (default: `./chroma_data`). Tests set `DECISIONOS_CHROMA_PATH=""` to force in-memory mode — **this fix is already implemented**.

**Tech Stack:** Python 3.12, `httpx` (**not yet in requirements.txt — must be added**), ChromaDB (already installed), APScheduler (already installed), FastAPI.

**Key files:**

- `backend/app/agents/graphs/proactive/news_monitor.py`
- `backend/app/agents/graphs/proactive/cross_idea_analyzer.py`
- `backend/app/agents/memory/vector_store.py`
- `backend/app/core/scheduler.py`
- `backend/app/routes/ideas.py` — hook idea creation → vector store
- `backend/app/routes/insights.py` — trigger endpoints for manual testing

---

## Task 1: Add httpx to requirements (it is NOT currently there)

**Files:**

- Modify: `backend/requirements.txt`

**Step 1: Check httpx (expect it to be missing)**

```bash
grep httpx backend/requirements.txt || echo "NOT FOUND — must add"
```

**Step 2: Add it**

```bash
echo "httpx>=0.27.0" >> backend/requirements.txt
cd backend && UV_CACHE_DIR=../.uv-cache uv pip install httpx
```

**Step 3: Verify import**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -c "import httpx; print('httpx', httpx.__version__)"
```

Expected: prints version string like `httpx 0.27.2`.

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add httpx to requirements for HN Algolia API calls"
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


def fetch_stories_for_topics(topics: list[str], limit_per_topic: int = 5) -> list[HNStory]:
    """Fetch HN stories for each topic keyword and deduplicate by story ID.

    NOTE: The Algolia API is a keyword search, NOT a "top stories" or trending feed.
    Use specific topic keywords derived from your idea titles/seeds for best results.
    A generic query like 'product startup AI' returns different (and often irrelevant) results
    compared to topic-specific queries like 'mobile payment wallet India'.
    """
    seen: dict[str, HNStory] = {}
    for topic in topics:
        for story in fetch_top_stories(query=topic, limit=limit_per_topic):
            if story.id not in seen:
                seen[story.id] = story
    return list(seen.values())
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
from app.core.hn_client import fetch_stories_for_topics
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store


SIMILARITY_THRESHOLD = 0.35  # cosine distance below this = relevant match


class NewsMonitorState(TypedDict):
    user_id: str
    idea_summaries: list[dict]   # [{idea_id, summary}] — loaded from vector store
    notifications: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _load_ideas_for_topics(state: NewsMonitorState) -> dict[str, object]:
    """Load idea summaries from vector store to derive search topics."""
    vs = get_vector_store()
    data = vs._ideas.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    summaries = [{"idea_id": id_, "summary": doc} for id_, doc in zip(ids, docs) if doc]
    thought = {
        "agent": "news_monitor",
        "action": "loaded_ideas",
        "detail": f"Loaded {len(summaries)} ideas from vector store for topic extraction",
        "timestamp": utc_now_iso(),
    }
    return {"idea_summaries": summaries, "agent_thoughts": [thought]}


def _fetch_news(state: NewsMonitorState) -> dict[str, object]:
    """Fetch recent HN stories for topics derived from idea summaries.

    IMPORTANT: The Algolia API is keyword search, not a trending feed.
    We extract topic keywords from idea titles for targeted results.
    """
    summaries = state.get("idea_summaries", [])
    # Extract first 3-4 words from each idea title as search topics
    topics = []
    for s in summaries[:10]:  # cap at 10 ideas to avoid rate limits
        words = s["summary"].split()[:4]
        if words:
            topics.append(" ".join(words))

    if not topics:
        topics = ["AI startup product"]  # fallback if no ideas exist yet

    stories = fetch_stories_for_topics(topics, limit_per_topic=5)

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
    graph.add_node("load_ideas_for_topics", _load_ideas_for_topics)
    graph.add_node("fetch_news", _fetch_news)
    graph.add_node("match_news_to_ideas", _match_news_to_ideas)
    graph.add_edge(START, "load_ideas_for_topics")
    graph.add_edge("load_ideas_for_topics", "fetch_news")
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

**Step 1: Read ideas.py route to understand what fields are supported**

```bash
grep -n "create_idea\|PATCH\|IdeaUpdate\|idea_seed\|def " backend/app/routes/ideas.py | head -30
cat backend/app/db/repo_ideas.py | grep -A20 "class IdeaUpdate\|def update_idea"
```

**IMPORTANT**: Check whether PATCH /ideas accepts `idea_seed` before assuming it does. If `IdeaUpdate` schema does not include `idea_seed`, do NOT add vector store writes for it in the PATCH handler — only write the `title` (which is always available).

**Step 2: Add vector store writes on idea creation**

In the `POST /ideas` (create) handler, after `_repo.create_idea(...)`:

```python
from app.agents.memory.vector_store import get_vector_store as _get_vs

# After creating the idea:
try:
    _get_vs().add_idea_summary(
        idea_id=idea.id,
        summary=idea.title,  # idea_seed not available at creation time
    )
except Exception:
    pass  # Vector store failure must never break idea creation
```

**Step 3: Add vector store write after Opportunity agent completes (memory_writer_node)**

The `memory_writer_node` in `backend/app/agents/graphs/idea/memory_writer.py` already writes to the vector store after an Opportunity run. Verify it uses `idea.title + idea.idea_seed` as the summary. If it does, **no change needed** — the vector store will be enriched automatically once users run the Opportunity agent.

In the `PATCH /ideas/{idea_id}` (update) handler, only write to vector store if PATCH supports `title` changes:

```python
try:
    _get_vs().add_idea_summary(
        idea_id=updated.id,
        summary=updated.title,
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

**Step 2: Add deduplication — skip creating notifications for known (type, idea_id, news_id) combos**

Dedup must use a **composite key** — `news_id` alone is not enough because the same news story could match multiple ideas. The correct key is `(type="news_match", idea_id, news_id)`.

For cross-idea notifications, the key is `sorted([idea_a_id, idea_b_id])` stored in metadata — skip if both appear together in an existing `cross_idea_insight` notification.

In `run_proactive_agents`, before creating a news notification:

```python
# In the news monitor section inside run_proactive_agents:
for notif in result.get("notifications", []):
    news_id = notif.get("news_id", "")
    idea_id = notif.get("idea_id", "")
    # Deduplicate: skip if we already have a notification for this EXACT (news_id, idea_id) pair
    if news_id and idea_id and _notif_repo.exists_news_match(news_id=news_id, idea_id=idea_id):
        continue
    record = _notif_repo.create(
        type="news_match",
        title=f"News: {notif.get('news_title', 'Untitled')}",
        body=notif.get("insight", "Relevant news detected."),
        metadata=notif,
    )
    created_notifications.append(record)
```

For cross-idea analysis:

```python
for insight in result.get("insights", []):
    idea_a_id = insight.get("idea_a_id", "")
    idea_b_id = insight.get("idea_b_id", "")
    # Deduplicate: sorted pair so (a,b) == (b,a)
    if idea_a_id and idea_b_id and _notif_repo.exists_cross_idea(idea_a_id, idea_b_id):
        continue
    record = _notif_repo.create(
        type="cross_idea_insight",
        title=f"Related ideas detected",
        body=insight.get("analysis", "These ideas share common themes."),
        metadata=insight,
    )
    created_notifications.append(record)
```

**Step 3: Add `exists_news_match` and `exists_cross_idea` to NotificationRepository**

In `backend/app/db/repo_notifications.py`, add:

```python
def exists_news_match(self, news_id: str, idea_id: str) -> bool:
    """Return True if a news_match notification already exists for this (news_id, idea_id) pair."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM notification
            WHERE type = 'news_match'
              AND json_extract(metadata_json, '$.news_id') = ?
              AND json_extract(metadata_json, '$.idea_id') = ?
            LIMIT 1
            """,
            (news_id, idea_id),
        ).fetchone()
    return row is not None


def exists_cross_idea(self, idea_a_id: str, idea_b_id: str) -> bool:
    """Return True if a cross_idea_insight notification already exists for this idea pair.

    Order-independent: (a, b) == (b, a).
    """
    pair_a, pair_b = sorted([idea_a_id, idea_b_id])
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM notification
            WHERE type = 'cross_idea_insight'
              AND (
                (json_extract(metadata_json, '$.idea_a_id') = ? AND json_extract(metadata_json, '$.idea_b_id') = ?)
                OR
                (json_extract(metadata_json, '$.idea_a_id') = ? AND json_extract(metadata_json, '$.idea_b_id') = ?)
              )
            LIMIT 1
            """,
            (pair_a, pair_b, pair_b, pair_a),
        ).fetchone()
    return row is not None
```

**Step 4: Fix scheduler startup delay**

**IMPORTANT**: `trigger="date", run_date=None` fires the job **immediately** when `scheduler.start()` is called, before the app is ready. Do NOT use `run_date=None` and patch it later — APScheduler does not support deferred `run_date` on `DateTrigger`.

The correct approach: compute `run_date` at job-registration time, **before** calling `scheduler.start()`.

In `create_scheduler()` (or wherever jobs are registered), pass `run_date` directly:

```python
from datetime import datetime, timezone, timedelta

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # WRONG (fires immediately): trigger="date", run_date=None
    # RIGHT: compute run_date now, before scheduler.start()
    startup_run_time = datetime.now(timezone.utc) + timedelta(seconds=60)

    scheduler.add_job(
        run_proactive_agents,
        trigger="date",
        run_date=startup_run_time,  # 60s from now at registration time
        id="proactive_agents_startup",
        replace_existing=True,
        kwargs={"trigger_type": "startup"},
    )
    # Recurring every 6 hours
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

**No patching needed in `main.py`** — `create_scheduler()` must be called when the app is ready (e.g., in a FastAPI `lifespan` handler), so `datetime.now()` inside `create_scheduler()` is already post-startup.

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

## Task 7: Add targeted unit tests and end-to-end smoke test

**Why new tests are needed**: The existing `test_proactive_agents.py` tests only verify that graphs return some output — they do NOT assert:

- Network failures in `hn_client` still produce empty lists (not exceptions)
- Duplicate notifications are not created when the scheduler runs twice with the same news
- Data loss does not occur when ChromaDB restarts (because SQLite is source of truth)
- Cross-idea dedup prevents duplicate `cross_idea_insight` notifications for the same pair

These assertions must be added as explicit test cases. Write them **before** implementing the corresponding code (TDD).

**New test cases to write:**

```python
# backend/tests/test_news_dedup.py

def test_news_match_no_duplicate_notification(client, auth_headers):
    """Running news scan twice with the same news/idea pair creates only 1 notification."""
    # Setup: create an idea, add it to vector store, mock HN to return same story
    # Run: POST /insights/news-scan twice
    # Assert: notification count for that news_id+idea_id is exactly 1

def test_cross_idea_no_duplicate_notification(client, auth_headers):
    """Cross-idea analysis twice with same idea pair creates only 1 notification."""
    # Setup: add 2 ideas to vector store with high similarity
    # Run: POST /insights/cross-idea-analysis twice
    # Assert: notification count for that pair is exactly 1
```

**Step 1: Write the failing tests (they will fail until dedup is implemented)**

**Step 2: Run them to confirm they fail**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_news_dedup.py -v --tb=short
```

Expected: FAIL with "expected 1 notification, got 2" or similar.

**Step 3: Implement dedup (Task 6), then re-run to confirm they pass.**

---

## Task 8: End-to-end smoke test for proactive agents

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
