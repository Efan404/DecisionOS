from __future__ import annotations

import os
import tempfile


from app.agents.checkpointer import get_checkpointer
from app.agents.state import AgentThought, DecisionOSState


def test_state_schema_defaults():
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
        "market_evidence_context": "",
    }
    assert state["idea_id"] == "test-id"
    assert state["agent_thoughts"] == []


def test_agent_thought_structure():
    thought: AgentThought = {
        "agent": "researcher",
        "action": "analyzing",
        "detail": "Found 2 similar ideas",
        "timestamp": "2026-03-06T00:00:00Z",
    }
    assert thought["agent"] == "researcher"


def test_checkpointer_creates_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_checkpoint.db")
        saver = get_checkpointer(db_path)
        assert saver is not None
