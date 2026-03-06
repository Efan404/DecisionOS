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
    """Build feasibility subgraph: ContextLoader -> PlanGenerator -> Synthesizer -> PatternMatcher -> MemoryWriter."""
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
