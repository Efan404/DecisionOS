from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.agents.state import DecisionOSState, AgentThought
from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.core import ai_gateway, prompts
from app.core.time import utc_now_iso
from app.schemas.prd import PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput

logger = logging.getLogger(__name__)


# ── Node: requirements_writer ─────────────────────────────────────────────────

def _requirements_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-A parallel: generate 6-12 structured requirements."""
    slim_ctx = state.get("prd_slim_context") or {}
    patterns = state.get("retrieved_patterns", [])

    prompt = prompts.build_prd_requirements_prompt(context=slim_ctx)
    if patterns:
        prompt += "\n\nUser decision patterns:\n" + "\n".join(
            f"- {p.get('description', '')[:120]}" for p in patterns[:2]
        )

    result: PRDRequirementsOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompt,
        schema_model=PRDRequirementsOutput,
    )

    thought: AgentThought = {
        "agent": "requirements_writer",
        "action": "generated_requirements",
        "detail": f"Generated {len(result.requirements)} requirements",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_requirements": [r.model_dump() for r in result.requirements],
        "agent_thoughts": [thought],
    }


# ── Node: markdown_writer ─────────────────────────────────────────────────────

def _markdown_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-A parallel: generate full markdown narrative + sections."""
    slim_ctx = state.get("prd_slim_context") or {}
    similar = state.get("retrieved_similar_ideas", [])

    prompt = prompts.build_prd_markdown_prompt(context=slim_ctx)
    if similar:
        prompt += "\n\nSimilar past ideas for reference:\n" + "\n".join(
            f"- {s.get('summary', '')[:100]}" for s in similar[:2]
        )

    result: PRDMarkdownOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompt,
        schema_model=PRDMarkdownOutput,
    )

    thought: AgentThought = {
        "agent": "markdown_writer",
        "action": "generated_markdown",
        "detail": f"Generated PRD markdown ({len(result.markdown)} chars, {len(result.sections)} sections)",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_markdown": result.markdown,
        "prd_sections": [s.model_dump() for s in result.sections],
        "agent_thoughts": [thought],
    }


# ── Node: backlog_writer ──────────────────────────────────────────────────────

def _backlog_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-B sequential: generate backlog items that reference requirement IDs."""
    slim_ctx = state.get("prd_slim_context") or {}
    requirements = state.get("prd_requirements", [])
    requirement_ids = [r.get("id", "") for r in requirements if r.get("id")]

    if not requirement_ids:
        thought: AgentThought = {
            "agent": "backlog_writer",
            "action": "skipped",
            "detail": "No requirement IDs available — skipping backlog generation",
            "timestamp": utc_now_iso(),
        }
        return {"prd_backlog_items": [], "agent_thoughts": [thought]}

    result: PRDBacklogOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_backlog_prompt(
            context=slim_ctx, requirement_ids=requirement_ids
        ),
        schema_model=PRDBacklogOutput,
    )

    thought: AgentThought = {
        "agent": "backlog_writer",
        "action": "generated_backlog",
        "detail": f"Generated {len(result.backlog.items)} backlog items",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_backlog_items": [item.model_dump() for item in result.backlog.items],
        "agent_thoughts": [thought],
    }


# ── Node: prd_reviewer ────────────────────────────────────────────────────────

def _prd_reviewer_node(state: DecisionOSState) -> dict[str, object]:
    """Quality review: check scope coverage and requirement count."""
    markdown = state.get("prd_markdown", "")
    requirements = state.get("prd_requirements", [])
    scope = state.get("scope_output") or {}
    in_scope = scope.get("in_scope", [])

    issues: list[str] = []
    if len(markdown) < 200:
        issues.append("PRD markdown is unusually short (<200 chars)")
    if len(requirements) < 4:
        issues.append(f"Too few requirements: {len(requirements)} (expected ≥6)")
    if in_scope:
        scope_titles = {item.get("title", "").lower() for item in in_scope if isinstance(item, dict)}
        md_lower = markdown.lower()
        missing = [t for t in scope_titles if t and t not in md_lower]
        if missing:
            issues.append(f"{len(missing)} scope items not mentioned in PRD: {', '.join(missing[:3])}")

    detail = (
        f"Review found {len(issues)} issues: {'; '.join(issues)}"
        if issues
        else f"PRD passed quality review: {len(requirements)} requirements, all scope items covered"
    )
    thought: AgentThought = {
        "agent": "prd_reviewer",
        "action": "quality_review",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }
    return {"prd_review_issues": issues, "agent_thoughts": [thought]}


# ── Fan-out router ────────────────────────────────────────────────────────────

def _fan_out_to_parallel_writers(state: DecisionOSState) -> list[Send]:
    """After context_loader: dispatch requirements_writer and markdown_writer in parallel."""
    return [
        Send("requirements_writer", state),
        Send("markdown_writer", state),
    ]


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_prd_graph() -> object:
    """
    PRD graph topology:
        START → context_loader
                  ├─(Send)→ requirements_writer ─┐
                  └─(Send)→ markdown_writer      ─┤ (fan-in)
                                                  └─► backlog_writer
                                                          └─► prd_reviewer
                                                                  └─► memory_writer → END
    """
    graph = StateGraph(DecisionOSState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("requirements_writer", _requirements_writer_node)
    graph.add_node("markdown_writer", _markdown_writer_node)
    graph.add_node("backlog_writer", _backlog_writer_node)
    graph.add_node("prd_reviewer", _prd_reviewer_node)
    graph.add_node("memory_writer", memory_writer_node)

    # context_loader fans out to parallel writers
    graph.add_edge(START, "context_loader")
    graph.add_conditional_edges(
        "context_loader",
        _fan_out_to_parallel_writers,
        ["requirements_writer", "markdown_writer"],
    )

    # Both parallel branches feed into backlog_writer (fan-in via state merge)
    graph.add_edge("requirements_writer", "backlog_writer")
    graph.add_edge("markdown_writer", "backlog_writer")

    graph.add_edge("backlog_writer", "prd_reviewer")
    graph.add_edge("prd_reviewer", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
