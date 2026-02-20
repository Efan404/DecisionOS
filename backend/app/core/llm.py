from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TypeVar

from app.core import ai_gateway
from app.core import mock_data
from app.core import prompts
from app.core.settings import get_settings
from app.schemas.feasibility import FeasibilityInput, FeasibilityOutput
from app.schemas.idea import OpportunityInput, OpportunityOutput
from app.schemas.prd import PRDInput, PRDOutput
from app.schemas.scope import ScopeInput, ScopeOutput

SchemaT = TypeVar("SchemaT")
logger = logging.getLogger(__name__)


def generate_json(
    *,
    mock_factory: Callable[[], SchemaT],
    model_factory: Callable[[], SchemaT] | None = None,
) -> SchemaT:
    settings = get_settings()
    if settings.llm_mode != "mock" and model_factory is not None:
        try:
            return model_factory()
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI provider call failed, fallback to mock output: %s", exc)
    return mock_factory()


def generate_opportunity(payload: OpportunityInput) -> OpportunityOutput:
    return generate_json(
        mock_factory=lambda: mock_data.generate_opportunity_output(payload.idea_seed, count=payload.count),
        model_factory=lambda: ai_gateway.generate_structured(
            task="opportunity",
            user_prompt=prompts.build_opportunity_prompt(idea_seed=payload.idea_seed, count=payload.count),
            schema_model=OpportunityOutput,
        ),
    )


def generate_feasibility(payload: FeasibilityInput) -> FeasibilityOutput:
    return generate_json(
        mock_factory=lambda: mock_data.generate_feasibility_output(payload),
        model_factory=lambda: ai_gateway.generate_structured(
            task="feasibility",
            user_prompt=prompts.build_feasibility_prompt(
                idea_seed=payload.idea_seed,
                direction_id=payload.direction_id,
                direction_text=payload.direction_text,
                path_id=payload.path_id,
            ),
            schema_model=FeasibilityOutput,
        ),
    )


def generate_scope(payload: ScopeInput) -> ScopeOutput:
    return generate_json(
        mock_factory=lambda: mock_data.generate_scope_output(payload),
        model_factory=lambda: ai_gateway.generate_structured(
            task="scope",
            user_prompt=prompts.build_scope_prompt(
                idea_seed=payload.idea_seed,
                direction_id=payload.direction_id,
                direction_text=payload.direction_text,
                path_id=payload.path_id,
                selected_plan_id=payload.selected_plan_id,
                feasibility_payload=payload.feasibility.model_dump(mode="python"),
            ),
            schema_model=ScopeOutput,
        ),
    )


def generate_prd(payload: PRDInput) -> PRDOutput:
    return generate_json(
        mock_factory=lambda: mock_data.generate_prd_output(payload),
        model_factory=lambda: ai_gateway.generate_structured(
            task="prd",
            user_prompt=prompts.build_prd_prompt(
                idea_seed=payload.idea_seed,
                direction_text=payload.direction_text,
                selected_plan_id=payload.selected_plan_id,
                scope_payload=payload.scope.model_dump(mode="python"),
            ),
            schema_model=PRDOutput,
        ),
    )


def generate_expand_nodes(
    content: str,
    pattern_label: str,
    pattern_description: str,
    chain_summary: str,
) -> list[dict[str, str]]:
    """Return list of {content, edge_label} dicts for AI node expansion."""
    return generate_json(
        mock_factory=lambda: mock_data.MOCK_EXPAND_NODES,
    )


def generate_expand_node_user(
    content: str,
    user_direction: str,
    chain_summary: str,
) -> list[dict[str, str]]:
    """Return list of {content, edge_label} dicts for user-guided expansion."""
    return generate_json(
        mock_factory=lambda: mock_data.MOCK_EXPAND_NODES[:1],
    )


def generate_path_summary(node_chain_text: str) -> str:
    """Return a plain-text summary of a confirmed path."""
    settings = get_settings()
    if settings.llm_mode == "mock":
        return mock_data.MOCK_PATH_SUMMARY
    try:
        return mock_data.MOCK_PATH_SUMMARY
    except Exception:  # noqa: BLE001
        return mock_data.MOCK_PATH_SUMMARY
