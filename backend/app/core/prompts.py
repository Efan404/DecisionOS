from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are the DecisionOS backend planner. Always return strict JSON matching the requested schema. "
    "Never include markdown or extra prose."
)


def build_opportunity_prompt(*, idea_seed: str, count: int) -> str:
    return (
        f"Generate exactly {count} opportunity directions for this idea seed: {idea_seed!r}. "
        "Each direction must contain: id, title, one_liner, pain_tags. "
        "Use ids in order starting from A (A, B, C, ...). "
        "Return JSON object with key 'directions'."
    )

FEASIBILITY_PROMPT = (
    "Given an idea seed, selected direction, and path, produce exactly three feasibility plans "
    "with scoring and reasoning."
)

SCOPE_PROMPT = (
    "Given a selected plan and feasibility output, classify features into in_scope and out_scope."
)

PRD_PROMPT = "Generate a concise MVP PRD markdown from approved scope."


def build_feasibility_prompt(
    *,
    idea_seed: str,
    direction_id: str,
    direction_text: str,
    path_id: str,
) -> str:
    return (
        f"{FEASIBILITY_PROMPT}\n"
        f"idea_seed={idea_seed!r}\n"
        f"direction_id={direction_id!r}\n"
        f"direction_text={direction_text!r}\n"
        f"path_id={path_id!r}\n"
        "Return JSON with key 'plans'."
    )


def build_scope_prompt(
    *,
    idea_seed: str,
    direction_id: str,
    direction_text: str,
    path_id: str,
    selected_plan_id: str,
    feasibility_payload: dict[str, object],
) -> str:
    return (
        f"{SCOPE_PROMPT}\n"
        f"idea_seed={idea_seed!r}\n"
        f"direction_id={direction_id!r}\n"
        f"direction_text={direction_text!r}\n"
        f"path_id={path_id!r}\n"
        f"selected_plan_id={selected_plan_id!r}\n"
        f"feasibility={json.dumps(feasibility_payload, ensure_ascii=False)}\n"
        "Return JSON with keys 'in_scope' and 'out_scope'."
    )


def build_prd_prompt(
    *,
    idea_seed: str,
    direction_text: str,
    selected_plan_id: str,
    scope_payload: dict[str, object],
) -> str:
    return (
        f"{PRD_PROMPT}\n"
        f"idea_seed={idea_seed!r}\n"
        f"direction_text={direction_text!r}\n"
        f"selected_plan_id={selected_plan_id!r}\n"
        f"scope={json.dumps(scope_payload, ensure_ascii=False)}\n"
        "Return JSON with keys 'markdown' and 'sections'."
    )


def expand_node_prompt(
    content: str,
    pattern_label: str,
    pattern_description: str,
    chain_summary: str,
) -> str:
    return (
        "You are a product thinking assistant helping explore an idea through structured lenses.\n\n"
        f"Current idea node:\n{content}\n\n"
        f"Path so far:\n{chain_summary}\n\n"
        f"Expansion lens: {pattern_label} — {pattern_description}\n\n"
        "Generate 2-3 distinct child ideas that extend the current node through this lens.\n"
        "Return JSON array:\n"
        "[\n"
        f'  {{"content": "...", "edge_label": "{pattern_label}"}},\n'
        "  ...\n"
        "]\n"
        "Only return the JSON array, no other text."
    )


def expand_node_user_prompt(
    content: str,
    user_direction: str,
    chain_summary: str,
) -> str:
    return (
        "You are a product thinking assistant.\n\n"
        f"Current idea node:\n{content}\n\n"
        f"Path so far:\n{chain_summary}\n\n"
        f"User's direction: {user_direction}\n\n"
        "Generate 1-2 child ideas that follow the user's direction.\n"
        "Return JSON array:\n"
        "[\n"
        '  {"content": "...", "edge_label": "<short label for the relationship>"},\n'
        "  ...\n"
        "]\n"
        "Only return the JSON array, no other text."
    )


def summarize_path_prompt(node_chain_text: str) -> str:
    return (
        "Summarize this idea evolution chain in 2-3 sentences, "
        "explaining the reasoning arc from start to finish:\n\n"
        f"{node_chain_text}\n\n"
        "Return only the summary paragraph."
    )
