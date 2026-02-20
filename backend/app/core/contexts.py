from __future__ import annotations

from uuid import uuid4

from app.core.time import utc_now_iso
from app.schemas.ideas import DecisionContext, IdeaStage


def create_default_context(idea_seed: str | None = None) -> DecisionContext:
    context = DecisionContext(
        session_id=str(uuid4()),
        created_at=utc_now_iso(),
        context_schema_version=1,
        scope_frozen=False,
    )
    if idea_seed is not None:
        context.idea_seed = idea_seed
    return context


def infer_stage_from_context(context: DecisionContext) -> IdeaStage:
    if context.prd is not None:
        return "prd"
    if context.scope is not None or bool(context.scope_frozen) or context.selected_plan_id is not None:
        return "scope_freeze"
    if context.feasibility is not None or context.confirmed_dag_path_id is not None:
        return "feasibility"
    return "idea_canvas"
