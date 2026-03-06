# Multi-Agent + Memory System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LangGraph multi-agent orchestration, memory/RAG system, and proactive agent capabilities to DecisionOS for hackathon demo.

**Architecture:** LangGraph orchestration layer on top of existing `ai_gateway.py`. Each LangGraph Node wraps existing `ai_gateway.generate_structured()` calls. Memory uses LangGraph Checkpointer (thread state) + Store (cross-session). RAG uses ChromaDB embedded. Existing routes, schemas, and DB layer remain unchanged.

**Tech Stack:** LangGraph + langchain-core + ChromaDB + existing FastAPI/Pydantic/SSE stack.

**Design Doc:** `docs/plans/2026-03-06-multi-agent-memory-hackathon-design.md`

---

### Task 1: Install Dependencies and Verify Environment

**Files:**

- Modify: `backend/requirements.txt`

**Step 1: Add new dependencies to requirements.txt**

Append to `backend/requirements.txt`:

```
langgraph>=0.3.0
langgraph-checkpoint-sqlite>=2.0.0
chromadb>=0.5.0
```

**Step 2: Install dependencies**

Run: `cd backend && pip install -r requirements.txt`
Expected: All packages install successfully. `langgraph` pulls in `langchain-core` as transitive dep.

**Step 3: Verify imports work**

Run: `cd backend && python -c "from langgraph.graph import StateGraph; from langgraph.checkpoint.sqlite import SqliteSaver; import chromadb; print('OK')"`
Expected: prints `OK`

**Step 4: Verify existing tests still pass**

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All existing tests PASS (new deps don't break anything).

**Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add langgraph and chromadb dependencies"
```

---

### Task 2: LangGraph State Schema + Checkpointer Setup

**Files:**

- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/state.py`
- Create: `backend/app/agents/checkpointer.py`
- Test: `backend/tests/test_agent_state.py`

**Step 1: Write failing test for state schema and checkpointer**

```python
# backend/tests/test_agent_state.py
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.agents.state import DecisionOSState, AgentThought
from app.agents.checkpointer import get_checkpointer


def test_state_schema_defaults():
    """DecisionOSState can be constructed with minimal required fields."""
    state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "An AI tool",
        "current_stage": "opportunity",
        "opportunity_output": None,
        "dag_path": None,
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }
    assert state["idea_id"] == "test-id"
    assert state["agent_thoughts"] == []


def test_agent_thought_structure():
    """AgentThought TypedDict has expected fields."""
    thought: AgentThought = {
        "agent": "researcher",
        "action": "analyzing",
        "detail": "Found 2 similar ideas",
        "timestamp": "2026-03-06T00:00:00Z",
    }
    assert thought["agent"] == "researcher"


def test_checkpointer_creates_sqlite():
    """get_checkpointer returns a working SqliteSaver."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_checkpoint.db")
        saver = get_checkpointer(db_path)
        assert saver is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_agent_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents'`

**Step 3: Implement state schema and checkpointer**

```python
# backend/app/agents/__init__.py
```

```python
# backend/app/agents/state.py
from __future__ import annotations

from typing import TypedDict, Annotated
from langgraph.graph import add_messages


class AgentThought(TypedDict):
    agent: str      # e.g. "researcher", "critic", "memory_writer"
    action: str     # e.g. "retrieving_similar_ideas", "evaluating"
    detail: str     # human-readable description of what happened
    timestamp: str  # ISO 8601


class DecisionOSState(TypedDict):
    # Core identifiers
    idea_id: str
    idea_seed: str
    current_stage: str  # "opportunity" | "feasibility" | "scope" | "prd"

    # Stage outputs (set by each stage's agent nodes)
    opportunity_output: dict | None
    dag_path: dict | None
    feasibility_output: dict | None
    selected_plan_id: str | None
    scope_output: dict | None
    prd_output: dict | None

    # Agent working memory — visible to frontend via SSE
    agent_thoughts: Annotated[list[AgentThought], add_messages]

    # Memory retrieval results (injected from Store / vector DB)
    retrieved_patterns: list[dict]
    retrieved_similar_ideas: list[dict]
    user_preferences: dict | None
```

```python
# backend/app/agents/checkpointer.py
from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver


def get_checkpointer(db_path: str = "decisionos_checkpoints.db") -> SqliteSaver:
    """Create a SQLite-backed checkpointer for LangGraph thread state."""
    return SqliteSaver.from_conn_string(db_path)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_agent_state.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/app/agents/ backend/tests/test_agent_state.py
git commit -m "feat(agents): add LangGraph state schema and checkpointer setup"
```

---

### Task 3: ChromaDB Vector Store + Seed Data

**Files:**

- Create: `backend/app/agents/memory/__init__.py`
- Create: `backend/app/agents/memory/vector_store.py`
- Create: `backend/app/agents/memory/seed_data.py`
- Test: `backend/tests/test_vector_store.py`

**Step 1: Write failing test for vector store**

```python
# backend/tests/test_vector_store.py
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.agents.memory.vector_store import VectorStore


def test_vector_store_add_and_query():
    """VectorStore can add documents and query by similarity."""
    vs = VectorStore(persist_directory=None)  # in-memory for tests
    vs.add_idea_summary(idea_id="idea-1", summary="AI-powered code review tool for developers")
    vs.add_idea_summary(idea_id="idea-2", summary="Recipe recommendation app for home cooks")
    vs.add_idea_summary(idea_id="idea-3", summary="Developer productivity dashboard with metrics")

    results = vs.search_similar_ideas(query="code analysis for software engineers", n_results=2)
    assert len(results) == 2
    # idea-1 and idea-3 should be more relevant than idea-2
    result_ids = [r["idea_id"] for r in results]
    assert "idea-1" in result_ids


def test_vector_store_add_news_and_match():
    """VectorStore can store news and match against ideas."""
    vs = VectorStore(persist_directory=None)
    vs.add_idea_summary(idea_id="idea-1", summary="AI-powered code review tool")
    vs.add_news_item(
        news_id="news-1",
        title="GitHub launches AI code review feature",
        content="GitHub announced a new AI-powered code review feature today.",
    )

    matches = vs.match_news_to_ideas(news_id="news-1", n_results=2)
    assert len(matches) >= 1
    assert matches[0]["idea_id"] == "idea-1"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_vector_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.memory'`

**Step 3: Implement VectorStore wrapper around ChromaDB**

```python
# backend/app/agents/memory/__init__.py
```

```python
# backend/app/agents/memory/vector_store.py
from __future__ import annotations

import logging
from typing import Any

import chromadb

logger = logging.getLogger(__name__)

# Module-level singleton (lazy init)
_instance: VectorStore | None = None


class VectorStore:
    """Thin wrapper around ChromaDB for idea/news vector similarity."""

    def __init__(self, persist_directory: str | None = "./chroma_data") -> None:
        if persist_directory is None:
            self._client = chromadb.Client()  # in-memory
        else:
            self._client = chromadb.PersistentClient(path=persist_directory)

        self._ideas = self._client.get_or_create_collection(
            name="idea_summaries",
            metadata={"hnsw:space": "cosine"},
        )
        self._news = self._client.get_or_create_collection(
            name="news_items",
            metadata={"hnsw:space": "cosine"},
        )
        self._patterns = self._client.get_or_create_collection(
            name="decision_patterns",
            metadata={"hnsw:space": "cosine"},
        )

    def add_idea_summary(self, *, idea_id: str, summary: str) -> None:
        self._ideas.upsert(
            ids=[idea_id],
            documents=[summary],
            metadatas=[{"idea_id": idea_id}],
        )
        logger.info("vector_store.add_idea idea_id=%s chars=%d", idea_id, len(summary))

    def search_similar_ideas(
        self, query: str, n_results: int = 3, exclude_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results = self._ideas.query(query_texts=[query], n_results=n_results + 1)
        out: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            if exclude_id and doc_id == exclude_id:
                continue
            out.append({
                "idea_id": doc_id,
                "summary": results["documents"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return out[:n_results]

    def add_news_item(self, *, news_id: str, title: str, content: str) -> None:
        self._news.upsert(
            ids=[news_id],
            documents=[f"{title}. {content}"],
            metadatas=[{"news_id": news_id, "title": title}],
        )

    def match_news_to_ideas(self, news_id: str, n_results: int = 3) -> list[dict[str, Any]]:
        news_result = self._news.get(ids=[news_id], include=["documents"])
        if not news_result["documents"]:
            return []
        news_text = news_result["documents"][0]
        results = self._ideas.query(query_texts=[news_text], n_results=n_results)
        out: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            out.append({
                "idea_id": doc_id,
                "summary": results["documents"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return out

    def add_decision_pattern(self, *, pattern_id: str, description: str) -> None:
        self._patterns.upsert(
            ids=[pattern_id],
            documents=[description],
            metadatas=[{"pattern_id": pattern_id}],
        )

    def search_patterns(self, query: str, n_results: int = 3) -> list[dict[str, Any]]:
        if self._patterns.count() == 0:
            return []
        results = self._patterns.query(query_texts=[query], n_results=n_results)
        out: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            out.append({
                "pattern_id": doc_id,
                "description": results["documents"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return out


def get_vector_store() -> VectorStore:
    global _instance
    if _instance is None:
        _instance = VectorStore()
    return _instance
```

```python
# backend/app/agents/memory/seed_data.py
"""Pre-seeded demo data for hackathon presentation.

Run: python -m app.agents.memory.seed_data
"""
from __future__ import annotations

DEMO_IDEAS = [
    {
        "id": "demo-idea-1",
        "seed": "AI-powered code review tool",
        "summary": (
            "An AI-powered code review tool that automatically analyzes pull requests, "
            "detects bugs, suggests improvements, and enforces coding standards. "
            "Targets development teams of 5-50 engineers. B2B SaaS model."
        ),
    },
    {
        "id": "demo-idea-2",
        "seed": "Developer productivity dashboard",
        "summary": (
            "A dashboard that aggregates developer activity across GitHub, Jira, and Slack "
            "to provide insights on team productivity, bottlenecks, and code health metrics. "
            "Targets engineering managers. B2B SaaS with per-seat pricing."
        ),
    },
    {
        "id": "demo-idea-3",
        "seed": "AI tutoring platform for programming",
        "summary": (
            "An interactive AI tutoring platform that teaches programming through personalized "
            "exercises, real-time code feedback, and adaptive learning paths. "
            "Targets self-taught developers and bootcamp students. B2C freemium model."
        ),
    },
    {
        "id": "demo-idea-4",
        "seed": "Smart meeting summarizer",
        "summary": (
            "An AI tool that joins video meetings, transcribes discussions, extracts action items, "
            "and generates structured meeting notes with follow-up reminders. "
            "Targets remote teams. B2B SaaS with tiered pricing."
        ),
    },
    {
        "id": "demo-idea-5",
        "seed": "Open-source dependency risk analyzer",
        "summary": (
            "A tool that scans project dependencies for security vulnerabilities, license conflicts, "
            "and maintenance risks, providing actionable risk scores and remediation advice. "
            "Targets DevSecOps teams. Open-core model."
        ),
    },
]

DEMO_NEWS = [
    {
        "id": "news-1",
        "title": "GitHub Launches AI-Powered Code Review Feature",
        "content": (
            "GitHub announced Copilot Code Review, a new AI-powered feature that automatically "
            "reviews pull requests and suggests improvements. The feature is available for "
            "GitHub Enterprise users and supports multiple programming languages."
        ),
    },
    {
        "id": "news-2",
        "title": "Stack Overflow Survey: 70% of Developers Use AI Tools Daily",
        "content": (
            "The latest Stack Overflow developer survey reveals that 70% of professional "
            "developers now use AI-assisted coding tools daily, up from 44% last year. "
            "Code completion and bug detection are the most popular use cases."
        ),
    },
    {
        "id": "news-3",
        "title": "Remote Work Fatigue: Teams Report 30% More Meetings Post-Pandemic",
        "content": (
            "A new study shows remote and hybrid teams spend 30% more time in meetings compared "
            "to pre-pandemic levels. Companies are increasingly looking for tools to reduce "
            "meeting overhead and improve async communication."
        ),
    },
    {
        "id": "news-4",
        "title": "Critical Log4j-Style Vulnerability Found in Popular NPM Package",
        "content": (
            "Security researchers discovered a critical vulnerability in a widely-used NPM package "
            "with over 10 million weekly downloads. The incident highlights the ongoing challenges "
            "of open-source supply chain security."
        ),
    },
    {
        "id": "news-5",
        "title": "AI Education Market Expected to Reach $20B by 2027",
        "content": (
            "The AI-powered education technology market is projected to reach $20 billion by 2027, "
            "driven by demand for personalized learning experiences and coding education. "
            "Adaptive learning platforms are the fastest-growing segment."
        ),
    },
]

DEMO_PATTERNS = [
    {
        "id": "pattern-1",
        "description": (
            "User prefers B2B SaaS models over B2C. In 3 out of 4 ideas, the user chose "
            "business-focused positioning with per-seat or tiered pricing."
        ),
    },
    {
        "id": "pattern-2",
        "description": (
            "User tends to choose bootstrapped/capital-light approaches over VC-funded growth. "
            "In feasibility analysis, the user selected the bootstrapped plan 2 out of 3 times."
        ),
    },
    {
        "id": "pattern-3",
        "description": (
            "User values technical feasibility over market size when evaluating plans. "
            "Selected plans consistently have higher technical_feasibility scores."
        ),
    },
]


def seed_vector_store() -> None:
    """Populate vector store with demo data for hackathon presentation."""
    from app.agents.memory.vector_store import get_vector_store

    vs = get_vector_store()
    for idea in DEMO_IDEAS:
        vs.add_idea_summary(idea_id=idea["id"], summary=idea["summary"])
    for news in DEMO_NEWS:
        vs.add_news_item(news_id=news["id"], title=news["title"], content=news["content"])
    for pattern in DEMO_PATTERNS:
        vs.add_decision_pattern(pattern_id=pattern["id"], description=pattern["description"])
    print(f"Seeded {len(DEMO_IDEAS)} ideas, {len(DEMO_NEWS)} news, {len(DEMO_PATTERNS)} patterns")


if __name__ == "__main__":
    seed_vector_store()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_vector_store.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/agents/memory/ backend/tests/test_vector_store.py
git commit -m "feat(agents): add ChromaDB vector store with seed data for demo"
```

---

### Task 4: Opportunity Subgraph — First LangGraph Integration

This is the critical task: wrap the existing opportunity generation in a multi-agent LangGraph graph. The subgraph has 4 nodes: ContextLoader → Researcher → DirectionGenerator → MemoryWriter.

**Files:**

- Create: `backend/app/agents/nodes/__init__.py`
- Create: `backend/app/agents/nodes/context_loader.py`
- Create: `backend/app/agents/nodes/memory_writer.py`
- Create: `backend/app/agents/graphs/__init__.py`
- Create: `backend/app/agents/graphs/opportunity_subgraph.py`
- Test: `backend/tests/test_opportunity_graph.py`

**Step 1: Write failing test for opportunity subgraph**

```python
# backend/tests/test_opportunity_graph.py
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import patch, MagicMock

from app.agents.state import DecisionOSState
from app.agents.graphs.opportunity_subgraph import build_opportunity_graph


def _mock_generate_structured(**kwargs):
    """Mock ai_gateway.generate_structured for opportunity."""
    from app.schemas.common import Direction
    from app.schemas.idea import OpportunityOutput
    return OpportunityOutput(
        directions=[
            Direction(id="A", title="Direction A", one_liner="One-liner A", pain_tags=["tag1"]),
            Direction(id="B", title="Direction B", one_liner="One-liner B", pain_tags=["tag2"]),
            Direction(id="C", title="Direction C", one_liner="One-liner C", pain_tags=["tag3"]),
        ]
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_opportunity_graph_produces_output_and_thoughts(mock_gen):
    """Opportunity subgraph produces directions + agent thoughts."""
    graph = build_opportunity_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "opportunity",
        "opportunity_output": None,
        "dag_path": None,
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    result = graph.invoke(initial_state)

    # Should have opportunity output
    assert result["opportunity_output"] is not None
    assert len(result["opportunity_output"]["directions"]) == 3

    # Should have agent thoughts from each node
    assert len(result["agent_thoughts"]) >= 2  # at least context_loader + generator
    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "context_loader" in agents
    assert "direction_generator" in agents
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_opportunity_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.nodes'`

**Step 3: Implement the nodes and subgraph**

```python
# backend/app/agents/nodes/__init__.py
```

```python
# backend/app/agents/nodes/context_loader.py
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.agents.memory.vector_store import get_vector_store
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def context_loader_node(state: DecisionOSState) -> dict:
    """Load relevant context from vector store and memory for the current stage."""
    idea_seed = state["idea_seed"]
    idea_id = state["idea_id"]

    vs = get_vector_store()
    similar = vs.search_similar_ideas(query=idea_seed, n_results=3, exclude_id=idea_id)
    patterns = vs.search_patterns(query=idea_seed, n_results=3)

    similar_summary = f"Found {len(similar)} similar ideas" if similar else "No similar ideas in memory"
    pattern_summary = f"Found {len(patterns)} decision patterns" if patterns else "No prior patterns"

    thought: AgentThought = {
        "agent": "context_loader",
        "action": "retrieving_context",
        "detail": f"{similar_summary}, {pattern_summary}",
        "timestamp": utc_now_iso(),
    }

    logger.info("context_loader idea_id=%s similar=%d patterns=%d", idea_id, len(similar), len(patterns))

    return {
        "retrieved_similar_ideas": similar,
        "retrieved_patterns": patterns,
        "agent_thoughts": [thought],
    }
```

```python
# backend/app/agents/nodes/memory_writer.py
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.agents.memory.vector_store import get_vector_store
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def memory_writer_node(state: DecisionOSState) -> dict:
    """Write stage outputs to long-term memory (vector store)."""
    idea_id = state["idea_id"]
    idea_seed = state["idea_seed"]
    stage = state["current_stage"]

    vs = get_vector_store()
    written_items: list[str] = []

    if stage == "opportunity" and state.get("opportunity_output"):
        directions = state["opportunity_output"].get("directions", [])
        summary = f"Idea: {idea_seed}. Directions: " + "; ".join(
            d.get("title", "") for d in directions if isinstance(d, dict)
        )
        vs.add_idea_summary(idea_id=idea_id, summary=summary)
        written_items.append("idea_summary")

    if stage == "feasibility" and state.get("feasibility_output"):
        plans = state["feasibility_output"].get("plans", [])
        pattern_desc = f"Idea '{idea_seed}' feasibility: {len(plans)} plans generated"
        if state.get("selected_plan_id"):
            pattern_desc += f", selected plan: {state['selected_plan_id']}"
        vs.add_decision_pattern(pattern_id=f"{idea_id}-feasibility", description=pattern_desc)
        written_items.append("decision_pattern")

    detail = f"Saved to long-term memory: {', '.join(written_items)}" if written_items else "No new items to save"
    thought: AgentThought = {
        "agent": "memory_writer",
        "action": "saving_to_memory",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    logger.info("memory_writer idea_id=%s stage=%s items=%s", idea_id, stage, written_items)
    return {"agent_thoughts": [thought]}
```

```python
# backend/app/agents/graphs/__init__.py
```

```python
# backend/app/agents/graphs/opportunity_subgraph.py
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.agents.state import DecisionOSState, AgentThought
from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.core import ai_gateway, prompts
from app.core.time import utc_now_iso
from app.schemas.idea import OpportunityOutput

logger = logging.getLogger(__name__)


def _researcher_node(state: DecisionOSState) -> dict:
    """Analyze idea seed with retrieved context to build enriched prompt context."""
    similar = state.get("retrieved_similar_ideas", [])
    patterns = state.get("retrieved_patterns", [])

    analysis_parts: list[str] = []
    if similar:
        analysis_parts.append(
            "Similar ideas found: " + "; ".join(
                f"'{s.get('summary', '')[:80]}'" for s in similar[:3]
            )
        )
    if patterns:
        analysis_parts.append(
            "Relevant patterns: " + "; ".join(
                p.get("description", "")[:80] for p in patterns[:3]
            )
        )

    detail = ". ".join(analysis_parts) if analysis_parts else "No prior context found, generating from scratch"

    thought: AgentThought = {
        "agent": "researcher",
        "action": "analyzing_context",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    return {"agent_thoughts": [thought]}


def _direction_generator_node(state: DecisionOSState) -> dict:
    """Generate opportunity directions using existing ai_gateway."""
    idea_seed = state["idea_seed"]
    similar = state.get("retrieved_similar_ideas", [])
    patterns = state.get("retrieved_patterns", [])

    # Build enriched prompt with memory context
    base_prompt = prompts.build_opportunity_prompt(idea_seed=idea_seed, count=3)
    memory_context_parts: list[str] = []
    if similar:
        memory_context_parts.append(
            "Previously explored similar ideas: " + "; ".join(
                s.get("summary", "")[:100] for s in similar[:2]
            ) + ". Generate DIFFERENT directions that don't overlap."
        )
    if patterns:
        for p in patterns[:2]:
            memory_context_parts.append(f"User pattern: {p.get('description', '')[:120]}")

    enriched_prompt = base_prompt
    if memory_context_parts:
        enriched_prompt += "\n\nContext from memory:\n" + "\n".join(memory_context_parts)

    output: OpportunityOutput = ai_gateway.generate_structured(
        task="opportunity",
        user_prompt=enriched_prompt,
        schema_model=OpportunityOutput,
    )

    thought: AgentThought = {
        "agent": "direction_generator",
        "action": "generated_directions",
        "detail": f"Generated {len(output.directions)} directions for '{idea_seed[:50]}'",
        "timestamp": utc_now_iso(),
    }

    return {
        "opportunity_output": output.model_dump(),
        "agent_thoughts": [thought],
    }


def build_opportunity_graph() -> StateGraph:
    """Build a compiled opportunity subgraph: ContextLoader → Researcher → Generator → MemoryWriter."""
    graph = StateGraph(DecisionOSState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("researcher", _researcher_node)
    graph.add_node("direction_generator", _direction_generator_node)
    graph.add_node("memory_writer", memory_writer_node)

    graph.add_edge(START, "context_loader")
    graph.add_edge("context_loader", "researcher")
    graph.add_edge("researcher", "direction_generator")
    graph.add_edge("direction_generator", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_opportunity_graph.py -v`
Expected: PASS

**Step 5: Verify existing tests are unbroken**

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/app/agents/nodes/ backend/app/agents/graphs/ backend/tests/test_opportunity_graph.py
git commit -m "feat(agents): implement opportunity subgraph with context loader and memory writer"
```

---

### Task 5: SSE Streaming for Agent Thoughts

Wire the LangGraph opportunity subgraph into a new SSE streaming endpoint that emits `agent_thought` events alongside existing `progress`/`partial`/`done` events.

**Files:**

- Create: `backend/app/agents/stream.py`
- Modify: `backend/app/routes/idea_agents.py` (add new route)
- Test: `backend/tests/test_opportunity_stream.py`

**Step 1: Write failing test for agent-thought SSE stream**

```python
# backend/tests/test_opportunity_stream.py
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from tests._test_env import ensure_required_seed_env
ensure_required_seed_env()

from app.agents.stream import run_opportunity_graph_sse
from app.agents.state import DecisionOSState


def _mock_generate_structured(**kwargs):
    from app.schemas.common import Direction
    from app.schemas.idea import OpportunityOutput
    return OpportunityOutput(
        directions=[
            Direction(id="A", title="Dir A", one_liner="One-liner A", pain_tags=["t1"]),
            Direction(id="B", title="Dir B", one_liner="One-liner B", pain_tags=["t2"]),
        ]
    )


class TestOpportunityStreamSSE(unittest.TestCase):

    @patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
    def test_stream_emits_agent_thoughts_and_done(self, mock_gen):
        """SSE stream from opportunity graph emits agent_thought and done events."""
        events: list[dict] = []

        async def collect():
            async for event in run_opportunity_graph_sse(
                idea_id="test-id",
                idea_seed="AI tool",
            ):
                events.append(event)

        asyncio.get_event_loop().run_until_complete(collect())

        event_types = [e["event"] for e in events]
        assert "agent_thought" in event_types, f"Expected agent_thought, got {event_types}"
        assert "done" in event_types, f"Expected done event, got {event_types}"

        # done event should have opportunity_output
        done_event = next(e for e in events if e["event"] == "done")
        done_data = json.loads(done_event["data"])
        assert "opportunity_output" in done_data
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_opportunity_stream.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.stream'`

**Step 3: Implement the SSE streaming bridge**

```python
# backend/app/agents/stream.py
"""Bridge between LangGraph graph execution and SSE event emission."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.agents.state import DecisionOSState
from app.agents.graphs.opportunity_subgraph import build_opportunity_graph

logger = logging.getLogger(__name__)


def _sse_event(event: str, payload: dict) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


async def run_opportunity_graph_sse(
    *,
    idea_id: str,
    idea_seed: str,
) -> AsyncIterator[dict[str, str]]:
    """Run the opportunity subgraph and yield SSE events for each agent thought."""
    graph = build_opportunity_graph()

    initial_state: DecisionOSState = {
        "idea_id": idea_id,
        "idea_seed": idea_seed,
        "current_stage": "opportunity",
        "opportunity_output": None,
        "dag_path": None,
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    yield _sse_event("progress", {"step": "starting_agents", "pct": 5})

    # Run graph node-by-node via stream to capture intermediate state
    seen_thoughts = 0
    pct = 10
    async for event in graph.astream(initial_state, stream_mode="updates"):
        # event is a dict of {node_name: state_update}
        for node_name, update in event.items():
            thoughts = update.get("agent_thoughts", [])
            for thought in thoughts[seen_thoughts:]:
                pct = min(90, pct + 15)
                yield _sse_event("agent_thought", {
                    "agent": thought.get("agent", node_name),
                    "action": thought.get("action", "processing"),
                    "detail": thought.get("detail", ""),
                    "pct": pct,
                })
            seen_thoughts = 0  # reset per node since each update is per-node

            # If this node produced the final output, capture it
            if "opportunity_output" in update and update["opportunity_output"] is not None:
                final_output = update["opportunity_output"]

    yield _sse_event("progress", {"step": "saving", "pct": 95})

    yield _sse_event("done", {
        "idea_id": idea_id,
        "opportunity_output": final_output if 'final_output' in dir() else None,
    })
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_opportunity_stream.py -v`
Expected: PASS

**Step 5: Add the new SSE route to idea_agents.py**

Add after the existing `stream_opportunity` route in `backend/app/routes/idea_agents.py` (around line 304):

```python
@router.post("/opportunity/stream/v2")
async def stream_opportunity_v2(idea_id: str, payload: OpportunityIdeaRequest) -> EventSourceResponse:
    """Multi-agent opportunity generation with agent thought streaming."""
    _logger.info("agent.opportunity.stream.v2.start idea_id=%s version=%s", idea_id, payload.version)

    from app.agents.stream import run_opportunity_graph_sse

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in run_opportunity_graph_sse(
                idea_id=idea_id,
                idea_seed=payload.idea_seed,
            ):
                yield event

                # If this is the done event, persist to DB
                if event.get("event") == "done":
                    done_data = json.loads(event["data"])
                    opp_output = done_data.get("opportunity_output")
                    if opp_output:
                        from app.schemas.idea import OpportunityOutput
                        output = OpportunityOutput.model_validate(opp_output)
                        result = _repo.apply_agent_update(
                            idea_id,
                            version=payload.version,
                            mutate_context=lambda context: _apply_opportunity(context, payload, output),
                            allow_conflict_retry=True,
                        )
                        error_payload = _sse_error_payload(result)
                        if error_payload is not None:
                            yield _sse_event("error", error_payload)
                            return
                        assert result.idea is not None
                        yield _sse_event("done", {
                            "idea_id": idea_id,
                            "idea_version": result.idea.version,
                            "data": output.model_dump(),
                        })
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.opportunity.stream.v2.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "AGENT_ERROR", "message": str(exc)})

    return EventSourceResponse(event_generator())
```

**Step 6: Run all tests**

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add backend/app/agents/stream.py backend/app/routes/idea_agents.py backend/tests/test_opportunity_stream.py
git commit -m "feat(agents): add SSE streaming bridge for multi-agent opportunity generation"
```

---

### Task 6: Feasibility Subgraph — Parallel Plans + Synthesizer + Pattern Matcher

**Files:**

- Create: `backend/app/agents/graphs/feasibility_subgraph.py`
- Create: `backend/app/agents/nodes/plan_synthesizer.py`
- Create: `backend/app/agents/nodes/pattern_matcher.py`
- Modify: `backend/app/agents/stream.py` (add feasibility SSE)
- Modify: `backend/app/routes/idea_agents.py` (add v2 route)
- Test: `backend/tests/test_feasibility_graph.py`

**Step 1: Write failing test**

```python
# backend/tests/test_feasibility_graph.py
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.feasibility_subgraph import build_feasibility_graph


def _mock_generate_structured(**kwargs):
    schema_model = kwargs.get("schema_model")
    if schema_model is None:
        schema_model = kwargs.get("schema_model")

    from app.schemas.common import ScoreBreakdown, ReasoningBreakdown
    from app.schemas.feasibility import Plan

    # Check if we're generating a single Plan
    if schema_model == Plan or (hasattr(schema_model, "__name__") and schema_model.__name__ == "Plan"):
        return Plan(
            id="plan1",
            name="Bootstrap Plan",
            summary="Low-cost MVP approach",
            score_overall=8.0,
            scores=ScoreBreakdown(technical_feasibility=8.0, market_viability=7.5, execution_risk=7.0),
            reasoning=ReasoningBreakdown(
                technical_feasibility="Feasible", market_viability="Good", execution_risk="Moderate"
            ),
            recommended_positioning="B2B SaaS",
        )
    # Fallback
    return Plan(
        id="plan1", name="Plan", summary="Summary", score_overall=7.0,
        scores=ScoreBreakdown(technical_feasibility=7.0, market_viability=7.0, execution_risk=7.0),
        reasoning=ReasoningBreakdown(technical_feasibility="ok", market_viability="ok", execution_risk="ok"),
        recommended_positioning="Position",
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_feasibility_graph_produces_plans_and_synthesis(mock_gen):
    """Feasibility subgraph generates plans and runs synthesizer."""
    graph = build_feasibility_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "feasibility",
        "opportunity_output": None,
        "dag_path": {"path_summary": "From idea to code review focus"},
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    result = graph.invoke(initial_state)

    assert result["feasibility_output"] is not None
    plans = result["feasibility_output"]["plans"]
    assert len(plans) == 3

    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "plan_synthesizer" in agents
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_feasibility_graph.py -v`
Expected: FAIL

**Step 3: Implement plan_synthesizer, pattern_matcher, and feasibility subgraph**

```python
# backend/app/agents/nodes/plan_synthesizer.py
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def plan_synthesizer_node(state: DecisionOSState) -> dict:
    """Cross-evaluate and rank the generated plans, add synthesis commentary."""
    plans = state.get("feasibility_output", {}).get("plans", []) if state.get("feasibility_output") else []

    if not plans:
        thought: AgentThought = {
            "agent": "plan_synthesizer",
            "action": "no_plans_to_synthesize",
            "detail": "No plans available for synthesis",
            "timestamp": utc_now_iso(),
        }
        return {"agent_thoughts": [thought]}

    # Sort plans by score_overall descending
    sorted_plans = sorted(plans, key=lambda p: p.get("score_overall", 0), reverse=True)
    best = sorted_plans[0]

    detail = (
        f"Analyzed {len(plans)} plans. "
        f"Recommended: '{best.get('name', 'Unknown')}' (score: {best.get('score_overall', 0)}). "
        f"Key strength: {best.get('recommended_positioning', 'N/A')}"
    )

    thought: AgentThought = {
        "agent": "plan_synthesizer",
        "action": "synthesized_plans",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    # Update feasibility_output with sorted plans
    updated_output = dict(state["feasibility_output"])
    updated_output["plans"] = sorted_plans

    logger.info("plan_synthesizer idea_id=%s best=%s", state["idea_id"], best.get("name"))
    return {"feasibility_output": updated_output, "agent_thoughts": [thought]}
```

```python
# backend/app/agents/nodes/pattern_matcher.py
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.agents.memory.vector_store import get_vector_store
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def pattern_matcher_node(state: DecisionOSState) -> dict:
    """Match current stage output against historical decision patterns."""
    idea_seed = state["idea_seed"]
    stage = state["current_stage"]

    vs = get_vector_store()
    patterns = vs.search_patterns(query=f"{idea_seed} {stage}", n_results=3)

    if not patterns:
        thought: AgentThought = {
            "agent": "pattern_matcher",
            "action": "no_patterns_found",
            "detail": "No historical patterns found for this idea type",
            "timestamp": utc_now_iso(),
        }
        return {"agent_thoughts": [thought]}

    pattern_descriptions = "; ".join(p.get("description", "")[:80] for p in patterns)
    thought: AgentThought = {
        "agent": "pattern_matcher",
        "action": "matched_patterns",
        "detail": f"Found {len(patterns)} relevant patterns: {pattern_descriptions}",
        "timestamp": utc_now_iso(),
    }

    logger.info("pattern_matcher idea_id=%s matched=%d", state["idea_id"], len(patterns))
    return {"retrieved_patterns": patterns, "agent_thoughts": [thought]}
```

```python
# backend/app/agents/graphs/feasibility_subgraph.py
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.agents.state import DecisionOSState, AgentThought
from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.agents.nodes.plan_synthesizer import plan_synthesizer_node
from app.agents.nodes.pattern_matcher import pattern_matcher_node
from app.core import ai_gateway, prompts
from app.core.time import utc_now_iso
from app.schemas.feasibility import Plan, FeasibilityOutput

logger = logging.getLogger(__name__)

_PLAN_ARCHETYPES = [
    "a bootstrapped / capital-light approach",
    "a VC-funded / growth-first approach",
    "a platform / ecosystem / partner-led approach",
]


def _plan_generator_node(state: DecisionOSState) -> dict:
    """Generate 3 feasibility plans (sequential, each with different archetype)."""
    idea_seed = state["idea_seed"]
    dag_path = state.get("dag_path") or {}
    path_summary = dag_path.get("path_summary", "")
    node_content = dag_path.get("leaf_node_content", idea_seed)

    plans: list[dict] = []
    thoughts: list[AgentThought] = []

    for i, archetype in enumerate(_PLAN_ARCHETYPES):
        prompt = prompts.build_single_plan_prompt(
            idea_seed=idea_seed,
            confirmed_node_content=node_content,
            confirmed_path_summary=path_summary,
            plan_index=i,
        )

        # Enrich with memory context
        patterns = state.get("retrieved_patterns", [])
        if patterns:
            prompt += "\n\nHistorical patterns from similar ideas:\n" + "\n".join(
                f"- {p.get('description', '')[:120]}" for p in patterns[:2]
            )

        plan: Plan = ai_gateway.generate_structured(
            task="feasibility",
            user_prompt=prompt,
            schema_model=Plan,
        )
        plan.id = f"plan{i + 1}"
        plans.append(plan.model_dump())

        thoughts.append({
            "agent": "plan_generator",
            "action": f"generated_plan_{i+1}",
            "detail": f"Generated '{plan.name}' ({archetype}) — score: {plan.score_overall}",
            "timestamp": utc_now_iso(),
        })

    output = FeasibilityOutput(
        plans=[Plan.model_validate(p) for p in plans]
    )

    return {
        "feasibility_output": output.model_dump(),
        "agent_thoughts": thoughts,
    }


def build_feasibility_graph() -> StateGraph:
    """Build feasibility subgraph: ContextLoader → PlanGenerator → Synthesizer → PatternMatcher → MemoryWriter."""
    graph = StateGraph(DecisionOSState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("plan_generator", _plan_generator_node)
    graph.add_node("plan_synthesizer", plan_synthesizer_node)
    graph.add_node("pattern_matcher", pattern_matcher_node)
    graph.add_node("memory_writer", memory_writer_node)

    graph.add_edge(START, "context_loader")
    graph.add_edge("context_loader", "plan_generator")
    graph.add_edge("plan_generator", "plan_synthesizer")
    graph.add_edge("plan_synthesizer", "pattern_matcher")
    graph.add_edge("pattern_matcher", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
```

**Step 4: Add feasibility SSE to stream.py and route**

Append to `backend/app/agents/stream.py`:

```python
from app.agents.graphs.feasibility_subgraph import build_feasibility_graph


async def run_feasibility_graph_sse(
    *,
    idea_id: str,
    idea_seed: str,
    confirmed_path_summary: str = "",
    confirmed_node_content: str = "",
) -> AsyncIterator[dict[str, str]]:
    """Run feasibility subgraph and yield SSE events."""
    graph = build_feasibility_graph()

    initial_state: DecisionOSState = {
        "idea_id": idea_id,
        "idea_seed": idea_seed,
        "current_stage": "feasibility",
        "opportunity_output": None,
        "dag_path": {
            "path_summary": confirmed_path_summary,
            "leaf_node_content": confirmed_node_content,
        },
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    yield _sse_event("progress", {"step": "starting_agents", "pct": 5})

    final_output = None
    pct = 10
    async for event in graph.astream(initial_state, stream_mode="updates"):
        for node_name, update in event.items():
            thoughts = update.get("agent_thoughts", [])
            for thought in thoughts:
                pct = min(90, pct + 8)
                yield _sse_event("agent_thought", {
                    "agent": thought.get("agent", node_name),
                    "action": thought.get("action", "processing"),
                    "detail": thought.get("detail", ""),
                    "pct": pct,
                })

            if "feasibility_output" in update and update["feasibility_output"] is not None:
                final_output = update["feasibility_output"]
                # Emit partial plans as they arrive
                for plan in final_output.get("plans", []):
                    yield _sse_event("partial", {"plan": plan})

    yield _sse_event("done", {
        "idea_id": idea_id,
        "feasibility_output": final_output,
    })
```

Add route to `backend/app/routes/idea_agents.py` after the v2 opportunity route:

```python
@router.post("/feasibility/stream/v2")
async def stream_feasibility_v2(idea_id: str, payload: FeasibilityIdeaRequest) -> EventSourceResponse:
    """Multi-agent feasibility generation with agent thought streaming."""
    _logger.info("agent.feasibility.stream.v2.start idea_id=%s", idea_id)

    from app.agents.stream import run_feasibility_graph_sse

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in run_feasibility_graph_sse(
                idea_id=idea_id,
                idea_seed=payload.idea_seed,
                confirmed_path_summary=payload.confirmed_path_summary or "",
                confirmed_node_content=payload.confirmed_node_content or "",
            ):
                yield event
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.feasibility.stream.v2.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "AGENT_ERROR", "message": str(exc)})

    return EventSourceResponse(event_generator())
```

**Step 5: Run test**

Run: `cd backend && python -m pytest tests/test_feasibility_graph.py tests/test_opportunity_graph.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/agents/ backend/tests/test_feasibility_graph.py backend/app/routes/idea_agents.py
git commit -m "feat(agents): add feasibility subgraph with plan synthesizer and pattern matcher"
```

---

### Task 7: PRD Subgraph — Writer + Reviewer + Memory

**Files:**

- Create: `backend/app/agents/graphs/prd_subgraph.py`
- Create: `backend/app/agents/nodes/critic.py`
- Modify: `backend/app/agents/stream.py` (add PRD SSE)
- Modify: `backend/app/routes/idea_agents.py` (add v2 route)
- Test: `backend/tests/test_prd_graph.py`

This follows the same pattern as Tasks 4-6. The PRD subgraph has: ContextLoader → PRDWriter → PRDReviewer (critic) → MemoryWriter.

**Step 1: Write failing test**

```python
# backend/tests/test_prd_graph.py
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.prd_subgraph import build_prd_graph


def _mock_generate_structured(**kwargs):
    from app.schemas.prd import PRDMarkdownOutput
    return PRDMarkdownOutput(
        markdown="# Test PRD\n\nThis is a test PRD.",
        sections=[{"id": "s1", "title": "Executive Summary", "content": "Test content."}],
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_prd_graph_produces_markdown_and_review(mock_gen):
    """PRD subgraph generates markdown and runs critic review."""
    graph = build_prd_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "prd",
        "opportunity_output": None,
        "dag_path": {"path_summary": "From idea to code review"},
        "feasibility_output": {"plans": [{"name": "Bootstrap", "summary": "Low cost"}]},
        "selected_plan_id": "plan1",
        "scope_output": {"in_scope": [{"title": "Core review"}], "out_scope": []},
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    result = graph.invoke(initial_state)

    assert result["prd_output"] is not None
    assert "markdown" in result["prd_output"]
    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "prd_writer" in agents
    assert "prd_reviewer" in agents
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prd_graph.py -v`
Expected: FAIL

**Step 3: Implement critic node and PRD subgraph**

```python
# backend/app/agents/nodes/critic.py
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def prd_reviewer_node(state: DecisionOSState) -> dict:
    """Review the generated PRD against scope and provide quality assessment."""
    prd = state.get("prd_output", {})
    scope = state.get("scope_output", {})

    markdown = prd.get("markdown", "") if prd else ""
    in_scope = scope.get("in_scope", []) if scope else []

    # Simple quality checks (in a real system, this would be another LLM call)
    issues: list[str] = []
    if len(markdown) < 200:
        issues.append("PRD is unusually short")
    if in_scope:
        scope_titles = {item.get("title", "").lower() for item in in_scope if isinstance(item, dict)}
        md_lower = markdown.lower()
        missing = [t for t in scope_titles if t and t not in md_lower]
        if missing:
            issues.append(f"{len(missing)} scope items not mentioned in PRD")

    if issues:
        detail = f"Review found {len(issues)} issues: {'; '.join(issues)}"
    else:
        detail = "PRD passed quality review: all scope items covered, sufficient detail"

    thought: AgentThought = {
        "agent": "prd_reviewer",
        "action": "quality_review",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    logger.info("prd_reviewer idea_id=%s issues=%d", state["idea_id"], len(issues))
    return {"agent_thoughts": [thought]}
```

```python
# backend/app/agents/graphs/prd_subgraph.py
from __future__ import annotations

import json
import logging

from langgraph.graph import StateGraph, START, END

from app.agents.state import DecisionOSState, AgentThought
from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.critic import prd_reviewer_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.core import ai_gateway, prompts
from app.core.time import utc_now_iso
from app.schemas.prd import PRDMarkdownOutput

logger = logging.getLogger(__name__)


def _prd_writer_node(state: DecisionOSState) -> dict:
    """Generate PRD markdown using existing ai_gateway, enriched with memory context."""
    idea_seed = state["idea_seed"]
    dag_path = state.get("dag_path") or {}
    feasibility = state.get("feasibility_output") or {}
    scope = state.get("scope_output") or {}
    selected_plan_id = state.get("selected_plan_id", "")

    # Build slim context similar to llm._build_slim_prd_context
    plans = feasibility.get("plans", [])
    selected_plan = next((p for p in plans if p.get("id") == selected_plan_id), plans[0] if plans else {})

    slim_context = {
        "idea_seed": idea_seed,
        "confirmed_path_summary": dag_path.get("path_summary", ""),
        "leaf_node_content": dag_path.get("leaf_node_content", idea_seed),
        "selected_plan": {
            "name": selected_plan.get("name", ""),
            "summary": selected_plan.get("summary", ""),
            "score_overall": selected_plan.get("score_overall", 0),
            "recommended_positioning": selected_plan.get("recommended_positioning", ""),
        },
        "in_scope": scope.get("in_scope", []),
        "out_scope": scope.get("out_scope", []),
    }

    # Enrich with memory
    similar = state.get("retrieved_similar_ideas", [])
    patterns = state.get("retrieved_patterns", [])

    prompt = prompts.build_prd_markdown_prompt(context=slim_context)
    if similar:
        prompt += "\n\nSimilar ideas for reference:\n" + "\n".join(
            f"- {s.get('summary', '')[:100]}" for s in similar[:2]
        )
    if patterns:
        prompt += "\n\nUser patterns:\n" + "\n".join(
            f"- {p.get('description', '')[:120]}" for p in patterns[:2]
        )

    result: PRDMarkdownOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompt,
        schema_model=PRDMarkdownOutput,
    )

    thought: AgentThought = {
        "agent": "prd_writer",
        "action": "generated_prd",
        "detail": f"Generated PRD with {len(result.sections)} sections ({len(result.markdown)} chars)",
        "timestamp": utc_now_iso(),
    }

    return {
        "prd_output": {"markdown": result.markdown, "sections": [s if isinstance(s, dict) else s for s in result.sections]},
        "agent_thoughts": [thought],
    }


def build_prd_graph() -> StateGraph:
    """Build PRD subgraph: ContextLoader → PRDWriter → PRDReviewer → MemoryWriter."""
    graph = StateGraph(DecisionOSState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("prd_writer", _prd_writer_node)
    graph.add_node("prd_reviewer", prd_reviewer_node)
    graph.add_node("memory_writer", memory_writer_node)

    graph.add_edge(START, "context_loader")
    graph.add_edge("context_loader", "prd_writer")
    graph.add_edge("prd_writer", "prd_reviewer")
    graph.add_edge("prd_reviewer", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
```

Add PRD SSE to `backend/app/agents/stream.py` and corresponding v2 route to `idea_agents.py` (same pattern as feasibility).

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_prd_graph.py tests/ -x -q`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/agents/ backend/tests/test_prd_graph.py backend/app/routes/idea_agents.py
git commit -m "feat(agents): add PRD subgraph with writer, reviewer, and memory integration"
```

---

### Task 8: Proactive Agents — News Monitor + Cross-Idea Analyzer

**Files:**

- Create: `backend/app/agents/graphs/proactive/__init__.py`
- Create: `backend/app/agents/graphs/proactive/news_monitor.py`
- Create: `backend/app/agents/graphs/proactive/cross_idea_analyzer.py`
- Create: `backend/app/agents/graphs/proactive/user_pattern_learner.py`
- Create: `backend/app/routes/notifications.py`
- Create: `backend/app/routes/insights.py`
- Create: `backend/app/db/repo_notifications.py`
- Modify: `backend/app/db/models.py` (add notification + agent_trace tables)
- Modify: `backend/app/db/bootstrap.py` (initialize new tables)
- Modify: `backend/app/main.py` (register new routers)
- Test: `backend/tests/test_proactive_agents.py`

**Step 1: Write failing test**

```python
# backend/tests/test_proactive_agents.py
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import patch

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph


def _mock_generate_text(**kwargs):
    return '{"insight": "This news is relevant to your AI code review idea because it validates market demand."}'


def _mock_generate_structured(**kwargs):
    """Generic mock that returns a dict-like object with model_dump."""
    class MockOutput:
        def model_dump(self):
            return {"summary": "Cross-idea analysis complete"}
    return MockOutput()


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
def test_news_monitor_graph_runs(mock_text):
    """News monitor graph executes without errors and produces notifications."""
    graph = build_news_monitor_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_ids": ["demo-idea-1", "demo-idea-2"],
        "notifications": [],
        "agent_thoughts": [],
    })
    assert "notifications" in result


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
def test_cross_idea_graph_runs(mock_text):
    """Cross-idea analyzer graph executes and produces insights."""
    graph = build_cross_idea_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [
            {"idea_id": "1", "summary": "AI code review"},
            {"idea_id": "2", "summary": "Developer dashboard"},
        ],
        "insights": [],
        "agent_thoughts": [],
    })
    assert "insights" in result


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
def test_pattern_learner_graph_runs(mock_text):
    """Pattern learner graph executes and produces learned preferences."""
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI tool"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    assert "learned_preferences" in result
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_proactive_agents.py -v`
Expected: FAIL

**Step 3: Implement DB schema changes**

Add to end of `SCHEMA_STATEMENTS` tuple in `backend/app/db/models.py`:

```python
    """
    CREATE TABLE IF NOT EXISTS notification (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        type TEXT NOT NULL CHECK (type IN ('news_match', 'cross_idea_insight', 'pattern_learned')),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        read_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_trace (
        id TEXT PRIMARY KEY,
        idea_id TEXT,
        graph_name TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        node_name TEXT NOT NULL,
        input_json TEXT,
        output_json TEXT,
        duration_ms INTEGER,
        created_at TEXT NOT NULL
    );
    """,
```

**Step 4: Implement notification repo**

```python
# backend/app/db/repo_notifications.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass
class NotificationRecord:
    id: str
    user_id: str
    type: str
    title: str
    body: str
    metadata_json: str
    read_at: str | None
    created_at: str


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
                "SELECT * FROM notification WHERE user_id = ? AND read_at IS NULL "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [NotificationRecord(**dict(r)) for r in rows]

    def list_all(self, user_id: str = "default", limit: int = 50) -> list[NotificationRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM notification WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [NotificationRecord(**dict(r)) for r in rows]

    def dismiss(self, notification_id: str) -> bool:
        now = utc_now_iso()
        with db_session() as conn:
            cursor = conn.execute(
                "UPDATE notification SET read_at = ? WHERE id = ? AND read_at IS NULL",
                (now, notification_id),
            )
        return cursor.rowcount > 0
```

**Step 5: Implement proactive agent graphs**

Each graph is a small LangGraph StateGraph. They use pre-seeded data from the vector store and `ai_gateway.generate_text()` for LLM analysis.

```python
# backend/app/agents/graphs/proactive/__init__.py
```

```python
# backend/app/agents/graphs/proactive/news_monitor.py
from __future__ import annotations

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, add_messages
from app.agents.memory.vector_store import get_vector_store
from app.core import ai_gateway
from app.core.time import utc_now_iso


class NewsMonitorState(TypedDict):
    user_id: str
    idea_ids: list[str]
    notifications: list[dict]
    agent_thoughts: Annotated[list[dict], add_messages]


def _fetch_news(state: NewsMonitorState) -> dict:
    vs = get_vector_store()
    # Get all news items from vector store
    all_news = vs._news.get(include=["documents", "metadatas"])
    thought = {
        "agent": "news_fetcher",
        "action": "fetched_news",
        "detail": f"Retrieved {len(all_news['ids'])} news articles from database",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _match_news_to_ideas(state: NewsMonitorState) -> dict:
    vs = get_vector_store()
    all_news = vs._news.get(include=["documents", "metadatas"])
    notifications: list[dict] = []

    for i, news_id in enumerate(all_news["ids"]):
        matches = vs.match_news_to_ideas(news_id=news_id, n_results=2)
        for match in matches:
            if match.get("distance", 1.0) < 0.5:  # relevance threshold
                notifications.append({
                    "type": "news_match",
                    "news_id": news_id,
                    "news_title": all_news["metadatas"][i].get("title", ""),
                    "idea_id": match["idea_id"],
                    "idea_summary": match.get("summary", ""),
                    "relevance": 1.0 - match.get("distance", 0),
                })

    thought = {
        "agent": "news_matcher",
        "action": "matched_news",
        "detail": f"Found {len(notifications)} relevant news-idea matches",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": notifications, "agent_thoughts": [thought]}


def _generate_insights(state: NewsMonitorState) -> dict:
    notifications = state.get("notifications", [])
    enriched: list[dict] = []

    for notif in notifications[:5]:  # limit LLM calls for demo
        try:
            raw = ai_gateway.generate_text(
                task="opportunity",
                user_prompt=(
                    f"A news article titled '{notif.get('news_title', '')}' is relevant to an idea about "
                    f"'{notif.get('idea_summary', '')[:100]}'. "
                    "In 1-2 sentences, explain why this news matters for this idea and suggest one action. "
                    "Return plain text, no JSON."
                ),
            )
            notif["insight"] = raw.strip()
        except Exception:
            notif["insight"] = "This news article may be relevant to your idea."
        enriched.append(notif)

    thought = {
        "agent": "insight_generator",
        "action": "generated_insights",
        "detail": f"Generated insights for {len(enriched)} news matches",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": enriched, "agent_thoughts": [thought]}


def build_news_monitor_graph():
    graph = StateGraph(NewsMonitorState)
    graph.add_node("fetch_news", _fetch_news)
    graph.add_node("match_to_ideas", _match_news_to_ideas)
    graph.add_node("generate_insights", _generate_insights)
    graph.add_edge(START, "fetch_news")
    graph.add_edge("fetch_news", "match_to_ideas")
    graph.add_edge("match_to_ideas", "generate_insights")
    graph.add_edge("generate_insights", END)
    return graph.compile()
```

```python
# backend/app/agents/graphs/proactive/cross_idea_analyzer.py
from __future__ import annotations

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, add_messages
from app.agents.memory.vector_store import get_vector_store
from app.core import ai_gateway
from app.core.time import utc_now_iso


class CrossIdeaState(TypedDict):
    user_id: str
    idea_summaries: list[dict]  # [{"idea_id": ..., "summary": ...}]
    insights: list[dict]
    agent_thoughts: Annotated[list[dict], add_messages]


def _collect_ideas(state: CrossIdeaState) -> dict:
    summaries = state.get("idea_summaries", [])
    thought = {
        "agent": "idea_collector",
        "action": "collected_ideas",
        "detail": f"Analyzing {len(summaries)} ideas for cross-idea patterns",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _detect_patterns(state: CrossIdeaState) -> dict:
    summaries = state.get("idea_summaries", [])
    vs = get_vector_store()
    insights: list[dict] = []

    # Find similar pairs
    for i, idea_a in enumerate(summaries):
        similar = vs.search_similar_ideas(
            query=idea_a.get("summary", ""),
            n_results=3,
            exclude_id=idea_a.get("idea_id"),
        )
        for match in similar:
            if match.get("distance", 1.0) < 0.4:
                insights.append({
                    "type": "similar_ideas",
                    "idea_a_id": idea_a["idea_id"],
                    "idea_b_id": match["idea_id"],
                    "similarity": 1.0 - match.get("distance", 0),
                    "idea_a_summary": idea_a.get("summary", "")[:100],
                    "idea_b_summary": match.get("summary", "")[:100],
                })

    thought = {
        "agent": "pattern_detector",
        "action": "detected_patterns",
        "detail": f"Found {len(insights)} cross-idea relationships",
        "timestamp": utc_now_iso(),
    }
    return {"insights": insights, "agent_thoughts": [thought]}


def _generate_cross_insights(state: CrossIdeaState) -> dict:
    insights = state.get("insights", [])
    enriched: list[dict] = []

    for insight in insights[:5]:
        try:
            raw = ai_gateway.generate_text(
                task="opportunity",
                user_prompt=(
                    f"Two product ideas are similar:\n"
                    f"Idea A: {insight.get('idea_a_summary', '')}\n"
                    f"Idea B: {insight.get('idea_b_summary', '')}\n"
                    "In 1-2 sentences, explain what they have in common and suggest how the user "
                    "could combine or differentiate them. Return plain text."
                ),
            )
            insight["analysis"] = raw.strip()
        except Exception:
            insight["analysis"] = "These ideas share common themes and could be combined."
        enriched.append(insight)

    thought = {
        "agent": "insight_generator",
        "action": "generated_cross_insights",
        "detail": f"Generated analysis for {len(enriched)} idea relationships",
        "timestamp": utc_now_iso(),
    }
    return {"insights": enriched, "agent_thoughts": [thought]}


def build_cross_idea_graph():
    graph = StateGraph(CrossIdeaState)
    graph.add_node("collect_ideas", _collect_ideas)
    graph.add_node("detect_patterns", _detect_patterns)
    graph.add_node("generate_insights", _generate_cross_insights)
    graph.add_edge(START, "collect_ideas")
    graph.add_edge("collect_ideas", "detect_patterns")
    graph.add_edge("detect_patterns", "generate_insights")
    graph.add_edge("generate_insights", END)
    return graph.compile()
```

```python
# backend/app/agents/graphs/proactive/user_pattern_learner.py
from __future__ import annotations

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, add_messages
from app.core import ai_gateway
from app.core.time import utc_now_iso


class PatternLearnerState(TypedDict):
    user_id: str
    decision_history: list[dict]  # [{"stage": ..., "choice": ..., "idea": ...}]
    learned_preferences: dict
    agent_thoughts: Annotated[list[dict], add_messages]


def _load_history(state: PatternLearnerState) -> dict:
    history = state.get("decision_history", [])
    thought = {
        "agent": "history_loader",
        "action": "loaded_history",
        "detail": f"Loaded {len(history)} decision records for pattern analysis",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _extract_patterns(state: PatternLearnerState) -> dict:
    history = state.get("decision_history", [])

    if not history:
        return {
            "learned_preferences": {},
            "agent_thoughts": [{
                "agent": "pattern_extractor",
                "action": "no_history",
                "detail": "No decision history available yet",
                "timestamp": utc_now_iso(),
            }],
        }

    history_text = "\n".join(
        f"- Stage: {d.get('stage')}, Choice: {d.get('choice')}, Idea: {d.get('idea')}"
        for d in history
    )

    try:
        raw = ai_gateway.generate_text(
            task="opportunity",
            user_prompt=(
                "Analyze this user's product decision history and identify 2-3 patterns:\n"
                f"{history_text}\n\n"
                "Return a JSON object with keys: 'business_model_preference', 'risk_tolerance', "
                "'focus_area', 'decision_style'. Each value is a short string description."
            ),
        )
        import json
        try:
            preferences = json.loads(raw.strip().strip("`").strip())
        except json.JSONDecodeError:
            preferences = {"raw_analysis": raw.strip()}
    except Exception:
        preferences = {"analysis_status": "failed"}

    thought = {
        "agent": "pattern_extractor",
        "action": "extracted_patterns",
        "detail": f"Identified preferences: {', '.join(f'{k}={v}' for k, v in list(preferences.items())[:3])}",
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

**Step 6: Implement notification and insight routes**

```python
# backend/app/routes/notifications.py
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
```

```python
# backend/app/routes/insights.py
from __future__ import annotations

import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph
from app.agents.memory.vector_store import get_vector_store
from app.db.repo_notifications import NotificationRepository

router = APIRouter(prefix="/insights", tags=["insights"])
_notif_repo = NotificationRepository()
_logger = logging.getLogger(__name__)


@router.post("/news-scan")
async def trigger_news_scan():
    """Trigger news monitoring agent (for demo)."""
    graph = build_news_monitor_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_ids": [],
        "notifications": [],
        "agent_thoughts": [],
    })

    # Persist notifications
    created = []
    for notif in result.get("notifications", []):
        record = _notif_repo.create(
            type="news_match",
            title=f"News: {notif.get('news_title', 'Untitled')}",
            body=notif.get("insight", "Relevant news detected."),
            metadata=notif,
        )
        created.append(record.id)

    return {
        "notifications_created": len(created),
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.post("/cross-idea-analysis")
async def trigger_cross_idea_analysis():
    """Trigger cross-idea analysis agent (for demo)."""
    vs = get_vector_store()
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

    # Persist as notifications
    for insight in result.get("insights", []):
        _notif_repo.create(
            type="cross_idea_insight",
            title=f"Ideas '{insight.get('idea_a_id', '')}' and '{insight.get('idea_b_id', '')}' are related",
            body=insight.get("analysis", "These ideas share common themes."),
            metadata=insight,
        )

    return {
        "insights": result.get("insights", []),
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.post("/learn-patterns")
async def trigger_pattern_learning():
    """Trigger user pattern learning agent (for demo)."""
    # In a real app, this would load from decision history in DB
    # For demo, use pre-seeded data
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI code review tool"},
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "Developer dashboard"},
            {"stage": "scope", "choice": "minimal_mvp", "idea": "AI code review tool"},
            {"stage": "opportunity", "choice": "B2B_focus", "idea": "Meeting summarizer"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })

    # Persist pattern notification
    prefs = result.get("learned_preferences", {})
    if prefs:
        _notif_repo.create(
            type="pattern_learned",
            title="Updated your preference profile",
            body=f"Learned patterns: {', '.join(f'{k}: {v}' for k, v in list(prefs.items())[:3])}",
            metadata={"preferences": prefs},
        )

    return {
        "learned_preferences": prefs,
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.get("/user-patterns")
async def get_user_patterns():
    """Get learned user patterns (for settings page display)."""
    # For demo, run pattern learner inline
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI code review tool"},
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "Developer dashboard"},
            {"stage": "scope", "choice": "minimal_mvp", "idea": "AI code review tool"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    return {"preferences": result.get("learned_preferences", {})}
```

**Step 7: Register new routers in main.py**

Add imports and router registrations in `backend/app/main.py`:

```python
from app.routes.notifications import router as notifications_router
from app.routes.insights import router as insights_router
```

And in the `create_app()` function, add after the existing router registrations:

```python
    app.include_router(notifications_router, dependencies=protected_dependencies)
    app.include_router(insights_router, dependencies=protected_dependencies)
```

**Step 8: Run tests**

Run: `cd backend && python -m pytest tests/test_proactive_agents.py tests/ -x -q`
Expected: All PASS

**Step 9: Commit**

```bash
git add backend/app/agents/graphs/proactive/ backend/app/db/repo_notifications.py \
  backend/app/db/models.py backend/app/routes/notifications.py \
  backend/app/routes/insights.py backend/app/main.py \
  backend/tests/test_proactive_agents.py
git commit -m "feat(agents): add proactive agents — news monitor, cross-idea analyzer, pattern learner"
```

---

### Task 9: Seed Data Initialization + Demo Bootstrap

**Files:**

- Modify: `backend/app/db/bootstrap.py` (seed vector store on startup)
- Create: `backend/scripts/seed_demo.py`
- Test: manual verification

**Step 1: Add vector store seeding to bootstrap**

Add to `backend/app/db/bootstrap.py`:

```python
def seed_demo_data_if_empty() -> None:
    """Seed vector store with demo data if collections are empty."""
    try:
        from app.agents.memory.vector_store import get_vector_store
        vs = get_vector_store()
        if vs._ideas.count() == 0:
            from app.agents.memory.seed_data import seed_vector_store
            seed_vector_store()
    except Exception:
        pass  # Non-critical for app startup
```

Call it at end of `initialize_database()`:

```python
def initialize_database() -> None:
    with db_session() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        ensure_default_workspace(connection)
        ensure_default_ai_settings(connection)
        _auth_repo.ensure_seed_users(connection)
    seed_demo_data_if_empty()
```

**Step 2: Create standalone demo seed script**

```python
# backend/scripts/seed_demo.py
"""Standalone script to seed demo data for hackathon presentation.

Run: cd backend && python -m scripts.seed_demo
"""
from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.agents.memory.seed_data import seed_vector_store

if __name__ == "__main__":
    seed_vector_store()
    print("Demo data seeded successfully!")
```

**Step 3: Verify end-to-end**

Run: `cd backend && python -m scripts.seed_demo`
Expected: "Seeded 5 ideas, 5 news, 3 patterns"

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add backend/app/db/bootstrap.py backend/scripts/
git commit -m "feat: add demo data seeding on startup for hackathon"
```

---

### Task 10: Frontend — Agent Thought Stream Component

**Files:**

- Create: `frontend/components/agent/AgentThoughtStream.tsx`
- Modify: `frontend/lib/sse.ts` (handle new event types)

**Step 1: Extend SSE client to handle `agent_thought` events**

In `frontend/lib/sse.ts`, extend the `StreamPostHandlers` type and the event routing:

Add to the type:

```typescript
onAgentThought?: (data: { agent: string; action: string; detail: string; pct: number }) => void
onMemoryInsight?: (data: { type: string; idea_title: string; relevance: number; insight: string }) => void
```

Add to the event routing loop (before the `error` check):

```typescript
if (parsed.event === 'agent_thought') {
  handlers.onAgentThought?.(
    parsed.data as { agent: string; action: string; detail: string; pct: number }
  )
  continue
}

if (parsed.event === 'memory_insight') {
  handlers.onMemoryInsight?.(
    parsed.data as { type: string; idea_title: string; relevance: number; insight: string }
  )
  continue
}
```

**Step 2: Build AgentThoughtStream component**

```tsx
// frontend/components/agent/AgentThoughtStream.tsx
'use client'

import { useState } from 'react'

type AgentThought = {
  agent: string
  action: string
  detail: string
  pct: number
  timestamp?: string
}

const AGENT_ICONS: Record<string, string> = {
  context_loader: 'Search',
  researcher: 'Search',
  direction_generator: 'Lightbulb',
  plan_generator: 'FileText',
  plan_synthesizer: 'BarChart',
  pattern_matcher: 'Brain',
  prd_writer: 'Edit',
  prd_reviewer: 'CheckCircle',
  memory_writer: 'Database',
  critic: 'AlertTriangle',
  news_fetcher: 'Newspaper',
  news_matcher: 'Link',
  insight_generator: 'Zap',
}

const AGENT_LABELS: Record<string, string> = {
  context_loader: 'Context Loader',
  researcher: 'Researcher',
  direction_generator: 'Direction Generator',
  plan_generator: 'Plan Generator',
  plan_synthesizer: 'Plan Synthesizer',
  pattern_matcher: 'Pattern Matcher',
  prd_writer: 'PRD Writer',
  prd_reviewer: 'PRD Reviewer',
  memory_writer: 'Memory Writer',
  critic: 'Critic',
}

export function AgentThoughtStream({ thoughts }: { thoughts: AgentThought[] }) {
  const [collapsed, setCollapsed] = useState(false)

  if (thoughts.length === 0) return null

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900/50">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center justify-between px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800/50"
      >
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-400" />
          Agent Activity ({thoughts.length} steps)
        </span>
        <span>{collapsed ? '+' : '-'}</span>
      </button>

      {!collapsed && (
        <div className="max-h-64 space-y-2 overflow-y-auto px-4 pb-3">
          {thoughts.map((thought, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="w-16 shrink-0 text-right font-mono text-zinc-500">
                {thought.pct}%
              </span>
              <span className="w-36 shrink-0 font-medium text-blue-400">
                {AGENT_LABELS[thought.agent] || thought.agent}
              </span>
              <span className="text-zinc-400">{thought.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function useAgentThoughts() {
  const [thoughts, setThoughts] = useState<AgentThought[]>([])

  const addThought = (thought: AgentThought) => {
    setThoughts((prev) => [...prev, thought])
  }

  const reset = () => setThoughts([])

  return { thoughts, addThought, reset }
}
```

**Step 3: Commit**

```bash
git add frontend/components/agent/ frontend/lib/sse.ts
git commit -m "feat(frontend): add AgentThoughtStream component and SSE event handling"
```

---

### Task 11: Frontend — Notification Bell + Insights Page

**Files:**

- Create: `frontend/components/notifications/NotificationBell.tsx`
- Create: `frontend/components/insights/CrossIdeaInsights.tsx`
- Create: `frontend/components/insights/UserPatternCard.tsx`

These are self-contained UI components. They fetch from the new API endpoints.

**Step 1: Build NotificationBell**

```tsx
// frontend/components/notifications/NotificationBell.tsx
'use client'

import { useEffect, useState } from 'react'
import { buildApiUrl, withAuthHeaders } from '@/lib/api'

type Notification = {
  id: string
  type: string
  title: string
  body: string
  metadata: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export function NotificationBell() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)

  const fetchNotifications = async () => {
    try {
      const res = await fetch(buildApiUrl('/notifications?unread_only=true'), {
        headers: withAuthHeaders({}),
      })
      if (res.ok) {
        const data = await res.json()
        setNotifications(data.notifications || [])
      }
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [])

  const dismiss = async (id: string) => {
    await fetch(buildApiUrl(`/notifications/${id}/dismiss`), {
      method: 'POST',
      headers: withAuthHeaders({}),
    })
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }

  const count = notifications.length

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 text-zinc-400 hover:text-zinc-200"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>
        {count > 0 && (
          <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 max-h-96 w-80 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl">
          <div className="border-b border-zinc-700 p-3">
            <h3 className="text-sm font-medium text-zinc-200">Notifications</h3>
          </div>
          {notifications.length === 0 ? (
            <p className="p-4 text-sm text-zinc-500">No new notifications</p>
          ) : (
            notifications.map((n) => (
              <div key={n.id} className="border-b border-zinc-800 p-3 hover:bg-zinc-800/50">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-medium text-blue-400">{n.type.replace('_', ' ')}</p>
                    <p className="mt-1 text-sm text-zinc-200">{n.title}</p>
                    <p className="mt-1 text-xs text-zinc-400">{n.body}</p>
                  </div>
                  <button
                    onClick={() => dismiss(n.id)}
                    className="shrink-0 text-xs text-zinc-500 hover:text-zinc-300"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
```

**Step 2: Build CrossIdeaInsights and UserPatternCard**

```tsx
// frontend/components/insights/CrossIdeaInsights.tsx
'use client'

import { useState } from 'react'
import { buildApiUrl, withAuthHeaders } from '@/lib/api'

type Insight = {
  type: string
  idea_a_id: string
  idea_b_id: string
  similarity: number
  idea_a_summary: string
  idea_b_summary: string
  analysis: string
}

export function CrossIdeaInsights() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(false)

  const runAnalysis = async () => {
    setLoading(true)
    try {
      const res = await fetch(buildApiUrl('/insights/cross-idea-analysis'), {
        method: 'POST',
        headers: withAuthHeaders({ 'Content-Type': 'application/json' }),
      })
      if (res.ok) {
        const data = await res.json()
        setInsights(data.insights || [])
      }
    } catch {
      /* ignore */
    }
    setLoading(false)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">Cross-Idea Analysis</h3>
        <button
          onClick={runAnalysis}
          disabled={loading}
          className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? 'Analyzing...' : 'Run Analysis'}
        </button>
      </div>
      {insights.map((insight, i) => (
        <div key={i} className="rounded-lg border border-zinc-700 bg-zinc-900/50 p-3">
          <div className="flex items-center gap-2 text-xs text-blue-400">
            <span>Similarity: {(insight.similarity * 100).toFixed(0)}%</span>
          </div>
          <p className="mt-2 text-sm text-zinc-300">{insight.analysis}</p>
          <div className="mt-2 flex gap-2 text-xs text-zinc-500">
            <span>{insight.idea_a_summary}</span>
            <span>vs</span>
            <span>{insight.idea_b_summary}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
```

```tsx
// frontend/components/insights/UserPatternCard.tsx
'use client'

import { useEffect, useState } from 'react'
import { buildApiUrl, withAuthHeaders } from '@/lib/api'

export function UserPatternCard() {
  const [preferences, setPreferences] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(buildApiUrl('/insights/user-patterns'), {
      headers: withAuthHeaders({}),
    })
      .then((r) => r.json())
      .then((data) => setPreferences(data.preferences || {}))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-zinc-500">Loading learned patterns...</p>

  const entries = Object.entries(preferences)
  if (entries.length === 0) return null

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900/50 p-4">
      <h3 className="mb-3 text-sm font-medium text-zinc-200">
        What the system has learned about you
      </h3>
      <div className="space-y-2">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-start gap-2">
            <span className="w-40 shrink-0 text-xs font-medium text-blue-400">
              {key.replace(/_/g, ' ')}
            </span>
            <span className="text-xs text-zinc-400">{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/components/notifications/ frontend/components/insights/
git commit -m "feat(frontend): add notification bell, cross-idea insights, and user pattern card"
```

---

### Task 12: Wire Agent Thought Stream into Existing Pages

**Files:**

- Modify: Frontend page components that use SSE streaming (opportunity, feasibility, PRD pages)

This task integrates the `AgentThoughtStream` component into existing page components. The exact files depend on the page structure, but the pattern is:

1. Import `useAgentThoughts` and `AgentThoughtStream`
2. Add `onAgentThought: addThought` to the SSE handlers
3. Render `<AgentThoughtStream thoughts={thoughts} />` in the page layout
4. Call `reset()` when starting a new generation

The SSE endpoint URL changes from `/stream` to `/stream/v2` for the enhanced version.

**Step 1: Modify one page as example (opportunity page)**

Find the opportunity page component, add the agent thought stream panel alongside the existing generation UI. Use the v2 endpoint when available, falling back to v1.

**Step 2: Verify manually**

Run both frontend and backend, trigger an opportunity generation, observe agent thoughts in the UI.

**Step 3: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): wire agent thought stream into opportunity page"
```

---

### Task 13: Demo Polish + Architecture Diagrams

**Files:**

- Create: `docs/demo-architecture.md` (Mermaid diagrams for presentation)
- Ensure seed data loads correctly on fresh start

**Step 1: Create architecture diagrams for presentation**

Create a markdown file with Mermaid diagrams that can be rendered for the hackathon presentation:

- Multi-agent graph topology
- Memory architecture (Thread State + Store + Vector DB)
- Data flow diagram (idea → agents → memory → proactive agents → notifications)

**Step 2: Run full demo script**

1. Start backend: `cd backend && uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Create idea, observe agent thoughts
4. Create second idea, observe cross-idea detection
5. Trigger news scan, observe notification
6. Check user patterns in settings

**Step 3: Record backup demo video**

Use screen recording to capture the full demo flow in case live demo fails during hackathon.

**Step 4: Commit**

```bash
git add docs/
git commit -m "docs: add architecture diagrams and demo preparation"
```

---

## Summary: Task Dependency Graph

```
Task 1 (deps)
  └→ Task 2 (state + checkpointer)
       └→ Task 3 (vector store)
            └→ Task 4 (opportunity subgraph) ─────→ Task 5 (SSE streaming)
            └→ Task 6 (feasibility subgraph) ────→ Task 5
            └→ Task 7 (PRD subgraph) ────────────→ Task 5
            └→ Task 8 (proactive agents)
                 └→ Task 9 (seed data)
  Task 10 (frontend: thought stream) ←── Task 5
  Task 11 (frontend: notifications) ←── Task 8
  Task 12 (wire into pages) ←── Task 10
  Task 13 (demo polish) ←── all above
```

**Critical path:** Tasks 1 → 2 → 3 → 4 → 5 → 10 → 12 → 13

**Parallelizable:** Tasks 6, 7, 8 can be done in parallel after Task 3. Tasks 10, 11 can be done in parallel.
