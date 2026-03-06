from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.agents.state import AgentThought, DecisionOSState
from app.core import ai_gateway
from app.core.prompts import build_opportunity_prompt
from app.schemas.idea import OpportunityOutput


def _researcher_node(state: DecisionOSState) -> dict:
    """Analyze retrieved context and produce a research summary thought."""
    similar = state.get("retrieved_similar_ideas") or []
    patterns = state.get("retrieved_patterns") or []

    analysis_parts: list[str] = []
    if similar:
        idea_titles = [s.get("summary", "")[:60] for s in similar[:3]]
        analysis_parts.append(f"Found {len(similar)} similar ideas: {'; '.join(idea_titles)}")
    else:
        analysis_parts.append("No similar ideas found in memory.")

    if patterns:
        pattern_descs = [p.get("description", "")[:60] for p in patterns[:3]]
        analysis_parts.append(f"Found {len(patterns)} relevant patterns: {'; '.join(pattern_descs)}")
    else:
        analysis_parts.append("No matching decision patterns found.")

    thought: AgentThought = {
        "agent": "researcher",
        "action": "context_analysis",
        "detail": " ".join(analysis_parts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {"agent_thoughts": [thought]}


def _direction_generator_node(state: DecisionOSState) -> dict:
    """Generate opportunity directions using the existing AI gateway."""
    idea_seed = state["idea_seed"]
    similar = state.get("retrieved_similar_ideas") or []
    patterns = state.get("retrieved_patterns") or []

    # Build enriched prompt incorporating memory context
    base_prompt = build_opportunity_prompt(idea_seed=idea_seed, count=3)

    context_parts: list[str] = []
    if similar:
        context_parts.append("Similar existing ideas for differentiation:")
        for s in similar[:3]:
            context_parts.append(f"  - {s.get('summary', '')}")
    if patterns:
        context_parts.append("Relevant decision patterns to consider:")
        for p in patterns[:3]:
            context_parts.append(f"  - {p.get('description', '')}")

    if context_parts:
        enriched_prompt = (
            base_prompt + "\n\nContext from memory:\n" + "\n".join(context_parts)
            + "\n\nUse this context to generate more differentiated and informed directions."
        )
    else:
        enriched_prompt = base_prompt

    result: OpportunityOutput = ai_gateway.generate_structured(
        task="opportunity",
        user_prompt=enriched_prompt,
        schema_model=OpportunityOutput,
    )

    thought: AgentThought = {
        "agent": "direction_generator",
        "action": "generate_directions",
        "detail": f"Generated {len(result.directions)} opportunity directions.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "opportunity_output": result.model_dump(mode="python"),
        "agent_thoughts": [thought],
    }


def build_opportunity_graph() -> StateGraph:
    """Build and compile the opportunity subgraph."""
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
