from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentThought(TypedDict):
    agent: str
    action: str
    detail: str
    timestamp: str


class DecisionOSState(TypedDict):
    idea_id: str
    idea_seed: str
    current_stage: str
    opportunity_output: dict | None
    dag_path: dict | None
    feasibility_output: dict | None
    selected_plan_id: str | None
    scope_output: dict | None
    # Generic PRD output dict (stored in DB context_json as before)
    prd_output: dict | None
    # Typed intermediate PRD fields populated by the graph nodes
    prd_slim_context: dict | None        # built once in context_loader, shared by all writers
    prd_requirements: list[dict]          # from requirements_writer node
    prd_markdown: str                     # from markdown_writer node
    prd_sections: list[dict]              # from markdown_writer node
    prd_backlog_items: list[dict]         # from backlog_writer node
    prd_review_issues: list[str]          # from reviewer node
    agent_thoughts: Annotated[list[AgentThought], operator.add]
    retrieved_patterns: list[dict]
    retrieved_similar_ideas: list[dict]
    user_preferences: dict | None
