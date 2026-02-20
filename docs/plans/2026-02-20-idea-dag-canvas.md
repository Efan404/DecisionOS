# Idea DAG Canvas — Design & Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the flat bubble-based IdeaCanvas with a DAG (Directed Acyclic Graph) where each node is an idea, edges represent expansion relationships, and a confirmed root-to-node path becomes the structured context for downstream stages (Feasibility → Scope → PRD).

**Architecture:**

- Backend adds two new tables (`idea_nodes`, `idea_paths`) scoped under existing `idea.id`; all existing routes and tables are untouched.
- Frontend replaces the canvas bubble layout with a React Flow DAG panel + a right-side Node Detail Panel; the three operations (browse, expand, confirm) are separated into distinct UI affordances.
- Path snapshot (`path_md` + `path_json`) is written on confirm and passed as context into subsequent stages.

**Tech Stack:** FastAPI · SQLite · React Flow (`@xyflow/react`) · Next.js App Router · Zustand · Framer Motion · Tailwind CSS · pytest · Zod

---

## Boundaries (DO NOT change)

- Do **not** modify existing `workspace`, `idea`, or `ai_settings` tables.
- Do **not** change existing `/ideas/*` or `/settings/ai` route behaviour.
- Do **not** change existing SSE envelope `{idea_id, idea_version, data}`.
- Legacy `/agents/*` routes remain `410 Gone`.

---

## Acceptance Criteria

1. User can submit a root idea → root `idea_node` is created and displayed.
2. Selecting a node opens Node Detail Panel with three actions.
3. [AI 扩展] → pick an expansion pattern → AI generates 1-3 child nodes via SSE.
4. [我来写] → inline input → AI generates child node from user description.
5. [确认路径] → `idea_paths` row written; `idea.context_json` updated; UI transitions to Feasibility.
6. All new backend endpoints have passing pytest tests.
7. No TypeScript errors (`pnpm tsc --noEmit`).
8. Responsive at 375 px and 1440 px.

---

## AI Expansion Patterns (hardcoded)

```python
EXPANSION_PATTERNS = [
    {"id": "narrow_users",    "label": "缩小用户群体",  "description": "针对更精准的细分用户群重新定义问题"},
    {"id": "expand_features", "label": "功能边界扩展",  "description": "在核心功能基础上延伸出相邻能力"},
    {"id": "shift_scenario",  "label": "场景迁移",      "description": "将此 idea 迁移至不同使用场景"},
    {"id": "monetize",        "label": "商业模式变体",  "description": "探索不同的商业化路径"},
    {"id": "simplify",        "label": "极简核心",      "description": "只保留最小可行内核，砍掉所有附加物"},
]
```

---

## Data Model

```sql
-- New table 1: individual nodes in the DAG
CREATE TABLE IF NOT EXISTS idea_nodes (
    id                TEXT PRIMARY KEY,
    idea_id           TEXT NOT NULL REFERENCES ideas(id),
    parent_id         TEXT REFERENCES idea_nodes(id),   -- NULL = root
    content           TEXT NOT NULL,
    expansion_pattern TEXT,          -- one of the 5 pattern ids, NULL for root/user-written
    edge_label        TEXT,          -- human-readable edge description
    depth             INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'active',   -- active | confirmed | pruned
    created_at        TEXT NOT NULL
);

-- New table 2: confirmed root→node path snapshots
CREATE TABLE IF NOT EXISTS idea_paths (
    id          TEXT PRIMARY KEY,
    idea_id     TEXT NOT NULL REFERENCES ideas(id),
    node_chain  TEXT NOT NULL,   -- JSON array of node ids root→leaf
    path_md     TEXT NOT NULL,   -- Markdown narrative (LLM context for next stages)
    path_json   TEXT NOT NULL,   -- Structured JSON (future cross-idea queries)
    created_at  TEXT NOT NULL
);
```

---

## API Surface (new endpoints only)

| Method | Path                                             | Description                  |
| ------ | ------------------------------------------------ | ---------------------------- |
| GET    | `/ideas/{idea_id}/nodes`                         | List all nodes for a DAG     |
| POST   | `/ideas/{idea_id}/nodes`                         | Create root node (idea_seed) |
| GET    | `/ideas/{idea_id}/nodes/{node_id}`               | Get single node              |
| POST   | `/ideas/{idea_id}/nodes/{node_id}/expand/stream` | SSE: AI-expand a node        |
| POST   | `/ideas/{idea_id}/nodes/{node_id}/expand/user`   | User-written child node      |
| POST   | `/ideas/{idea_id}/paths`                         | Confirm path, write snapshot |
| GET    | `/ideas/{idea_id}/paths/latest`                  | Get latest confirmed path    |

### SSE Expand envelope (consistent with existing pattern)

```json
{ "idea_id": "...", "idea_version": 2, "data": { "nodes": [...] } }
```

### Path snapshot `path_json` structure

```json
{
  "idea_id": "...",
  "confirmed_at": "2026-02-20T...",
  "node_chain": [
    { "id": "n1", "content": "...", "expansion_pattern": null, "edge_label": null, "depth": 0 },
    {
      "id": "n2",
      "content": "...",
      "expansion_pattern": "narrow_users",
      "edge_label": "缩小用户群体",
      "depth": 1
    },
    {
      "id": "n3",
      "content": "...",
      "expansion_pattern": "shift_scenario",
      "edge_label": "场景迁移",
      "depth": 2
    }
  ],
  "summary": "AI-generated one-paragraph summary of the reasoning chain"
}
```

---

## Frontend Component Map

```
frontend/
  components/
    idea/
      dag/
        IdeaDAGCanvas.tsx      ← replaces IdeaCanvas.tsx (keep old file, rename usage)
        NodeDetailPanel.tsx    ← right panel: browse/expand/confirm
        ExpansionPatternPicker.tsx  ← 5-card pattern selector
        UserExpandInput.tsx    ← inline textarea for user-guided expand
        DAGNode.tsx            ← custom React Flow node renderer
        DAGEdge.tsx            ← custom React Flow edge renderer
  lib/
    dag-store.ts               ← Zustand slice for node/path state
    dag-api.ts                 ← typed API calls for new endpoints
```

---

## Node Visual States

| State      | Ring                 | Fill      | Edge                   |
| ---------- | -------------------- | --------- | ---------------------- |
| default    | `#334155` 1px        | `#1E293B` | `#334155` thin         |
| hover      | `#64748B` glow       | `#1E293B` | —                      |
| selected   | `#22C55E` 2px + glow | `#0F172A` | chain → `#22C55E` bold |
| confirmed  | `#22C55E` solid fill | `#22C55E` | `#22C55E` bold locked  |
| generating | pulse animation      | `#1E293B` | dashed animate         |

---

## Task Breakdown

---

### Task 1: DB — Add `idea_nodes` and `idea_paths` tables

**Files:**

- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/bootstrap.py`
- Test: `backend/tests/test_dag_db.py` (create)

**Step 1: Write failing test**

```python
# backend/tests/test_dag_db.py
import sqlite3, os, pytest
from app.db.bootstrap import initialize_database
from app.core.settings import get_settings

def test_idea_nodes_table_exists(tmp_path):
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    get_settings.cache_clear()
    initialize_database()
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "idea_nodes" in tables
    assert "idea_paths" in tables
    conn.close()
```

**Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_dag_db.py -v
```

**Step 3: Implement** — append to `SCHEMA_STATEMENTS` list in `backend/app/db/models.py`:

```python
"""
CREATE TABLE IF NOT EXISTS idea_nodes (
    id                TEXT PRIMARY KEY,
    idea_id           TEXT NOT NULL REFERENCES ideas(id),
    parent_id         TEXT REFERENCES idea_nodes(id),
    content           TEXT NOT NULL,
    expansion_pattern TEXT,
    edge_label        TEXT,
    depth             INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'active',
    created_at        TEXT NOT NULL
);
""",
"""
CREATE TABLE IF NOT EXISTS idea_paths (
    id          TEXT PRIMARY KEY,
    idea_id     TEXT NOT NULL REFERENCES ideas(id),
    node_chain  TEXT NOT NULL,
    path_md     TEXT NOT NULL,
    path_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
""",
```

**Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_dag_db.py -v
```

**Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/test_dag_db.py
git commit -m "feat(db): add idea_nodes and idea_paths tables"
```

---

### Task 2: Backend — `repo_dag.py` repository layer

**Files:**

- Create: `backend/app/db/repo_dag.py`
- Test: `backend/tests/test_dag_repo.py` (create)

**Step 1: Write failing tests**

```python
# backend/tests/test_dag_repo.py
import os, pytest
from app.db.bootstrap import initialize_database
from app.db.engine import get_connection
from app.db import repo_dag

@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    initialize_database()

def _seed_idea():
    from app.db.repo_ideas import create_idea
    from app.db.bootstrap import get_default_workspace_id
    ws_id = get_default_workspace_id()
    return create_idea(workspace_id=ws_id, title="Test", idea_seed="seed")

def test_create_root_node():
    idea = _seed_idea()
    node = repo_dag.create_node(idea_id=idea.id, content="root content", parent_id=None)
    assert node.id is not None
    assert node.depth == 0
    assert node.parent_id is None

def test_create_child_node():
    idea = _seed_idea()
    root = repo_dag.create_node(idea_id=idea.id, content="root", parent_id=None)
    child = repo_dag.create_node(
        idea_id=idea.id, content="child", parent_id=root.id,
        expansion_pattern="narrow_users", edge_label="缩小用户群体"
    )
    assert child.depth == 1
    assert child.parent_id == root.id

def test_list_nodes():
    idea = _seed_idea()
    root = repo_dag.create_node(idea_id=idea.id, content="root", parent_id=None)
    repo_dag.create_node(idea_id=idea.id, content="child", parent_id=root.id)
    nodes = repo_dag.list_nodes(idea_id=idea.id)
    assert len(nodes) == 2

def test_create_and_get_path():
    idea = _seed_idea()
    root = repo_dag.create_node(idea_id=idea.id, content="root", parent_id=None)
    path = repo_dag.create_path(
        idea_id=idea.id,
        node_chain=[root.id],
        path_md="# Root\nroot content",
        path_json='{"node_chain": []}'
    )
    latest = repo_dag.get_latest_path(idea_id=idea.id)
    assert latest is not None
    assert latest.id == path.id
```

**Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_dag_repo.py -v
```

**Step 3: Implement** `backend/app/db/repo_dag.py`:

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Optional
from app.core.time import utcnow_iso
from app.db.engine import get_connection
import uuid

@dataclass
class IdeaNode:
    id: str
    idea_id: str
    parent_id: Optional[str]
    content: str
    expansion_pattern: Optional[str]
    edge_label: Optional[str]
    depth: int
    status: str
    created_at: str

@dataclass
class IdeaPath:
    id: str
    idea_id: str
    node_chain: list[str]
    path_md: str
    path_json: str
    created_at: str

def create_node(
    idea_id: str,
    content: str,
    parent_id: Optional[str] = None,
    expansion_pattern: Optional[str] = None,
    edge_label: Optional[str] = None,
) -> IdeaNode:
    depth = 0
    if parent_id:
        with get_connection() as conn:
            row = conn.execute("SELECT depth FROM idea_nodes WHERE id=?", (parent_id,)).fetchone()
            if row:
                depth = row[0] + 1
    node_id = str(uuid.uuid4())
    now = utcnow_iso()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO idea_nodes (id,idea_id,parent_id,content,expansion_pattern,edge_label,depth,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (node_id, idea_id, parent_id, content, expansion_pattern, edge_label, depth, "active", now)
        )
    return IdeaNode(id=node_id, idea_id=idea_id, parent_id=parent_id, content=content,
                    expansion_pattern=expansion_pattern, edge_label=edge_label,
                    depth=depth, status="active", created_at=now)

def list_nodes(idea_id: str) -> list[IdeaNode]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id,idea_id,parent_id,content,expansion_pattern,edge_label,depth,status,created_at FROM idea_nodes WHERE idea_id=? ORDER BY depth,created_at",
            (idea_id,)
        ).fetchall()
    return [IdeaNode(*r) for r in rows]

def get_node(node_id: str) -> Optional[IdeaNode]:
    with get_connection() as conn:
        r = conn.execute(
            "SELECT id,idea_id,parent_id,content,expansion_pattern,edge_label,depth,status,created_at FROM idea_nodes WHERE id=?",
            (node_id,)
        ).fetchone()
    return IdeaNode(*r) if r else None

def create_path(idea_id: str, node_chain: list[str], path_md: str, path_json: str) -> IdeaPath:
    path_id = str(uuid.uuid4())
    now = utcnow_iso()
    chain_json = json.dumps(node_chain)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO idea_paths (id,idea_id,node_chain,path_md,path_json,created_at) VALUES (?,?,?,?,?,?)",
            (path_id, idea_id, chain_json, path_md, path_json, now)
        )
    return IdeaPath(id=path_id, idea_id=idea_id, node_chain=node_chain,
                    path_md=path_md, path_json=path_json, created_at=now)

def get_latest_path(idea_id: str) -> Optional[IdeaPath]:
    with get_connection() as conn:
        r = conn.execute(
            "SELECT id,idea_id,node_chain,path_md,path_json,created_at FROM idea_paths WHERE idea_id=? ORDER BY created_at DESC LIMIT 1",
            (idea_id,)
        ).fetchone()
    if not r:
        return None
    return IdeaPath(id=r[0], idea_id=r[1], node_chain=json.loads(r[2]),
                    path_md=r[3], path_json=r[4], created_at=r[5])
```

**Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_dag_repo.py -v
```

**Step 5: Commit**

```bash
git add backend/app/db/repo_dag.py backend/tests/test_dag_repo.py
git commit -m "feat(db): add DAG repository layer (repo_dag)"
```

---

### Task 3: Backend — Pydantic schemas for DAG

**Files:**

- Create: `backend/app/schemas/dag.py`

No test needed (pure data classes) — TypeErrors surface in route tests.

**Implement** `backend/app/schemas/dag.py`:

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional

class IdeaNodeOut(BaseModel):
    id: str
    idea_id: str
    parent_id: Optional[str]
    content: str
    expansion_pattern: Optional[str]
    edge_label: Optional[str]
    depth: int
    status: str
    created_at: str

class CreateRootNodeRequest(BaseModel):
    content: str   # idea_seed text

class UserExpandRequest(BaseModel):
    description: str   # user's free-text direction

class ConfirmPathRequest(BaseModel):
    node_chain: list[str]  # ordered node ids root→leaf

class IdeaPathOut(BaseModel):
    id: str
    idea_id: str
    node_chain: list[str]
    path_md: str
    path_json: str
    created_at: str

EXPANSION_PATTERNS = [
    {"id": "narrow_users",    "label": "缩小用户群体",  "description": "针对更精准的细分用户群重新定义问题"},
    {"id": "expand_features", "label": "功能边界扩展",  "description": "在核心功能基础上延伸出相邻能力"},
    {"id": "shift_scenario",  "label": "场景迁移",      "description": "将此 idea 迁移至不同使用场景"},
    {"id": "monetize",        "label": "商业模式变体",  "description": "探索不同的商业化路径"},
    {"id": "simplify",        "label": "极简核心",      "description": "只保留最小可行内核，砍掉所有附加物"},
]
```

**Commit:**

```bash
git add backend/app/schemas/dag.py
git commit -m "feat(schema): add DAG Pydantic schemas and expansion patterns"
```

---

### Task 4: Backend — LLM prompts for node expansion

**Files:**

- Modify: `backend/app/core/prompts.py`
- Modify: `backend/app/core/mock_data.py`
- Modify: `backend/app/core/llm.py`

**Add to `prompts.py`:**

```python
def expand_node_prompt(content: str, pattern_label: str, pattern_description: str, chain_summary: str) -> str:
    return f"""You are a product thinking assistant helping explore an idea through structured lenses.

Current idea node:
{content}

Path so far:
{chain_summary}

Expansion lens: {pattern_label} — {pattern_description}

Generate 2-3 distinct child ideas that extend the current node through this lens.
Return JSON array:
[
  {{"content": "...", "edge_label": "{pattern_label}"}},
  ...
]
Only return the JSON array, no other text."""

def expand_node_user_prompt(content: str, user_direction: str, chain_summary: str) -> str:
    return f"""You are a product thinking assistant.

Current idea node:
{content}

Path so far:
{chain_summary}

User's direction: {user_direction}

Generate 1-2 child ideas that follow the user's direction.
Return JSON array:
[
  {{"content": "...", "edge_label": "<short label for the relationship>"}},
  ...
]
Only return the JSON array, no other text."""

def summarize_path_prompt(node_chain_text: str) -> str:
    return f"""Summarize this idea evolution chain in 2-3 sentences, explaining the reasoning arc from start to finish:

{node_chain_text}

Return only the summary paragraph."""
```

**Add to `mock_data.py`:**

```python
MOCK_EXPAND_NODES = [
    {"content": "Mock child idea A — narrow focus on power users", "edge_label": "缩小用户群体"},
    {"content": "Mock child idea B — extend to enterprise workflow", "edge_label": "缩小用户群体"},
]
MOCK_PATH_SUMMARY = "This idea evolved from a broad concept to a focused solution for a specific user segment, validating core assumptions along the way."
```

**Add to `llm.py`:**

```python
async def generate_expand_nodes(content: str, pattern_label: str, pattern_description: str, chain_summary: str):
    """Returns list of {content, edge_label} dicts."""
    from app.core.mock_data import MOCK_EXPAND_NODES
    from app.core.prompts import expand_node_prompt
    prompt = expand_node_prompt(content, pattern_label, pattern_description, chain_summary)
    return await generate_json(prompt, mock_fallback=MOCK_EXPAND_NODES)

async def generate_expand_node_user(content: str, user_direction: str, chain_summary: str):
    from app.core.mock_data import MOCK_EXPAND_NODES
    from app.core.prompts import expand_node_user_prompt
    prompt = expand_node_user_prompt(content, user_direction, chain_summary)
    return await generate_json(prompt, mock_fallback=MOCK_EXPAND_NODES[:1])

async def generate_path_summary(node_chain_text: str) -> str:
    from app.core.mock_data import MOCK_PATH_SUMMARY
    from app.core.prompts import summarize_path_prompt
    # Returns plain text, not JSON
    settings = get_settings()
    if settings.llm_mode == "mock":
        return MOCK_PATH_SUMMARY
    try:
        return await ai_gateway.generate_text(summarize_path_prompt(node_chain_text))
    except Exception:
        return MOCK_PATH_SUMMARY
```

**Commit:**

```bash
git add backend/app/core/prompts.py backend/app/core/mock_data.py backend/app/core/llm.py
git commit -m "feat(llm): add node expansion and path summary prompts"
```

---

### Task 5: Backend — DAG routes

**Files:**

- Create: `backend/app/routes/idea_dag.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_dag_api.py` (create)

**Step 1: Write failing tests**

```python
# backend/tests/test_dag_api.py
import os, json, pytest
from app.db.bootstrap import initialize_database
from app.core.settings import get_settings

@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["LLM_MODE"] = "mock"
    get_settings.cache_clear()
    initialize_database()

def _client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app())

def _idea(client):
    from app.db.bootstrap import get_default_workspace_id
    ws_id = get_default_workspace_id()
    r = client.post("/ideas", json={"workspace_id": ws_id, "title": "T", "idea_seed": "S"})
    return r.json()["id"]

def test_create_root_node():
    c = _client()
    idea_id = _idea(c)
    r = c.post(f"/ideas/{idea_id}/nodes", json={"content": "root idea"})
    assert r.status_code == 201
    assert r.json()["depth"] == 0

def test_list_nodes_empty():
    c = _client()
    idea_id = _idea(c)
    r = c.get(f"/ideas/{idea_id}/nodes")
    assert r.status_code == 200
    assert r.json() == []

def test_user_expand():
    c = _client()
    idea_id = _idea(c)
    root = c.post(f"/ideas/{idea_id}/nodes", json={"content": "root"}).json()
    r = c.post(f"/ideas/{idea_id}/nodes/{root['id']}/expand/user",
               json={"description": "make it for B2B"})
    assert r.status_code == 201
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["depth"] == 1

def test_confirm_path():
    c = _client()
    idea_id = _idea(c)
    root = c.post(f"/ideas/{idea_id}/nodes", json={"content": "root"}).json()
    r = c.post(f"/ideas/{idea_id}/paths", json={"node_chain": [root["id"]]})
    assert r.status_code == 201
    assert "path_md" in r.json()

def test_get_latest_path_404_when_none():
    c = _client()
    idea_id = _idea(c)
    r = c.get(f"/ideas/{idea_id}/paths/latest")
    assert r.status_code == 404

def test_node_not_found():
    c = _client()
    idea_id = _idea(c)
    r = c.post(f"/ideas/{idea_id}/nodes/nonexistent/expand/user",
               json={"description": "test"})
    assert r.status_code == 404
```

**Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_dag_api.py -v
```

**Step 3: Implement** `backend/app/routes/idea_dag.py`:

```python
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.db import repo_dag, repo_ideas
from app.schemas.dag import (
    IdeaNodeOut, CreateRootNodeRequest, UserExpandRequest,
    ConfirmPathRequest, IdeaPathOut, EXPANSION_PATTERNS
)
from app.core import llm
from app.core.time import utcnow_iso

router = APIRouter(prefix="/ideas/{idea_id}", tags=["idea-dag"])

def _require_idea(idea_id: str):
    idea = repo_ideas.get_idea(idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    if idea.status == "archived":
        raise HTTPException(409, "Idea is archived")
    return idea

def _chain_summary(idea_id: str, node_chain: list[str]) -> str:
    nodes = {n.id: n for n in repo_dag.list_nodes(idea_id)}
    parts = [nodes[nid].content for nid in node_chain if nid in nodes]
    return " → ".join(parts)

@router.get("/nodes", response_model=list[IdeaNodeOut])
def list_nodes(idea_id: str):
    _require_idea(idea_id)
    return repo_dag.list_nodes(idea_id)

@router.post("/nodes", response_model=IdeaNodeOut, status_code=201)
def create_root_node(idea_id: str, body: CreateRootNodeRequest):
    _require_idea(idea_id)
    return repo_dag.create_node(idea_id=idea_id, content=body.content)

@router.get("/nodes/{node_id}", response_model=IdeaNodeOut)
def get_node(idea_id: str, node_id: str):
    _require_idea(idea_id)
    node = repo_dag.get_node(node_id)
    if not node or node.idea_id != idea_id:
        raise HTTPException(404, "Node not found")
    return node

@router.post("/nodes/{node_id}/expand/user", response_model=list[IdeaNodeOut], status_code=201)
async def expand_user(idea_id: str, node_id: str, body: UserExpandRequest):
    _require_idea(idea_id)
    parent = repo_dag.get_node(node_id)
    if not parent or parent.idea_id != idea_id:
        raise HTTPException(404, "Node not found")
    chain = [node_id]
    summary = _chain_summary(idea_id, chain)
    children_data = await llm.generate_expand_node_user(parent.content, body.description, summary)
    results = []
    for c in children_data:
        node = repo_dag.create_node(
            idea_id=idea_id, content=c["content"],
            parent_id=node_id, edge_label=c.get("edge_label", "用户方向")
        )
        results.append(node)
    return results

@router.post("/nodes/{node_id}/expand/stream")
async def expand_stream(idea_id: str, node_id: str, pattern_id: str):
    """SSE stream: expand node with AI pattern. Query param: pattern_id"""
    _require_idea(idea_id)
    parent = repo_dag.get_node(node_id)
    if not parent or parent.idea_id != idea_id:
        raise HTTPException(404, "Node not found")
    pattern = next((p for p in EXPANSION_PATTERNS if p["id"] == pattern_id), None)
    if not pattern:
        raise HTTPException(400, f"Unknown pattern: {pattern_id}")
    chain_summary = _chain_summary(idea_id, [node_id])

    async def event_stream():
        yield f"data: {json.dumps({'type': 'progress', 'pct': 10})}\n\n"
        try:
            children_data = await llm.generate_expand_nodes(
                parent.content, pattern["label"], pattern["description"], chain_summary
            )
            yield f"data: {json.dumps({'type': 'progress', 'pct': 70})}\n\n"
            created = []
            for c in children_data:
                node = repo_dag.create_node(
                    idea_id=idea_id, content=c["content"],
                    parent_id=node_id, expansion_pattern=pattern_id,
                    edge_label=c.get("edge_label", pattern["label"])
                )
                created.append({
                    "id": node.id, "content": node.content,
                    "parent_id": node.parent_id, "depth": node.depth,
                    "edge_label": node.edge_label, "expansion_pattern": node.expansion_pattern,
                    "status": node.status, "created_at": node.created_at
                })
            yield f"data: {json.dumps({'type': 'done', 'idea_id': idea_id, 'data': {'nodes': created}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/paths", response_model=IdeaPathOut, status_code=201)
async def confirm_path(idea_id: str, body: ConfirmPathRequest):
    _require_idea(idea_id)
    nodes = {n.id: n for n in repo_dag.list_nodes(idea_id)}
    # Build markdown
    lines = ["# Idea Path\n"]
    for i, nid in enumerate(body.node_chain):
        node = nodes.get(nid)
        if node:
            prefix = "Root" if i == 0 else node.edge_label or f"Step {i}"
            lines.append(f"## {prefix}\n{node.content}\n")
    chain_text = " → ".join(nodes[nid].content for nid in body.node_chain if nid in nodes)
    summary = await llm.generate_path_summary(chain_text)
    lines.append(f"## 演进摘要\n{summary}\n")
    path_md = "\n".join(lines)
    # Build path_json
    path_json_data = {
        "idea_id": idea_id,
        "confirmed_at": utcnow_iso(),
        "node_chain": [
            {
                "id": nid,
                "content": nodes[nid].content if nid in nodes else "",
                "expansion_pattern": nodes[nid].expansion_pattern if nid in nodes else None,
                "edge_label": nodes[nid].edge_label if nid in nodes else None,
                "depth": nodes[nid].depth if nid in nodes else 0,
            }
            for nid in body.node_chain
        ],
        "summary": summary,
    }
    path = repo_dag.create_path(
        idea_id=idea_id,
        node_chain=body.node_chain,
        path_md=path_md,
        path_json=json.dumps(path_json_data, ensure_ascii=False),
    )
    return path

@router.get("/paths/latest", response_model=IdeaPathOut)
def get_latest_path(idea_id: str):
    _require_idea(idea_id)
    path = repo_dag.get_latest_path(idea_id)
    if not path:
        raise HTTPException(404, "No confirmed path yet")
    return path
```

**Add to `backend/app/main.py`:**

```python
from app.routes.idea_dag import router as idea_dag_router
# in create_app():
app.include_router(idea_dag_router)
```

**Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_dag_api.py -v
```

**Step 5: Run full test suite — must stay green**

```bash
cd backend && uv run pytest -v
```

**Step 6: Commit**

```bash
git add backend/app/routes/idea_dag.py backend/app/main.py backend/tests/test_dag_api.py
git commit -m "feat(api): add DAG node and path endpoints"
```

---

### Task 6: Frontend — Zustand DAG store + API client

**Files:**

- Create: `frontend/lib/dag-api.ts`
- Create: `frontend/lib/dag-store.ts`

**`frontend/lib/dag-api.ts`:**

```typescript
import { buildApiUrl } from './api'

export interface IdeaNode {
  id: string
  idea_id: string
  parent_id: string | null
  content: string
  expansion_pattern: string | null
  edge_label: string | null
  depth: number
  status: string
  created_at: string
}

export interface IdeaPath {
  id: string
  idea_id: string
  node_chain: string[]
  path_md: string
  path_json: string
  created_at: string
}

export const EXPANSION_PATTERNS = [
  { id: 'narrow_users', label: '缩小用户群体', description: '针对更精准的细分用户群重新定义问题' },
  { id: 'expand_features', label: '功能边界扩展', description: '在核心功能基础上延伸出相邻能力' },
  { id: 'shift_scenario', label: '场景迁移', description: '将此 idea 迁移至不同使用场景' },
  { id: 'monetize', label: '商业模式变体', description: '探索不同的商业化路径' },
  { id: 'simplify', label: '极简核心', description: '只保留最小可行内核，砍掉所有附加物' },
] as const

export async function listNodes(ideaId: string): Promise<IdeaNode[]> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes`))
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function createRootNode(ideaId: string, content: string): Promise<IdeaNode> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function expandUserNode(
  ideaId: string,
  nodeId: string,
  description: string
): Promise<IdeaNode[]> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes/${nodeId}/expand/user`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function confirmPath(ideaId: string, nodeChain: string[]): Promise<IdeaPath> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/paths`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_chain: nodeChain }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getLatestPath(ideaId: string): Promise<IdeaPath | null> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/paths/latest`))
  if (r.status === 404) return null
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
```

**`frontend/lib/dag-store.ts`:**

```typescript
import { create } from 'zustand'
import type { IdeaNode, IdeaPath } from './dag-api'

interface DAGState {
  nodes: IdeaNode[]
  selectedNodeId: string | null
  confirmedPath: IdeaPath | null
  expandingNodeId: string | null // which node is currently generating children
  // actions
  setNodes: (nodes: IdeaNode[]) => void
  addNodes: (nodes: IdeaNode[]) => void
  selectNode: (id: string | null) => void
  setConfirmedPath: (path: IdeaPath) => void
  setExpandingNode: (id: string | null) => void
  reset: () => void
}

export const useDAGStore = create<DAGState>((set) => ({
  nodes: [],
  selectedNodeId: null,
  confirmedPath: null,
  expandingNodeId: null,
  setNodes: (nodes) => set({ nodes }),
  addNodes: (nodes) => set((s) => ({ nodes: [...s.nodes, ...nodes] })),
  selectNode: (id) => set({ selectedNodeId: id }),
  setConfirmedPath: (path) => set({ confirmedPath: path }),
  setExpandingNode: (id) => set({ expandingNodeId: id }),
  reset: () => set({ nodes: [], selectedNodeId: null, confirmedPath: null, expandingNodeId: null }),
}))
```

**Verify TypeScript:**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

**Commit:**

```bash
git add frontend/lib/dag-api.ts frontend/lib/dag-store.ts
git commit -m "feat(frontend): add DAG API client and Zustand store"
```

---

### Task 7: Frontend — DAG canvas components

**Files:**

- Create: `frontend/components/idea/dag/DAGNode.tsx`
- Create: `frontend/components/idea/dag/DAGEdge.tsx`
- Create: `frontend/components/idea/dag/ExpansionPatternPicker.tsx`
- Create: `frontend/components/idea/dag/NodeDetailPanel.tsx`
- Create: `frontend/components/idea/dag/IdeaDAGCanvas.tsx`

Install React Flow if not present:

```bash
cd frontend && pnpm add @xyflow/react
```

**`DAGNode.tsx`** — custom React Flow node:

```tsx
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { cn } from '@/lib/utils'

export type DAGNodeData = {
  content: string
  status: 'active' | 'confirmed' | 'generating'
  isSelected: boolean
  isOnSelectedPath: boolean
}

export function DAGNode({ data }: NodeProps) {
  const d = data as DAGNodeData
  return (
    <div
      className={cn(
        'relative max-w-[200px] cursor-pointer rounded-xl border px-4 py-3 text-sm transition-all duration-200',
        'bg-[#0F172A] text-[#F8FAFC]',
        d.isSelected
          ? 'border-[#22C55E] shadow-[0_0_16px_rgba(34,197,94,0.4)]'
          : d.isOnSelectedPath
            ? 'border-[#22C55E]/50'
            : 'border-[#334155] hover:border-[#64748B] hover:shadow-md',
        d.status === 'confirmed' && 'border-[#22C55E] bg-[#22C55E]/10',
        d.status === 'generating' && 'animate-pulse border-dashed border-[#334155]'
      )}
    >
      <p className="line-clamp-3 leading-snug">{d.content}</p>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-[#334155]" />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !border-0 !bg-[#334155]"
      />
    </div>
  )
}
```

**`DAGEdge.tsx`** — custom edge:

```tsx
import { BaseEdge, EdgeLabelRenderer, getStraightPath, type EdgeProps } from '@xyflow/react'

export function DAGEdge({ id, sourceX, sourceY, targetX, targetY, data, markerEnd }: EdgeProps) {
  const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const isHighlighted = (data as any)?.isHighlighted
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: isHighlighted ? '#22C55E' : '#334155',
          strokeWidth: isHighlighted ? 2 : 1,
        }}
      />
      {(data as any)?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)`,
            }}
            className="pointer-events-none rounded bg-[#0F172A] px-1 text-[10px] text-[#64748B]"
          >
            {(data as any).label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
```

**`ExpansionPatternPicker.tsx`:**

```tsx
import { EXPANSION_PATTERNS } from '@/lib/dag-api'

interface Props {
  onSelect: (patternId: string) => void
  loading?: boolean
}

export function ExpansionPatternPicker({ onSelect, loading }: Props) {
  return (
    <div className="grid grid-cols-1 gap-2">
      {EXPANSION_PATTERNS.map((p) => (
        <button
          key={p.id}
          onClick={() => onSelect(p.id)}
          disabled={loading}
          className="cursor-pointer rounded-lg border border-[#334155] px-3 py-2.5 text-left transition-all duration-150 hover:border-[#22C55E] hover:bg-[#22C55E]/5 disabled:opacity-50"
        >
          <div className="text-sm font-medium text-[#F8FAFC]">{p.label}</div>
          <div className="mt-0.5 text-xs text-[#64748B]">{p.description}</div>
        </button>
      ))}
    </div>
  )
}
```

**`NodeDetailPanel.tsx`:**

```tsx
'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExpansionPatternPicker } from './ExpansionPatternPicker'
import type { IdeaNode } from '@/lib/dag-api'

type PanelMode = 'idle' | 'ai-expand' | 'user-expand'

interface Props {
  node: IdeaNode | null
  pathChain: string[] // root → this node
  onExpandAI: (patternId: string) => Promise<void>
  onExpandUser: (description: string) => Promise<void>
  onConfirmPath: () => Promise<void>
  isConfirmed: boolean
  loading: boolean
}

export function NodeDetailPanel({
  node,
  pathChain,
  onExpandAI,
  onExpandUser,
  onConfirmPath,
  isConfirmed,
  loading,
}: Props) {
  const [mode, setMode] = useState<PanelMode>('idle')
  const [userInput, setUserInput] = useState('')

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[#64748B]">
        点击节点查看详情
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex h-full flex-col gap-4 p-4"
    >
      {/* Node content */}
      <div>
        <div className="mb-1 text-xs text-[#64748B]">
          {node.edge_label ?? '根节点'} · 深度 {node.depth}
        </div>
        <p className="text-sm leading-relaxed text-[#F8FAFC]">{node.content}</p>
      </div>

      {/* Path breadcrumb */}
      <div className="text-xs text-[#475569]">链路长度：{pathChain.length} 跳</div>

      <div className="border-t border-[#1E293B]" />

      {/* Actions */}
      <AnimatePresence mode="wait">
        {mode === 'idle' && (
          <motion.div key="idle" className="flex flex-col gap-2">
            <button
              onClick={() => setMode('ai-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#22C55E] disabled:opacity-50"
            >
              ⚡ AI 扩展
            </button>
            <button
              onClick={() => setMode('user-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#64748B] disabled:opacity-50"
            >
              ✏ 我来写方向
            </button>
          </motion.div>
        )}

        {mode === 'ai-expand' && (
          <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="mb-2 text-xs text-[#64748B]">选择扩展维度</div>
            <ExpansionPatternPicker
              onSelect={async (id) => {
                await onExpandAI(id)
                setMode('idle')
              }}
              loading={loading}
            />
            <button
              onClick={() => setMode('idle')}
              className="mt-2 cursor-pointer text-xs text-[#475569] hover:text-[#64748B]"
            >
              取消
            </button>
          </motion.div>
        )}

        {mode === 'user-expand' && (
          <motion.div
            key="user"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col gap-2"
          >
            <textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="描述你想探索的方向..."
              rows={3}
              className="w-full resize-none rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] placeholder-[#475569] focus:border-[#64748B] focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (userInput.trim()) {
                    await onExpandUser(userInput)
                    setUserInput('')
                    setMode('idle')
                  }
                }}
                disabled={loading || !userInput.trim()}
                className="flex-1 cursor-pointer rounded-lg border border-[#22C55E]/40 bg-[#22C55E]/10 py-2 text-sm text-[#22C55E] transition-all hover:bg-[#22C55E]/20 disabled:opacity-50"
              >
                生成
              </button>
              <button
                onClick={() => setMode('idle')}
                className="cursor-pointer rounded-lg border border-[#334155] px-3 py-2 text-sm text-[#64748B] hover:border-[#64748B]"
              >
                取消
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-auto">
        <button
          onClick={onConfirmPath}
          disabled={loading || isConfirmed}
          className="w-full cursor-pointer rounded-lg bg-[#22C55E] px-3 py-2.5 text-sm font-semibold text-[#0F172A] transition-all hover:bg-[#16A34A] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isConfirmed ? '路径已确认 ✓' : '→ 确认此路径'}
        </button>
        {!isConfirmed && (
          <p className="mt-1 text-center text-xs text-[#475569]">确认后进入 Feasibility 分析</p>
        )}
      </div>
    </motion.div>
  )
}
```

**`IdeaDAGCanvas.tsx`** — main canvas:

```tsx
'use client'
import { useCallback, useEffect, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useDAGStore } from '@/lib/dag-store'
import {
  listNodes,
  createRootNode,
  expandUserNode,
  confirmPath,
  type IdeaNode,
} from '@/lib/dag-api'
import { DAGNode, type DAGNodeData } from './DAGNode'
import { DAGEdge } from './DAGEdge'
import { NodeDetailPanel } from './NodeDetailPanel'

const nodeTypes = { dagNode: DAGNode }
const edgeTypes = { dagEdge: DAGEdge }

function buildPathChain(nodes: IdeaNode[], targetId: string): string[] {
  const map = new Map(nodes.map((n) => [n.id, n]))
  const chain: string[] = []
  let cur: IdeaNode | undefined = map.get(targetId)
  while (cur) {
    chain.unshift(cur.id)
    cur = cur.parent_id ? map.get(cur.parent_id) : undefined
  }
  return chain
}

interface Props {
  ideaId: string
  ideaSeed: string
}

export function IdeaDAGCanvas({ ideaId, ideaSeed }: Props) {
  const {
    nodes: dagNodes,
    selectedNodeId,
    confirmedPath,
    expandingNodeId,
    setNodes,
    addNodes,
    selectNode,
    setConfirmedPath,
    setExpandingNode,
  } = useDAGStore()

  const [rfNodes, setRFNodes, onNodesChange] = useNodesState<Node>([])
  const [rfEdges, setRFEdges, onEdgesChange] = useEdgesState<Edge>([])

  const selectedPathChain = useMemo(() => {
    if (!selectedNodeId) return []
    return buildPathChain(dagNodes, selectedNodeId)
  }, [dagNodes, selectedNodeId])

  // Convert DAG nodes to React Flow nodes/edges
  useEffect(() => {
    const LEVEL_HEIGHT = 140,
      NODE_WIDTH = 220
    const byDepth: Record<number, IdeaNode[]> = {}
    dagNodes.forEach((n) => {
      ;(byDepth[n.depth] ??= []).push(n)
    })

    const newRFNodes: Node[] = dagNodes.map((n) => {
      const siblings = byDepth[n.depth] ?? []
      const idx = siblings.indexOf(n)
      const x = (idx - (siblings.length - 1) / 2) * (NODE_WIDTH + 32)
      const y = n.depth * LEVEL_HEIGHT
      const data: DAGNodeData = {
        content: n.content,
        status: n.id === expandingNodeId ? 'generating' : (n.status as any),
        isSelected: n.id === selectedNodeId,
        isOnSelectedPath: selectedPathChain.includes(n.id),
      }
      return { id: n.id, type: 'dagNode', position: { x, y }, data }
    })

    const newRFEdges: Edge[] = dagNodes
      .filter((n) => n.parent_id)
      .map((n) => ({
        id: `e-${n.parent_id}-${n.id}`,
        source: n.parent_id!,
        target: n.id,
        type: 'dagEdge',
        data: {
          label: n.edge_label,
          isHighlighted:
            selectedPathChain.includes(n.parent_id!) && selectedPathChain.includes(n.id),
        },
      }))

    setRFNodes(newRFNodes)
    setRFEdges(newRFEdges)
  }, [dagNodes, selectedNodeId, selectedPathChain, expandingNodeId])

  // Init: load or create root node
  useEffect(() => {
    ;(async () => {
      const existing = await listNodes(ideaId)
      if (existing.length > 0) {
        setNodes(existing)
      } else {
        const root = await createRootNode(ideaId, ideaSeed)
        setNodes([root])
      }
    })()
  }, [ideaId])

  const handleNodeClick = useCallback(
    (_: any, node: Node) => {
      selectNode(node.id)
    },
    [selectNode]
  )

  const handleExpandAI = async (patternId: string) => {
    if (!selectedNodeId) return
    setExpandingNode(selectedNodeId)
    // Use SSE stream
    const url = `/api/ideas/${ideaId}/nodes/${selectedNodeId}/expand/stream?pattern_id=${patternId}`
    const es = new EventSource(url)
    es.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'done') {
        addNodes(msg.data.nodes)
        setExpandingNode(null)
        es.close()
      } else if (msg.type === 'error') {
        setExpandingNode(null)
        es.close()
      }
    }
    es.onerror = () => {
      setExpandingNode(null)
      es.close()
    }
  }

  const handleExpandUser = async (description: string) => {
    if (!selectedNodeId) return
    setExpandingNode(selectedNodeId)
    try {
      const newNodes = await expandUserNode(ideaId, selectedNodeId, description)
      addNodes(newNodes)
    } finally {
      setExpandingNode(null)
    }
  }

  const handleConfirmPath = async () => {
    if (!selectedNodeId) return
    const path = await confirmPath(ideaId, selectedPathChain)
    setConfirmedPath(path)
  }

  const selectedNode = dagNodes.find((n) => n.id === selectedNodeId) ?? null

  return (
    <div className="flex h-full w-full bg-[#0F172A]">
      {/* Canvas */}
      <div className="relative flex-1">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          className="bg-[#0F172A]"
        >
          <Background color="#1E293B" gap={24} />
          <Controls className="!border-[#334155] !bg-[#1E293B]" />
        </ReactFlow>
      </div>

      {/* Detail panel */}
      <div className="w-72 flex-shrink-0 border-l border-[#1E293B] bg-[#0A0F1A]">
        <NodeDetailPanel
          node={selectedNode}
          pathChain={selectedPathChain}
          onExpandAI={handleExpandAI}
          onExpandUser={handleExpandUser}
          onConfirmPath={handleConfirmPath}
          isConfirmed={confirmedPath !== null}
          loading={expandingNodeId !== null}
        />
      </div>
    </div>
  )
}
```

**Verify TypeScript:**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

**Commit:**

```bash
git add frontend/components/idea/dag/
git commit -m "feat(frontend): add IdeaDAGCanvas and NodeDetailPanel components"
```

---

### Task 8: Frontend — Wire DAGCanvas into idea-canvas page

**Files:**

- Modify: `frontend/app/ideas/[ideaId]/idea-canvas/page.tsx`

Read the current file first, then replace the IdeaCanvas import/usage with IdeaDAGCanvas:

```tsx
// Replace old IdeaCanvas with:
import { IdeaDAGCanvas } from '@/components/idea/dag/IdeaDAGCanvas'

// In the page component, pass ideaId and ideaSeed:
;<IdeaDAGCanvas ideaId={idea.id} ideaSeed={idea.idea_seed} />
```

The page must already fetch the idea (has `idea.id` and `idea.idea_seed`). If not, add:

```tsx
const idea = await getIdea(params.ideaId) // from lib/api.ts
```

**Verify build:**

```bash
cd frontend && pnpm build 2>&1 | tail -20
```

**Commit:**

```bash
git add frontend/app/ideas/
git commit -m "feat(frontend): wire IdeaDAGCanvas into idea-canvas route"
```

---

### Task 9: Review checkpoint — run full verification

```bash
# Backend: all tests
cd backend && uv run pytest -v

# Frontend: type check
cd frontend && pnpm tsc --noEmit

# Frontend: build
cd frontend && pnpm build

# Manual smoke test (backend running):
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/ideas \
  -H "Content-Type: application/json" \
  -d '{"workspace_id":"default","title":"Test","idea_seed":"Build a habit tracker"}' | jq .
```

Expected:

- All pytest tests PASS (including pre-existing tests)
- `tsc --noEmit` exits 0
- `pnpm build` exits 0

---

## Running the project

```bash
# Backend
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && pnpm dev

# Run all backend tests
cd backend && uv run pytest -v

# Type check frontend
cd frontend && pnpm tsc --noEmit
```

## Environment variables

| Variable                | Default                           | Notes                   |
| ----------------------- | --------------------------------- | ----------------------- |
| `LLM_MODE`              | `auto`                            | Set to `mock` for tests |
| `DECISIONOS_DB_PATH`    | `./decisionos.db`                 | SQLite file path        |
| `DECISIONOS_SECRET_KEY` | `decisionos-dev-secret-change-me` | Encryption key          |
