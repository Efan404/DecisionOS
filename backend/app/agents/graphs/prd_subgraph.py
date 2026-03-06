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


def _prd_writer_node(state: DecisionOSState) -> dict[str, object]:
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
        "prd_output": {"markdown": result.markdown, "sections": [s.model_dump() if hasattr(s, 'model_dump') else s for s in result.sections]},
        "agent_thoughts": [thought],
    }


def build_prd_graph() -> StateGraph:
    """Build PRD subgraph: ContextLoader -> PRDWriter -> PRDReviewer -> MemoryWriter."""
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
