from __future__ import annotations

import json
import logging
from typing import TypeVar

from app.core import ai_gateway
from app.core import prompts
from app.schemas.feasibility import FeasibilityInput, FeasibilityOutput
from app.schemas.idea import OpportunityInput, OpportunityOutput
from app.schemas.prd import (
    PRDOutput,
    PrdContextPack,
    PRDRequirementsOutput,
    PRDMarkdownOutput,
    PRDBacklogOutput,
)
from app.schemas.scope import ScopeInput, ScopeOutput

SchemaT = TypeVar("SchemaT")
logger = logging.getLogger(__name__)


class PRDGenerationError(RuntimeError):
    pass


def generate_opportunity(payload: OpportunityInput) -> OpportunityOutput:
    return ai_gateway.generate_structured(
        task="opportunity",
        user_prompt=prompts.build_opportunity_prompt(idea_seed=payload.idea_seed, count=payload.count),
        schema_model=OpportunityOutput,
    )


def generate_feasibility(payload: FeasibilityInput) -> FeasibilityOutput:
    return ai_gateway.generate_structured(
        task="feasibility",
        user_prompt=prompts.build_feasibility_prompt(
            idea_seed=payload.idea_seed,
            confirmed_path_id=payload.confirmed_path_id,
            confirmed_node_id=payload.confirmed_node_id,
            confirmed_node_content=payload.confirmed_node_content,
            confirmed_path_summary=payload.confirmed_path_summary,
        ),
        schema_model=FeasibilityOutput,
    )


def generate_single_plan(payload: FeasibilityInput, plan_index: int) -> Plan:
    """Generate exactly one feasibility Plan concurrently with other plan calls."""
    from app.schemas.feasibility import Plan  # local import to avoid circular at module level

    plan = ai_gateway.generate_structured(
        task="feasibility",
        user_prompt=prompts.build_single_plan_prompt(
            idea_seed=payload.idea_seed,
            confirmed_node_content=payload.confirmed_node_content,
            confirmed_path_summary=payload.confirmed_path_summary,
            plan_index=plan_index,
        ),
        schema_model=Plan,
    )
    plan.id = f"plan{plan_index + 1}"
    return plan


def generate_scope(payload: ScopeInput) -> ScopeOutput:
    return ai_gateway.generate_structured(
        task="scope",
        user_prompt=prompts.build_scope_prompt(
            idea_seed=payload.idea_seed,
            confirmed_path_id=payload.confirmed_path_id,
            confirmed_node_id=payload.confirmed_node_id,
            confirmed_node_content=payload.confirmed_node_content,
            confirmed_path_summary=payload.confirmed_path_summary,
            selected_plan_id=payload.selected_plan_id,
            feasibility_payload=payload.feasibility.model_dump(mode="python"),
        ),
        schema_model=ScopeOutput,
    )


def _build_slim_prd_context(pack: PrdContextPack) -> dict[str, object]:
    """Return a trimmed context dict for PRD prompts (no path_json, no alt plans)."""
    full = pack.model_dump(mode="python")
    step2: dict = full.get("step2_path", {})
    step3: dict = full.get("step3_feasibility", {})
    step4: dict = full.get("step4_scope", {})
    selected_plan: dict = step3.get("selected_plan", {})
    return {
        "idea_seed": full.get("idea_seed"),
        "confirmed_path_summary": step2.get("path_summary"),
        "leaf_node_content": step2.get("leaf_node_content"),
        "selected_plan": {
            "name": selected_plan.get("name"),
            "summary": selected_plan.get("summary"),
            "score_overall": selected_plan.get("score_overall"),
            "recommended_positioning": selected_plan.get("recommended_positioning"),
        },
        "in_scope": [
            {"title": i.get("title"), "desc": i.get("desc"), "priority": i.get("priority")}
            for i in step4.get("in_scope", [])
        ],
        "out_scope": [
            {"title": i.get("title"), "reason": i.get("reason")}
            for i in step4.get("out_scope", [])
        ],
    }


def generate_prd_strict(context_pack: PrdContextPack) -> PRDOutput:
    try:
        return ai_gateway.generate_structured(
            task="prd",
            user_prompt=prompts.build_prd_prompt(
                context_pack=_build_slim_prd_context(context_pack),
            ),
            schema_model=PRDOutput,
        )
    except Exception as exc:
        raise PRDGenerationError("Failed to generate PRD output from provider") from exc


def generate_prd_requirements(context: dict[str, object]) -> PRDRequirementsOutput:
    """Stage-A parallel call: requirements only."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_requirements_prompt(context=context),
        schema_model=PRDRequirementsOutput,
    )


def generate_prd_markdown(context: dict[str, object]) -> PRDMarkdownOutput:
    """Stage-A parallel call: markdown + sections only."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_markdown_prompt(context=context),
        schema_model=PRDMarkdownOutput,
    )


def generate_prd_backlog(
    context: dict[str, object],
    requirement_ids: list[str],
) -> PRDBacklogOutput:
    """Stage-B call: backlog items (requires requirement IDs from Stage A)."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_backlog_prompt(
            context=context, requirement_ids=requirement_ids
        ),
        schema_model=PRDBacklogOutput,
    )


def _parse_nodes_from_text(text: str) -> list[dict[str, str]]:
    """Parse LLM text response into list of {content, edge_label} dicts."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return [
            {"content": str(n.get("content", "")), "edge_label": str(n.get("edge_label", ""))}
            for n in parsed if isinstance(n, dict)
        ]
    if isinstance(parsed, dict) and "nodes" in parsed:
        nodes = parsed["nodes"]
        if isinstance(nodes, list):
            return [
                {"content": str(n.get("content", "")), "edge_label": str(n.get("edge_label", ""))}
                for n in nodes if isinstance(n, dict)
            ]
    raise ValueError(f"Unexpected nodes response shape: {text[:200]}")


def generate_expand_nodes(
    content: str,
    pattern_label: str,
    pattern_description: str,
    chain_summary: str,
) -> list[dict[str, str]]:
    """Return list of {content, edge_label} dicts for AI node expansion."""
    return _parse_nodes_from_text(
        ai_gateway.generate_text(
            task="opportunity",
            user_prompt=prompts.expand_node_prompt(
                content, pattern_label, pattern_description, chain_summary
            ),
        )
    )


def generate_expand_node_user(
    content: str,
    user_direction: str,
    chain_summary: str,
) -> list[dict[str, str]]:
    """Return list of {content, edge_label} dicts for user-guided expansion."""
    return _parse_nodes_from_text(
        ai_gateway.generate_text(
            task="opportunity",
            user_prompt=prompts.expand_node_user_prompt(
                content, user_direction, chain_summary
            ),
        )
    )


def generate_path_summary(node_chain_text: str) -> str:
    """Return a plain-text summary of a confirmed path."""
    raw = ai_gateway.generate_text(
        task="opportunity",
        user_prompt=prompts.summarize_path_prompt(node_chain_text),
    ).strip()
    # Model may return {"summary": "..."} or plain text
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "summary" in parsed:
            return str(parsed["summary"])
    except json.JSONDecodeError:
        pass
    return raw


def _get_active_provider_info() -> dict[str, str | None]:
    """Return {id, model} of the active provider for generation_meta."""
    provider = ai_gateway._get_active_provider()
    return {"id": provider.id, "model": provider.model}
