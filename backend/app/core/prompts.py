from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are the DecisionOS backend planner. Always return strict JSON matching the requested schema. "
    "Never include markdown or extra prose. "
    "All generated content (node text, labels, summaries) MUST be written in English."
)


def build_opportunity_prompt(*, idea_seed: str, count: int) -> str:
    return (
        f"Generate exactly {count} opportunity directions for this idea seed: {idea_seed!r}. "
        "Each direction must contain: id, title, one_liner, pain_tags. "
        "Use ids in order starting from A (A, B, C, ...). "
        "Return JSON object with key 'directions'."
    )

FEASIBILITY_PROMPT = (
    "Given an idea seed and confirmed DAG path context, produce exactly three feasibility plans "
    "with scoring and reasoning."
)

SCOPE_PROMPT = (
    "Given confirmed DAG context, selected plan and feasibility output, classify features into in_scope and out_scope."
)

PRD_PROMPT = (
    "Generate a delivery-ready PRD and executable backlog grounded in confirmed path, "
    "selected feasibility plan, and frozen scope baseline."
)


def build_feasibility_prompt(
    *,
    idea_seed: str,
    confirmed_path_id: str,
    confirmed_node_id: str,
    confirmed_node_content: str,
    confirmed_path_summary: str | None,
) -> str:
    return (
        f"{FEASIBILITY_PROMPT}\n"
        f"idea_seed={idea_seed!r}\n"
        f"confirmed_path_id={confirmed_path_id!r}\n"
        f"confirmed_node_id={confirmed_node_id!r}\n"
        f"confirmed_node_content={confirmed_node_content!r}\n"
        f"confirmed_path_summary={confirmed_path_summary!r}\n"
        "Return JSON with key 'plans'."
    )


_SINGLE_PLAN_ARCHETYPES = [
    "a bootstrapped / capital-light approach",
    "a VC-funded / growth-first approach",
    "a platform / ecosystem / partner-led approach",
]


def build_single_plan_prompt(
    *,
    idea_seed: str,
    confirmed_node_content: str,
    confirmed_path_summary: str | None,
    plan_index: int,
) -> str:
    """Build a prompt that asks the model for exactly ONE feasibility plan.

    plan_index is 0-based (0, 1, 2). Each call gets a different archetype hint
    to ensure the three concurrent plans are meaningfully distinct.
    """
    archetype = _SINGLE_PLAN_ARCHETYPES[plan_index % len(_SINGLE_PLAN_ARCHETYPES)]
    context = (
        f"confirmed_node_content={confirmed_node_content!r}\n"
        f"confirmed_path_summary={confirmed_path_summary!r}\n"
        f"idea_seed={idea_seed!r}\n"
    )
    return (
        "Given the following product context, generate exactly ONE detailed feasibility plan "
        f"following {archetype}.\n\n"
        f"{context}\n"
        "The plan MUST include:\n"
        '  - id: a short unique slug (e.g. "plan1", "plan2", "plan3")\n'
        "  - name: concise plan name\n"
        "  - summary: one-sentence value proposition\n"
        "  - score_overall: float 0-10\n"
        "  - scores: object with keys technical_feasibility, market_viability, execution_risk (each float 0-10)\n"
        "  - reasoning: object with keys technical_feasibility, market_viability, execution_risk (each a short string)\n"
        "  - recommended_positioning: one sentence on go-to-market positioning\n"
        "Return a single JSON object representing this plan (not wrapped in an array or 'plans' key)."
    )


def build_scope_prompt(
    *,
    idea_seed: str,
    confirmed_path_id: str,
    confirmed_node_id: str,
    confirmed_node_content: str,
    confirmed_path_summary: str | None,
    selected_plan_id: str,
    feasibility_payload: dict[str, object],
) -> str:
    return (
        f"{SCOPE_PROMPT}\n"
        f"idea_seed={idea_seed!r}\n"
        f"confirmed_path_id={confirmed_path_id!r}\n"
        f"confirmed_node_id={confirmed_node_id!r}\n"
        f"confirmed_node_content={confirmed_node_content!r}\n"
        f"confirmed_path_summary={confirmed_path_summary!r}\n"
        f"selected_plan_id={selected_plan_id!r}\n"
        f"feasibility={json.dumps(feasibility_payload, ensure_ascii=False)}\n"
        "Return JSON with keys 'in_scope' and 'out_scope'."
    )


def build_prd_prompt(
    *,
    context_pack: dict[str, object],
) -> str:
    # Build a trimmed context that omits fields the LLM does not need:
    # - step2_path.path_json and path_md (verbose node trees)
    # - step3_feasibility.alternatives_brief (non-selected plans)
    # - step4_scope.baseline_meta (internal versioning metadata)
    # - scope item ids (internal references)
    step2: dict = context_pack.get("step2_path", {})  # type: ignore[assignment]
    step3: dict = context_pack.get("step3_feasibility", {})  # type: ignore[assignment]
    step4: dict = context_pack.get("step4_scope", {})  # type: ignore[assignment]
    selected_plan: dict = step3.get("selected_plan", {})  # type: ignore[assignment]

    slim_context = {
        "idea_seed": context_pack.get("idea_seed"),
        "confirmed_path_summary": step2.get("path_summary"),
        "leaf_node_content": step2.get("leaf_node_content"),
        "selected_plan": {
            "name": selected_plan.get("name"),
            "summary": selected_plan.get("summary"),
            "score_overall": selected_plan.get("score_overall"),
            "recommended_positioning": selected_plan.get("recommended_positioning"),
        },
        "in_scope": [
            {"title": item.get("title"), "desc": item.get("desc"), "priority": item.get("priority")}
            for item in step4.get("in_scope", [])
        ],
        "out_scope": [
            {"title": item.get("title"), "reason": item.get("reason")}
            for item in step4.get("out_scope", [])
        ],
    }

    return (
        f"{PRD_PROMPT}\n"
        f"context={json.dumps(slim_context, ensure_ascii=False)}\n"
        "Constraints: 6-12 requirements; 8-15 backlog items; each item maps requirement_id; "
        "priority P0/P1/P2; type epic/story/task; >=2 acceptance_criteria per item; "
        "source_refs from step2/step3/step4; out_scope items must not be P0.\n"
        "Return JSON: markdown, sections, requirements, backlog, generation_meta."
    )


def expand_node_prompt(
    content: str,
    pattern_label: str,
    pattern_description: str,
    chain_summary: str,
) -> str:
    return (
        "You are a product thinking assistant helping explore an idea through structured lenses.\n"
        "All output — node content, edge labels, and any text — MUST be in English.\n\n"
        f"Current idea node:\n{content}\n\n"
        f"Path so far:\n{chain_summary}\n\n"
        f"Expansion lens: {pattern_label} — {pattern_description}\n\n"
        "Generate 2-3 distinct child ideas that extend the current node through this lens.\n"
        'Return a JSON object with key "nodes" containing an array of objects, each with "content" and "edge_label":\n'
        '{"nodes": [{"content": "...", "edge_label": "' + pattern_label + '"}, ...]}\n'
        "Only return the JSON object, no other text."
    )


def expand_node_user_prompt(
    content: str,
    user_direction: str,
    chain_summary: str,
) -> str:
    return (
        "You are a product thinking assistant.\n"
        "All output — node content, edge labels, and any text — MUST be in English.\n\n"
        f"Current idea node:\n{content}\n\n"
        f"Path so far:\n{chain_summary}\n\n"
        f"User's direction: {user_direction}\n\n"
        "Generate 1-2 child ideas that follow the user's direction.\n"
        'Return a JSON object with key "nodes" containing an array of objects, each with "content" and "edge_label":\n'
        '{"nodes": [{"content": "...", "edge_label": "<short label>"}, ...]}\n'
        "Only return the JSON object, no other text."
    )


def summarize_path_prompt(node_chain_text: str) -> str:
    return (
        "Summarize this idea evolution chain in 2-3 sentences, "
        "explaining the reasoning arc from start to finish.\n"
        "The summary MUST be written in English.\n\n"
        f"{node_chain_text}\n\n"
        'Return a JSON object: {"summary": "<your summary paragraph>"}'
    )


def build_prd_requirements_prompt(*, context: dict[str, object]) -> str:
    """Prompt for Stage-A parallel call: generate requirements only."""
    return (
        "You are a senior PM. Given the product context below, generate 6-12 well-defined "
        "product requirements. Each requirement needs: id (req-001...), title, description, "
        "rationale, 2-8 acceptance_criteria (list of strings), "
        "source_refs (list of step2/step3/step4).\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        "Return JSON: {\"requirements\": [...]}"
    )


def build_prd_markdown_prompt(*, context: dict[str, object]) -> str:
    """Prompt for Stage-A parallel call: generate markdown narrative + sections only."""
    return (
        "You are a senior PM. Given the product context below, write a delivery-ready PRD "
        "as markdown with 6-12 named sections (executive summary, personas, capabilities, etc). "
        "Be concrete and implementation-ready.\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        "Return JSON: {\"markdown\": \"...\", \"sections\": [{\"id\":\"...\",\"title\":\"...\",\"content\":\"...\"}]}"
    )


def build_prd_backlog_prompt(
    *,
    context: dict[str, object],
    requirement_ids: list[str],
) -> str:
    """Prompt for Stage-B call: generate backlog items referencing requirement IDs."""
    return (
        "You are a senior PM. Given the product context and requirement IDs below, "
        "generate 8-15 executable backlog items. Each item needs: id (bl-001...), title, summary, "
        "requirement_id (must be one of the provided IDs), priority (P0/P1/P2), "
        "type (epic/story/task), 2-8 acceptance_criteria, "
        "source_refs (step2/step3/step4), depends_on (list of bl-ids, may be empty). "
        "Out-of-scope items must not be P0.\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        f"requirement_ids={json.dumps(requirement_ids)}\n"
        "Return JSON: {\"backlog\": {\"items\": [...]}}"
    )
