# Decision Patterns — Real Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hardcoded mock `decision_history` in the pattern learner with real user behavior events captured from the existing workflow (DAG path confirm, feasibility plan selection, scope freeze, PRD generation), persist learned patterns to the DB, and surface them live in the Profile page.

**Architecture:**
A new `decision_events` SQLite table records one row per user action at key workflow checkpoints. The existing `UserPatternLearner` LangGraph reads from this table instead of hardcoded stubs. Learned patterns are persisted back to a new `learned_patterns_json` column in `user_preferences`. The `/insights/user-patterns` API reads from the DB first (zero LLM calls if fresh) and only re-runs the LangGraph if the events changed since last learning.

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

> Note: SQLite `ALTER TABLE … ADD COLUMN` is idempotent when wrapped in `CREATE TABLE IF NOT EXISTS` style, but here we must guard it. The actual implementation should use a `try/except` in the bootstrap code (see Task 2).

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

**Step 2: Wrap ALTER TABLE in try/except in the bootstrap function**

Find the loop that executes `SCHEMA_STATEMENTS` and add special handling:

```python
import sqlite3

def run_bootstrap(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        if statement.strip().upper().startswith("ALTER TABLE"):
            try:
                connection.execute(statement)
            except sqlite3.OperationalError:
                pass  # Column already exists — safe to ignore
        else:
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
git commit -m "fix(db): wrap ALTER TABLE in try/except during bootstrap to handle existing columns"
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

**Step 2: Add event recording to feasibility plan selection**

In `backend/app/routes/idea_agents.py`, inside `_apply_feasibility` function (around line ~896), add after context update:

```python
# At module level (near _repo = IdeaRepository()):
from app.db.repo_decision_events import DecisionEventRepository as _DecisionEventRepository
_event_repo_module = _DecisionEventRepository()
```

Then inside `stream_feasibility` (or wherever the plan selection is saved to context), after `_repo.apply_agent_update`:

```python
if selected_plan_id := context.selected_plan_id:
    plan_name = ""
    if context.feasibility:
        plan = next((p for p in context.feasibility.plans if p.id == selected_plan_id), None)
        plan_name = plan.name if plan else ""
    _event_repo_module.record(
        event_type="feasibility_plan_selected",
        idea_id=idea_id,
        payload={"plan_id": selected_plan_id, "plan_name": plan_name},
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

**Step 4: Add event at PRD generation done**

In `backend/app/routes/idea_agents.py`, inside `stream_prd` event_generator, after `yield _sse_event("done", ...)`:

```python
_event_repo_module.record(
    event_type="prd_generated",
    idea_id=idea_id,
    payload={
        "baseline_id": pack.step4_scope.baseline_meta.baseline_id,
        "requirements_count": len(merged_output.requirements),
        "backlog_count": len(merged_output.backlog.items),
    },
)
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
git add backend/app/routes/idea_dag.py backend/app/routes/idea_agents.py backend/app/routes/idea_scope.py
git commit -m "feat(patterns): instrument workflow endpoints to record decision events"
```

---

## Task 5: Update pattern learner to read real events + persist results

**Files:**

- Modify: `backend/app/agents/graphs/proactive/user_pattern_learner.py`
- Modify: `backend/app/db/repo_profile.py`

**Step 1: Extend ProfileRepository to persist learned patterns**

In `backend/app/db/repo_profile.py`, add two methods:

```python
def get_learned_patterns(self, user_id: str = "default") -> dict:
    """Return persisted learned patterns dict, or empty dict."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT learned_patterns_json FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(str(row["learned_patterns_json"]))
    except (json.JSONDecodeError, KeyError):
        return {}

def save_learned_patterns(self, user_id: str = "default", patterns: dict) -> None:
    """Upsert learned patterns dict."""
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, learned_patterns_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                learned_patterns_json = excluded.learned_patterns_json,
                updated_at = excluded.updated_at
            """,
            (user_id, json.dumps(patterns, ensure_ascii=False), now),
        )
```

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

**Step 3: Rewrite `/insights/user-patterns` endpoint to use real data**

In `backend/app/routes/insights.py`, replace `get_user_patterns`:

```python
@router.get("/user-patterns")
async def get_user_patterns():
    """Return learned user patterns.

    Fast path: return persisted patterns from DB if available.
    Slow path: run the pattern learner graph and persist results.
    """
    from app.db.repo_profile import ProfileRepository
    from app.db.repo_decision_events import DecisionEventRepository
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph

    profile_repo = ProfileRepository()
    event_repo = DecisionEventRepository()

    # Fast path: return cached patterns if we have both events and patterns
    cached = profile_repo.get_learned_patterns()
    event_count = event_repo.count_for_user()

    if cached and event_count > 0:
        return {"preferences": cached, "source": "cached", "event_count": event_count}

    # Slow path: run graph
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    return {
        "preferences": result.get("learned_preferences", {}),
        "source": "computed",
        "event_count": event_count,
    }
```

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
