from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Competitor, ReasoningBreakdown, ScoreBreakdown


class ConfirmedDAGContextInput(BaseModel):
    confirmed_path_id: str = Field(min_length=1)
    confirmed_node_id: str = Field(min_length=1)
    confirmed_node_content: str = Field(min_length=1)
    confirmed_path_summary: str | None = Field(default=None, min_length=1)


class FeasibilityInput(ConfirmedDAGContextInput):
    idea_seed: str = Field(min_length=1)


class Plan(BaseModel):
    id: str
    name: str
    summary: str
    score_overall: float = Field(ge=0, le=10)
    scores: ScoreBreakdown
    reasoning: ReasoningBreakdown
    recommended_positioning: str
    competitors: list[Competitor] = Field(default_factory=list)


class FeasibilityOutput(BaseModel):
    plans: list[Plan] = Field(min_length=3, max_length=3)
