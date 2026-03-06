# Decision Patterns — Real Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hardcoded mock `decision_history` in the pattern learner with real user behavior events captured from the existing workflow (DAG path confirm, feasibility plan selection, scope freeze, PRD generation), persist learned patterns to the DB, and surface them live in the Profile page.

**Architecture:**
A new `decision_events` SQLite table records one row per user action at key workflow checkpoints. The existing `UserPatternLearner` LangGraph reads from this table instead of hardcoded stubs. Learned patterns are persisted back to a new `learned_patterns_json` column in `user_preferences`. The `/insights/user-patterns` API reads from the DB first (zero LLM calls if fresh) and only re-runs the LangGraph when the event count has changed since last learning.

**Design constraints (critical):**

1. **Cache invalidation uses event count delta**: Persist `last_learned_event_count: int` alongside `learned_patterns_json`. On each `/insights/user-patterns` request, compare current `count_for_user()` against `last_learned_event_count` — re-run the graph only if the count increased. This prevents stale results building up indefinitely.

2. **`learned_patterns_json` lives in `user_preferences` as a separate semantic concern**: The `updated_at` column in `user_preferences` is for profile preference changes (email, notify settings). Pattern writes must **not** update `updated_at` — use a separate `patterns_updated_at` column, or accept that `updated_at` is ambiguous (document the choice). Do NOT let pattern writes touch email/notify_enabled fields.

3. **`feasibility_plan_selected` event is captured at PATCH context, not in the agent stream**: The agent generates feasibility plans but does NOT select one — the user selects via `PATCH /ideas/{idea_id}/context` (sets `selected_plan_id`). The event must be recorded in the PATCH context endpoint, not in `stream_feasibility`. Read `backend/app/routes/idea_agents.py` and `backend/app/routes/idea_context.py` to find the correct PATCH handler before writing any code.

4. **`prd_generated` events need business dedup**: `stream_prd` is an SSE route; the client may reconnect and retrigger the route. Add a dedup check: skip inserting `prd_generated` if an event already exists with the same `(idea_id, event_type="prd_generated")` and the same `baseline_id` in payload. Use `INSERT OR IGNORE` with a unique constraint, or query before inserting.

5. **Bootstrap ALTER TABLE must use PRAGMA check, not try/except**: The `try/except sqlite3.OperationalError: pass` pattern swallows real SQL errors. Instead, check if the column already exists with `PRAGMA table_info(user_preferences)` and skip the ALTER if found.

6. **Event payloads must capture user-interpretable decision variables**, not internal IDs:
   - `dag_path_confirmed`: include the human-readable leaf node content, not just `path_id`
   - `feasibility_plan_selected`: include `plan_name`, `score_overall`, `selected_plan_id`
   - `scope_frozen`: include `in_scope_count`, `out_scope_count`, `baseline_id`
   - `prd_generated`: include `baseline_id` (scope it was generated from)

7. **Pre-existing test failures are unrelated to this feature**: `test_profile_route.py` and `test_auth_api.py` fail with 401 due to env var mismatch (`DECISIONOS_SEED_ADMIN_PASSWORD`), not due to patterns changes. Do not treat these as success signals. Only newly written tests for `decision_events` are authoritative.

**Tech Stack:** Python 3.12, SQLite, LangGraph (existing), FastAPI, Next.js 14.

**Key files:**

- `backend/app/db/models.py` — schema (add `decision_events` table, extend `user_preferences`)
- `backend/app/db/repo_profile.py` — extend with pattern read/write
- `backend/app/routes/idea_agents.py` — insert events at `_apply_prd`, feasibility, scope confirm points
- `backend/app/routes/idea_dag.py` — insert event at path confirmation (`/paths` POST)
- `backend/app/routes/insights.py` — rewrite `get_user_patterns` to use real data
- `backend/app/agents/graphs/proactive/user_pattern_learner.py` — read from DB
- `frontend/components/insights/UserPatternCard.tsx` — remove "Demo data" badge once real

---

## Task 1: Add decision_events table and learned_patterns column

**Files:**

- Modify: `backend/app/db/models.py`

**Step 1: Read models.py**

```bash
cat backend/app/db/models.py
```

**Step 2: Add the new table and column at the end of SCHEMA_STATEMENTS**

Append two new statements to the `SCHEMA_STATEMENTS` tuple, after the `user_preferences` table:

```python
    """
    ALTER TABLE user_preferences
    ADD COLUMN learned_patterns_json TEXT NOT NULL DEFAULT '{}';
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_events (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL DEFAULT 'default',
        idea_id     TEXT,
        event_type  TEXT NOT NULL CHECK (event_type IN (
                        'dag_path_confirmed',
                        'feasibility_plan_selected',
                        'scope_frozen',
                        'prd_generated'
                    )),
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_decision_events_user_created
    ON decision_events(user_id, created_at DESC);
    """,
```

> Note: SQLite `ALTER TABLE … ADD COLUMN` will fail if the column already exists. The bootstrap code (Task 2) uses a `PRAGMA table_info` check — **not** `try/except` — to guard against re-running on an existing schema. See Task 2 for the exact implementation pattern.

**Step 3: Run existing tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass (schema is applied at bootstrap).

**Step 4: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(patterns): add decision_events table and learned_patterns_json column"
```

---

## Task 2: Update bootstrap to handle ALTER TABLE safely

**Files:**

- Modify: `backend/app/db/bootstrap.py`

The `ALTER TABLE … ADD COLUMN` statement will fail if the column already exists. We need to run it defensively.

**Step 1: Read bootstrap.py**

```bash
cat backend/app/db/bootstrap.py
```

**Step 2: Use PRAGMA table_info check before ALTER TABLE (do NOT use try/except)**

`try/except sqlite3.OperationalError: pass` swallows real SQL errors along with "column already exists" errors, making bugs invisible. Use `PRAGMA table_info` to check explicitly:

```python
def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def run_bootstrap(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        stripped = statement.strip().upper()
        if stripped.startswith("ALTER TABLE") and "ADD COLUMN" in stripped:
            # Parse: ALTER TABLE <table> ADD COLUMN <colname> ...
            # Extract table name and column name to check existence first
            parts = statement.split()
            table_name = parts[2]  # ALTER TABLE <table_name> ...
            col_idx = [i for i, p in enumerate(parts) if p.upper() == "COLUMN"]
            if col_idx:
                col_name = parts[col_idx[0] + 1]
                if _column_exists(connection, table_name, col_name):
                    continue  # column already exists, skip
        connection.execute(statement)
    connection.commit()
```

**Step 3: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass.

**Step 4: Commit**

```bash
git add backend/app/db/bootstrap.py
git commit -m "fix(db): guard ALTER TABLE with PRAGMA table_info check during bootstrap"
```

---

## Task 3: Add DecisionEventRepository

**Files:**

- Create: `backend/app/db/repo_decision_events.py`

**Step 1: Write the repository**

```python
# backend/app/db/repo_decision_events.py
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass

from app.core.time import utc_now_iso
from app.db.engine import get_connection


@dataclass
class DecisionEventRecord:
    id: str
    user_id: str
    idea_id: str | None
    event_type: str
    payload: dict
    created_at: str


class DecisionEventRepository:
    def record(
        self,
        *,
        event_type: str,
        idea_id: str | None = None,
        payload: dict | None = None,
        user_id: str = "default",
    ) -> DecisionEventRecord:
        """Insert one decision event row."""
        record_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO decision_events (id, user_id, idea_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, user_id, idea_id, event_type, payload_str, now),
            )
        return DecisionEventRecord(
            id=record_id,
            user_id=user_id,
            idea_id=idea_id,
            event_type=event_type,
            payload=payload or {},
            created_at=now,
        )

    def list_for_user(
        self,
        user_id: str = "default",
        limit: int = 100,
    ) -> list[DecisionEventRecord]:
        """Return the most recent decision events for a user."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, idea_id, event_type, payload_json, created_at
                FROM decision_events
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            DecisionEventRecord(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                idea_id=row["idea_id"],
                event_type=str(row["event_type"]),
                payload=json.loads(str(row["payload_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def count_for_user(self, user_id: str = "default") -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM decision_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0
```

**Step 2: Write tests**

Create `backend/tests/test_decision_events_repo.py`:

```python
# backend/tests/test_decision_events_repo.py
import pytest
from app.db.repo_decision_events import DecisionEventRepository


def test_record_and_list(tmp_db):
    repo = DecisionEventRepository()
    repo.record(event_type="dag_path_confirmed", idea_id="idea-1", payload={"path_id": "p1"})
    repo.record(event_type="feasibility_plan_selected", idea_id="idea-1", payload={"plan_name": "Bootstrap"})

    events = repo.list_for_user()
    assert len(events) == 2
    assert events[0].event_type == "feasibility_plan_selected"  # most recent first
    assert events[1].event_type == "dag_path_confirmed"


def test_count(tmp_db):
    repo = DecisionEventRepository()
    assert repo.count_for_user() == 0
    repo.record(event_type="scope_frozen", idea_id="idea-2")
    assert repo.count_for_user() == 1


def test_list_respects_limit(tmp_db):
    repo = DecisionEventRepository()
    for i in range(10):
        repo.record(event_type="prd_generated", idea_id=f"idea-{i}")
    events = repo.list_for_user(limit=3)
    assert len(events) == 3
```

Note: `tmp_db` fixture should already exist in `tests/_test_env.py` or `conftest.py`. Check with `grep -r "tmp_db\|fixture" backend/tests/_test_env.py | head -5`.

**Step 3: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_decision_events_repo.py -v --tb=short
```

Expected: all 3 tests pass.

**Step 4: Commit**

```bash
git add backend/app/db/repo_decision_events.py backend/tests/test_decision_events_repo.py
git commit -m "feat(patterns): add DecisionEventRepository with record/list/count"
```

---

## Task 4: Instrument key workflow endpoints to record events

**Files:**

- Modify: `backend/app/routes/idea_dag.py` (path confirmation endpoint)
- Modify: `backend/app/routes/idea_agents.py` (feasibility plan selection, scope freeze, PRD done)

The event insertion should happen **after** the DB write succeeds — never before, so we don't record events for failed operations.

**Step 1: Add event recording to DAG path confirmation**

In `backend/app/routes/idea_dag.py`, find the `POST /paths` endpoint (line ~218).
After the path is saved, insert a `dag_path_confirmed` event:

```python
# At top of idea_dag.py, add:
from app.db.repo_decision_events import DecisionEventRepository
_event_repo = DecisionEventRepository()

# Inside the POST /paths handler, after saving the path:
_event_repo.record(
    event_type="dag_path_confirmed",
    idea_id=idea_id,
    payload={
        "path_id": path.id,
        "node_count": len(node_chain),
        "leaf_content": node_chain[-1] if node_chain else "",
    },
)
```

**Step 2: Add event recording to feasibility plan selection — at PATCH context, NOT in agent stream**

**CRITICAL**: The `stream_feasibility` agent generates plans but does NOT record user selection. The user selects a plan later via `PATCH /ideas/{idea_id}/context` (sets `selected_plan_id`). Recording the event in the agent stream would capture the agent's default, not the user's actual choice.

**First**: Read the PATCH context endpoint to find where `selected_plan_id` is written:

```bash
grep -n "selected_plan_id\|context\|PATCH" backend/app/routes/idea_agents.py | head -20
# Also check if there is a dedicated context route:
grep -rn "selected_plan_id" backend/app/routes/ | head -10
```

**Then** add the event in the PATCH handler, after `selected_plan_id` is persisted:

```python
# In the PATCH /ideas/{idea_id}/context handler, after saving:
if body.selected_plan_id and body.selected_plan_id != existing_context.selected_plan_id:
    # User changed their plan selection — record the decision event
    plan_name = ""
    if existing_context.feasibility:
        plan = next(
            (p for p in existing_context.feasibility.plans if p.id == body.selected_plan_id),
            None,
        )
        plan_name = plan.name if plan else ""
        score = plan.score_overall if plan and hasattr(plan, "score_overall") else None
    _event_repo.record(
        event_type="feasibility_plan_selected",
        idea_id=idea_id,
        payload={
            "selected_plan_id": body.selected_plan_id,
            "plan_name": plan_name,
            "score_overall": score,
        },
    )
```

**Step 3: Add event at scope freeze**

In `backend/app/routes/idea_scope.py`, find the endpoint that freezes a scope baseline. After successful freeze:

```python
_event_repo_scope = DecisionEventRepository()
_event_repo_scope.record(
    event_type="scope_frozen",
    idea_id=idea_id,
    payload={
        "baseline_id": baseline_id,
        "in_scope_count": len(in_scope_items),
        "out_scope_count": len(out_scope_items),
    },
)
```

**Step 4: Add event at PRD generation done — with dedup to handle SSE reconnects**

`stream_prd` is an SSE route. Clients reconnect on network drops, re-running the whole SSE generator. Without dedup, each reconnect inserts a duplicate `prd_generated` event, which will make the pattern learner think the user generated 10 PRDs for the same idea.

Use `baseline_id` as the dedup key — one `prd_generated` event per `(idea_id, baseline_id)` pair:

```python
# Add a method to DecisionEventRepository:
def exists_for_idea_event_key(self, idea_id: str, event_type: str, key: str, value: str) -> bool:
    """Check if a decision event already exists for this (idea_id, event_type, payload key=value)."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM decision_events
            WHERE idea_id = ? AND event_type = ?
              AND json_extract(payload_json, '$.' || ?) = ?
            LIMIT 1
            """,
            (idea_id, event_type, key, value),
        ).fetchone()
    return row is not None
```

Then in `stream_prd`, inside the event_generator, after the PRD is done:

```python
baseline_id = pack.step4_scope.baseline_meta.baseline_id
# Dedup: only record if this baseline hasn't been recorded yet
if not _event_repo_module.exists_for_idea_event_key(idea_id, "prd_generated", "baseline_id", baseline_id):
    _event_repo_module.record(
        event_type="prd_generated",
        idea_id=idea_id,
        payload={
            "baseline_id": baseline_id,
        },
    )
```

Note: `requirements_count` and `backlog_count` are removed from the payload — they are always 0 in the current simplified PRD flow (single-call, no two-stage). Don't record misleading metrics.

**Step 5: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/app/routes/idea_dag.py backend/app/routes/idea_agents.py backend/app/routes/idea_scope.py
git commit -m "feat(patterns): instrument workflow endpoints to record decision events"
```

---

## Task 5: Update pattern learner to read real events + persist results

**Files:**

- Modify: `backend/app/agents/graphs/proactive/user_pattern_learner.py`
- Modify: `backend/app/db/repo_profile.py`

**Step 1: Extend DB schema and ProfileRepository to persist learned patterns with cache metadata**

First, the schema needs **two** new columns in `user_preferences`:

- `learned_patterns_json TEXT NOT NULL DEFAULT '{}'` — the actual patterns
- `last_learned_event_count INTEGER NOT NULL DEFAULT 0` — cache invalidation signal

This is cleaner than storing `updated_at` ambiguously (see design constraint #2).

**Schema additions** (in `models.py` SCHEMA_STATEMENTS, as two separate ALTER TABLE statements):

```sql
ALTER TABLE user_preferences ADD COLUMN learned_patterns_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE user_preferences ADD COLUMN last_learned_event_count INTEGER NOT NULL DEFAULT 0;
```

**ProfileRepository methods**:

```python
def get_learned_patterns(self, user_id: str = "default") -> tuple[dict, int]:
    """Return (patterns_dict, last_learned_event_count). Both empty/0 if not set."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT learned_patterns_json, last_learned_event_count FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {}, 0
    try:
        patterns = json.loads(str(row["learned_patterns_json"]))
        count = int(row["last_learned_event_count"] or 0)
        return patterns, count
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}, 0


def save_learned_patterns(self, user_id: str = "default", patterns: dict, event_count: int = 0) -> None:
    """Upsert learned patterns dict WITHOUT touching email/notify_enabled/updated_at.

    The updated_at column belongs to profile preference changes, NOT pattern learning.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, learned_patterns_json, last_learned_event_count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                learned_patterns_json = excluded.learned_patterns_json,
                last_learned_event_count = excluded.last_learned_event_count
            """,
            (user_id, json.dumps(patterns, ensure_ascii=False), event_count),
        )
```

Note: `save_learned_patterns` intentionally does **not** update `updated_at` — that field tracks profile preference writes only.

**Step 2: Rewrite user_pattern_learner.py to use real events**

```python
# backend/app/agents/graphs/proactive/user_pattern_learner.py
from __future__ import annotations

import json
import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core import ai_gateway
from app.core.time import utc_now_iso
from app.db.repo_decision_events import DecisionEventRepository
from app.db.repo_profile import ProfileRepository


class PatternLearnerState(TypedDict):
    user_id: str
    decision_history: list[dict]   # loaded from decision_events table
    learned_preferences: dict
    agent_thoughts: Annotated[list[dict], operator.add]


_event_repo = DecisionEventRepository()
_profile_repo = ProfileRepository()


def _load_history(state: PatternLearnerState) -> dict[str, object]:
    """Load real decision events from DB for the user."""
    user_id = state.get("user_id", "default")
    events = _event_repo.list_for_user(user_id=user_id, limit=50)

    history = []
    for e in events:
        payload = e.payload
        history.append({
            "stage": e.event_type,
            "choice": payload.get("plan_name") or payload.get("path_id") or e.event_type,
            "idea": payload.get("idea_id") or e.idea_id or "",
            "detail": payload,
        })

    thought = {
        "agent": "history_loader",
        "action": "loaded_history",
        "detail": f"Loaded {len(history)} real decision events from DB for user '{user_id}'",
        "timestamp": utc_now_iso(),
    }
    return {"decision_history": history, "agent_thoughts": [thought]}


def _extract_patterns(state: PatternLearnerState) -> dict[str, object]:
    """Use LLM to extract preference patterns from real history."""
    history = state.get("decision_history", [])
    user_id = state.get("user_id", "default")

    if not history:
        return {
            "learned_preferences": {},
            "agent_thoughts": [{
                "agent": "pattern_extractor",
                "action": "no_history",
                "detail": "No decision history available yet — returning empty preferences",
                "timestamp": utc_now_iso(),
            }],
        }

    history_text = "\n".join(
        f"- Event: {d.get('stage')}, Choice: {d.get('choice')}, Idea: {d.get('idea')}"
        for d in history[:30]  # cap at 30 to avoid token overflow
    )

    try:
        raw = ai_gateway.generate_text(
            task="opportunity",
            user_prompt=(
                "Analyze this user's product decision history and identify key patterns.\n\n"
                f"Decision history:\n{history_text}\n\n"
                "Return a JSON object with these keys:\n"
                "- business_model_preference: short description (e.g. 'Bootstrapped, minimal investment')\n"
                "- risk_tolerance: short description (e.g. 'Low — prefers incremental MVPs')\n"
                "- focus_area: product domain pattern (e.g. 'Developer tools and AI productivity')\n"
                "- decision_style: how they make choices (e.g. 'Data-driven, iterative')\n"
                "Each value must be a specific, evidence-based string of ≤15 words.\n"
                "Return only valid JSON."
            ),
        )
        try:
            preferences = json.loads(raw.strip().strip("`").strip())
            if not isinstance(preferences, dict):
                preferences = {"raw_analysis": str(preferences)}
        except json.JSONDecodeError:
            preferences = {"raw_analysis": raw.strip()[:200]}
    except Exception as exc:
        preferences = {"analysis_status": f"failed: {exc}"}

    # Persist to DB so next API call can return instantly
    _profile_repo.save_learned_patterns(user_id=user_id, patterns=preferences)

    thought = {
        "agent": "pattern_extractor",
        "action": "extracted_patterns",
        "detail": f"Extracted {len(preferences)} pattern keys from {len(history)} real events",
        "timestamp": utc_now_iso(),
    }
    return {"learned_preferences": preferences, "agent_thoughts": [thought]}


def build_pattern_learner_graph():
    graph = StateGraph(PatternLearnerState)
    graph.add_node("load_history", _load_history)
    graph.add_node("extract_patterns", _extract_patterns)
    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "extract_patterns")
    graph.add_edge("extract_patterns", END)
    return graph.compile()
```

**Step 3: Rewrite `/insights/user-patterns` endpoint with correct cache invalidation**

The fast path must compare `current_event_count` against `last_learned_event_count` stored in the DB. If they are equal, patterns are fresh. If count increased, re-run the graph.

```python
@router.get("/user-patterns")
async def get_user_patterns():
    """Return learned user patterns.

    Fast path: return cached patterns if event_count hasn't changed since last learning.
    Slow path: re-run the pattern learner graph when new events have been recorded.
    """
    from app.db.repo_profile import ProfileRepository
    from app.db.repo_decision_events import DecisionEventRepository
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph

    profile_repo = ProfileRepository()
    event_repo = DecisionEventRepository()

    current_event_count = event_repo.count_for_user()
    cached_patterns, last_learned_count = profile_repo.get_learned_patterns()

    # Fast path: cached patterns are still valid (no new events since last learning)
    if cached_patterns and current_event_count > 0 and current_event_count == last_learned_count:
        return {"preferences": cached_patterns, "source": "cached", "event_count": current_event_count}

    if current_event_count == 0:
        return {"preferences": {}, "source": "no_events", "event_count": 0}

    # Slow path: new events have appeared — re-run graph and update cache
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    # save_learned_patterns stores the event_count so next call can use fast path
    return {
        "preferences": result.get("learned_preferences", {}),
        "source": "computed",
        "event_count": current_event_count,
    }
```

**Passing the real event count through graph state (required for correct cache invalidation):**

The `event_count` stored in `last_learned_event_count` must be the **real DB total** (`count_for_user()`), not `len(decision_history)` (which is capped at 50). Using `len(history)` causes the cache to appear stale whenever the user has >50 events, triggering a re-run on every API call.

Pass `current_event_count` through graph state by adding it to the initial state dict in the `/insights/user-patterns` endpoint:

```python
# In get_user_patterns, when calling graph.invoke():
result = graph.invoke({
    "user_id": "default",
    "decision_history": [],
    "learned_preferences": {},
    "agent_thoughts": [],
    "current_event_count": current_event_count,  # real DB total
})
```

Add `current_event_count: int` to `PatternLearnerState`:

```python
class PatternLearnerState(TypedDict):
    user_id: str
    current_event_count: int   # real DB total, passed in at graph.invoke time
    decision_history: list[dict]
    learned_preferences: dict
    agent_thoughts: Annotated[list[dict], operator.add]
```

Then in `_extract_patterns`, use `state.get("current_event_count", 0)` instead of `len(history)`:

```python
event_count = state.get("current_event_count", 0)
_profile_repo.save_learned_patterns(user_id=user_id, patterns=preferences, event_count=event_count)
```

This guarantees that on the next `/insights/user-patterns` call, `current_event_count == last_learned_event_count` is exact and the fast path fires correctly.

**Step 4: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_proactive_agents.py tests/test_profile_repo.py -v --tb=short
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/agents/graphs/proactive/user_pattern_learner.py \
        backend/app/routes/insights.py \
        backend/app/db/repo_profile.py
git commit -m "feat(patterns): pattern learner reads real decision_events, persists results to DB"
```

---

## Task 6: Remove "Demo data" badge from frontend

**Files:**

- Modify: `frontend/components/profile/ProfilePage.tsx`
- Modify: `frontend/components/insights/UserPatternCard.tsx`

Once real data flows, the "Demo data" amber badge in the section header should be removed (it was added as a temporary marker).

**Step 1: Remove badge from ProfilePage.tsx**

In `frontend/components/profile/ProfilePage.tsx`, remove:

```typescript
          {activeSection === 'patterns' && (
            <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
              Demo data
            </span>
          )}
```

**Step 2: Optionally add empty-state guidance**

If `entries.length === 0` in `UserPatternCard.tsx`, the message already says:

> "No patterns learned yet. Make decisions across multiple ideas to build your profile."

This is the correct production empty state — no changes needed there.

**Step 3: Build frontend**

```bash
cd frontend
pnpm tsc --noEmit 2>&1 | head -10
```

Expected: no errors.

**Step 4: Commit**

```bash
git add frontend/components/profile/ProfilePage.tsx
git commit -m "feat(patterns): remove Demo data badge — real decision events now power Pattern Learner"
```
