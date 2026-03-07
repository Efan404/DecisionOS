from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.feasibility import FeasibilityInput, FeasibilityOutput
from app.schemas.idea import OpportunityInput, OpportunityOutput
from app.schemas.prd import (
    PRDOutput,
    PrdBundle,
    PrdFeedbackDimensions,
    PrdFeedbackLatest,
    PrdPptOutput,
)
from app.schemas.scope import ScopeInput, ScopeOutput

IdeaStage = Literal["idea_canvas", "feasibility", "scope_freeze", "prd"]
IdeaStatus = Literal["draft", "active", "frozen", "archived"]


class DecisionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    context_schema_version: int = Field(default=1, ge=1)
    idea_seed: str | None = None
    opportunity: OpportunityOutput | None = None
    feasibility: FeasibilityOutput | None = None
    selected_plan_id: str | None = Field(default=None, min_length=1)
    scope: ScopeOutput | None = None
    scope_frozen: bool = False
    current_scope_baseline_id: str | None = Field(default=None, min_length=1)
    current_scope_baseline_version: int | None = Field(default=None, ge=1)
    prd: PRDOutput | None = None
    prd_bundle: PrdBundle | None = None
    prd_feedback_latest: PrdFeedbackLatest | None = None
    prd_ppt: PrdPptOutput | None = None
    confirmed_dag_path_id: str | None = None
    confirmed_dag_node_id: str | None = Field(default=None, min_length=1)
    confirmed_dag_node_content: str | None = Field(default=None, min_length=1)
    confirmed_dag_path_summary: str | None = Field(default=None, min_length=1)


class WorkspaceDetail(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str


class IdeaSummary(BaseModel):
    id: str
    workspace_id: str
    title: str
    idea_seed: str | None = None
    stage: IdeaStage
    status: IdeaStatus
    version: int
    created_at: str
    updated_at: str
    archived_at: str | None = None


class IdeaDetail(IdeaSummary):
    context: DecisionContext


class IdeaListResponse(BaseModel):
    items: list[IdeaSummary]
    next_cursor: str | None = None


class CreateIdeaRequest(BaseModel):
    title: str = Field(min_length=1)
    idea_seed: str | None = Field(default=None, min_length=1)


class PatchIdeaRequest(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1)
    status: IdeaStatus | None = None

    @model_validator(mode="after")
    def _validate_non_empty_patch(self) -> PatchIdeaRequest:
        if self.title is None and self.status is None:
            raise ValueError("At least one of title or status must be provided")
        return self


class PatchIdeaContextRequest(BaseModel):
    version: int = Field(ge=1)
    context: dict[str, object]


class OpportunityIdeaRequest(OpportunityInput):
    version: int = Field(ge=1)


class FeasibilityIdeaRequest(FeasibilityInput):
    version: int = Field(ge=1)


class ScopeIdeaRequest(ScopeInput):
    version: int = Field(ge=1)


class PRDIdeaRequest(BaseModel):
    version: int = Field(ge=1)
    baseline_id: str = Field(min_length=1)


class PRDFeedbackRequest(BaseModel):
    version: int = Field(ge=1)
    baseline_id: str = Field(min_length=1)
    rating_overall: int = Field(ge=1, le=5)
    rating_dimensions: PrdFeedbackDimensions
    comment: str | None = Field(default=None, max_length=2000)


class OpportunityAgentResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: OpportunityOutput


class FeasibilityAgentResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: FeasibilityOutput


class ScopeAgentResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: ScopeOutput


class PRDAgentResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: PRDOutput


class PRDFeedbackResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: PrdFeedbackLatest


class PRDPptIdeaRequest(BaseModel):
    version: int = Field(ge=1)


class PRDPptAgentResponse(BaseModel):
    idea_id: str
    idea_version: int
    data: PrdPptOutput
