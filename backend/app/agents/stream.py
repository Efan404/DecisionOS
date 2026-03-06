"""Bridge between LangGraph graph execution and SSE event emission."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.agents.state import DecisionOSState
from app.agents.graphs.opportunity_subgraph import build_opportunity_graph
from app.agents.graphs.feasibility_subgraph import build_feasibility_graph
from app.agents.graphs.prd_subgraph import build_prd_graph

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
    final_output = None
    pct = 10
    async for event in graph.astream(initial_state, stream_mode="updates"):
        # event is a dict of {node_name: state_update}
        for node_name, update in event.items():
            thoughts = update.get("agent_thoughts", [])
            for thought in thoughts:
                pct = min(90, pct + 15)
                yield _sse_event("agent_thought", {
                    "agent": thought.get("agent", node_name),
                    "action": thought.get("action", "processing"),
                    "detail": thought.get("detail", ""),
                    "pct": pct,
                })

            # If this node produced the final output, capture it
            if "opportunity_output" in update and update["opportunity_output"] is not None:
                final_output = update["opportunity_output"]

    yield _sse_event("progress", {"step": "saving", "pct": 95})

    yield _sse_event("done", {
        "idea_id": idea_id,
        "opportunity_output": final_output,
    })


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


async def run_prd_graph_sse(
    *,
    idea_id: str,
    idea_seed: str,
    dag_path: dict | None = None,
    feasibility_output: dict | None = None,
    selected_plan_id: str = "",
    scope_output: dict | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Run PRD subgraph and yield SSE events."""
    graph = build_prd_graph()

    initial_state: DecisionOSState = {
        "idea_id": idea_id,
        "idea_seed": idea_seed,
        "current_stage": "prd",
        "opportunity_output": None,
        "dag_path": dag_path,
        "feasibility_output": feasibility_output,
        "selected_plan_id": selected_plan_id,
        "scope_output": scope_output,
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
                pct = min(90, pct + 12)
                yield _sse_event("agent_thought", {
                    "agent": thought.get("agent", node_name),
                    "action": thought.get("action", "processing"),
                    "detail": thought.get("detail", ""),
                    "pct": pct,
                })

            if "prd_output" in update and update["prd_output"] is not None:
                final_output = update["prd_output"]

    yield _sse_event("done", {
        "idea_id": idea_id,
        "prd_output": final_output,
    })
