from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are the DecisionOS backend planner. Always return strict JSON matching the requested schema. "
    "Never include markdown or extra prose. "
    "All generated content (node text, labels, summaries) MUST be written in English. "
    "IMPORTANT: For array fields (like 'in_scope', 'out_scope'), each item MUST be an object with the exact fields "
    "defined in the schema - never return plain strings. "
    "Example: for in_scope items, return [{'id': 'uuid', 'title': 'text', 'desc': 'text', 'priority': 'high'}] "
    "NOT ['text1', 'text2']."
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
    "Given confirmed DAG context, selected plan and feasibility output, classify features into in_scope and out_scope. "
    "Generate multiple items (at least 3-5 in_scope items and 2-4 out_scope items) to comprehensively cover the project scope."
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
    market_evidence: str = "",
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
    prompt = (
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
        "  - competitors: array of 2-4 objects, each with name (product name), url (homepage URL or null), "
        "similarity (one sentence on what makes this competitor similar or relevant)\n"
        "Return a single JSON object representing this plan (not wrapped in an array or 'plans' key)."
    )
    if market_evidence:
        prompt += "\n\n## Market Evidence\n" + market_evidence
    return prompt


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
        "IMPORTANT: Generate multiple items for both in_scope and out_scope arrays. "
        "At least 3-5 in_scope items and 2-4 out_scope items. "
        "Return JSON with keys 'in_scope' and 'out_scope', each containing an array of items."
    )


def build_prd_prompt(
    *,
    context_pack: dict[str, object],
    market_evidence: str = "",
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

    prompt = (
        f"{PRD_PROMPT}\n"
        f"context={json.dumps(slim_context, ensure_ascii=False)}\n"
        "Constraints: 6-12 requirements; 8-15 backlog items; each item maps requirement_id; "
        "priority P0/P1/P2; type epic/story/task; >=2 acceptance_criteria per item; "
        "source_refs from step2/step3/step4; out_scope items must not be P0.\n"
        "Return JSON: markdown, sections, requirements, backlog, generation_meta."
    )
    if market_evidence:
        prompt += "\n\n## Market Evidence\n" + market_evidence
    return prompt


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
        "You are a senior PM writing a delivery-ready PRD. "
        "Given the product context below, generate 6-12 well-defined product requirements.\n\n"
        "Field writing rules:\n"
        "- id: req-001, req-002, ... in order\n"
        "- title: concise noun phrase (≤10 words)\n"
        "- description: 2-3 sentences — what this requirement is AND why it is needed. "
        "Be specific to this product, not generic.\n"
        "- rationale: 1-2 sentences on business or user value. Must NOT restate description.\n"
        "- acceptance_criteria: 3-6 items. Each item must be a verifiable behaviour statement. "
        'Format: "[Actor] can [specific action] and [observable outcome]". '
        'Good: "A logged-in user can reset their password via email and receives a confirmation within 30 seconds." '
        'Bad: "The system should handle errors properly."\n'
        "- source_refs: list containing one or more of step2, step3, step4\n\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        'Return JSON: {"requirements": [...]}'
    )


def build_prd_markdown_prompt(*, context: dict[str, object]) -> str:
    """Prompt for Stage-A parallel call: generate markdown narrative + sections only."""
    return (
        "You are a senior PM writing a delivery-ready PRD. "
        "Given the product context below, write a structured PRD as markdown with 6-12 named sections.\n\n"
        "Section writing rules:\n"
        "- Each section content must be ≥3 sentences and self-contained "
        "(a reader with no other context should understand it).\n"
        "- Follow this arc per section: background/context → problem or opportunity → "
        "approach or decision → expected outcome.\n"
        "- Required sections and their focus:\n"
        "  * Executive Summary: what this product is, who it serves, core value proposition (3-5 sentences)\n"
        "  * Problem Statement: specific user pain points + why current solutions are insufficient\n"
        "  * User Personas: 1-2 concrete personas each with role, primary goal, and key frustration\n"
        "  * Key Capabilities: user-facing capabilities described from the user perspective, not implementation\n"
        "  * Out of Scope: explicit list of what will NOT be built and why, to prevent scope creep\n"
        "  * Other sections (success metrics, technical considerations, etc.): ≥3 substantive sentences each\n"
        "- The markdown field should be the full document rendered as clean GitHub-flavoured markdown.\n\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        'Return JSON: {"markdown": "...", "sections": [{"id":"...","title":"...","content":"..."}]}'
    )


def build_prd_full_prompt(
    *, context: dict[str, object], n_requirements: int = 5, n_backlog: int = 8
) -> str:
    """Single-call prompt: generate requirements + markdown + backlog.

    n_requirements and n_backlog are pre-computed by build_prd_plan_prompt.
    sections field is omitted — frontend uses markdown directly.
    """
    return (
        f"You are a senior PM. Produce a concise PRD in ONE JSON response.\n\n"
        f"EXACT COUNTS (do not exceed): requirements={n_requirements}, backlog.items={n_backlog}\n\n"
        "requirements fields (per item):\n"
        "  id: req-001..., title: ≤8 words, description: 1-2 sentences,\n"
        "  rationale: 1 sentence, acceptance_criteria: 2-3 items,\n"
        "  source_refs: one or more of [step2, step3, step4]\n\n"
        "markdown: 6-8 sections. Required sections: Executive Summary, Problem & Opportunity, "
        "Key Capabilities, Technical Considerations, Out of Scope, Success Metrics. "
        "Add 1-2 optional sections (e.g. User Personas, Risks & Mitigations, Go-to-Market). "
        "Each section: 4-8 sentences with concrete detail. Total 800-1500 words. "
        "Use ## for section headers and bullet points where appropriate.\n\n"
        "backlog.items fields (per item):\n"
        "  id: bl-001..., title: ≤8 words, requirement_id: must match a req-NNN above,\n"
        "  priority: P0|P1|P2, type: epic|story|task, summary: 1 sentence,\n"
        "  acceptance_criteria: 2-3 items, source_refs, depends_on: []\n\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n\n"
        'Return ONLY valid JSON, no markdown fences:\n'
        '{"requirements":[...],"markdown":"...","backlog":{"items":[...]}}'
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


def build_prd_plan_prompt(*, in_scope_count: int, out_scope_count: int, idea_seed: str) -> str:
    """Fast pre-flight call: estimate appropriate requirements and backlog counts.

    Returns JSON: {"n_requirements": int, "n_backlog": int, "rationale": str}
    """
    return (
        "You are a senior PM scoping a PRD. Given the product scope below, "
        "decide the appropriate number of requirements and backlog items.\n\n"
        f"Product idea: {idea_seed}\n"
        f"IN scope items: {in_scope_count}\n"
        f"OUT scope items: {out_scope_count}\n\n"
        "Rules:\n"
        "- n_requirements: 1 requirement per 1-2 IN scope items, min 3, max 8\n"
        "- n_backlog: 1.5x n_requirements rounded up, min 5, max 12\n"
        "- Keep it lean — fewer, more impactful items beat long lists\n\n"
        'Return ONLY JSON: {"n_requirements": <int>, "n_backlog": <int>, "rationale": "<1 sentence>"}'
    )
