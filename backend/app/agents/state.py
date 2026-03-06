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
    prd_output: dict | None
    agent_thoughts: Annotated[list[AgentThought], operator.add]
    retrieved_patterns: list[dict]
    retrieved_similar_ideas: list[dict]
    user_preferences: dict | None
