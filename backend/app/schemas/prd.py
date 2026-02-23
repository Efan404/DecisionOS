from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import PriorityLevel
from app.schemas.feasibility import Plan
from app.schemas.scope import InScopeItem, OutScopeItem


PrdSourceRef = Literal["step2", "step3", "step4"]
PrdBacklogType = Literal["epic", "story", "task"]


class PRDSection(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class PRDRequirement(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=2, max_length=8)
    source_refs: list[PrdSourceRef] = Field(min_length=1)


class PRDBacklogItem(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    priority: PriorityLevel
    type: PrdBacklogType
    summary: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=2, max_length=8)
    source_refs: list[PrdSourceRef] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)


class PRDBacklog(BaseModel):
    items: list[PRDBacklogItem] = Field(min_length=8, max_length=15)


class PRDGenerationMeta(BaseModel):
    provider_id: str | None = None
    model: str | None = None
    confirmed_path_id: str = Field(min_length=1)
    selected_plan_id: str = Field(min_length=1)
    baseline_id: str = Field(min_length=1)


class PRDRequirementsOutput(BaseModel):
    """Output of the parallel requirements LLM call."""
    requirements: list[PRDRequirement] = Field(min_length=6, max_length=12)


class PRDMarkdownOutput(BaseModel):
    """Output of the parallel markdown+sections LLM call."""
    markdown: str
    sections: list[PRDSection] = Field(min_length=6)


class PRDBacklogOutput(BaseModel):
    """Output of the Stage-B backlog LLM call (requires requirement IDs)."""
    backlog: PRDBacklog


class PRDOutput(BaseModel):
    markdown: str
    sections: list[PRDSection] = Field(min_length=6)
    requirements: list[PRDRequirement] = Field(min_length=6, max_length=12)
    backlog: PRDBacklog
    generation_meta: PRDGenerationMeta


class PrdPathNode(BaseModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    expansion_pattern: str | None = None
    edge_label: str | None = None
    depth: int = Field(ge=0)


class PrdStep2Path(BaseModel):
    path_id: str = Field(min_length=1)
    path_md: str = Field(min_length=1)
    path_json: dict[str, object]
    path_summary: str = Field(min_length=1)
    leaf_node_id: str = Field(min_length=1)
    leaf_node_content: str = Field(min_length=1)


class PrdPlanBrief(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    score_overall: float = Field(ge=0, le=10)
    recommended_positioning: str = Field(min_length=1)


class PrdStep3Feasibility(BaseModel):
    selected_plan: Plan
    alternatives_brief: list[PrdPlanBrief] = Field(default_factory=list)


class PrdBaselineMeta(BaseModel):
    baseline_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: Literal["draft", "frozen", "superseded"]
    source_baseline_id: str | None = None


class PrdStep4Scope(BaseModel):
    baseline_meta: PrdBaselineMeta
    in_scope: list[InScopeItem]
    out_scope: list[OutScopeItem]


class PrdContextPack(BaseModel):
    idea_seed: str = Field(min_length=1)
    step2_path: PrdStep2Path
    step3_feasibility: PrdStep3Feasibility
    step4_scope: PrdStep4Scope


class PrdBundle(BaseModel):
    baseline_id: str = Field(min_length=1)
    context_fingerprint: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    generation_meta: PRDGenerationMeta
    output: PRDOutput


class PrdFeedbackDimensions(BaseModel):
    clarity: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    scope_fit: int = Field(ge=1, le=5)


class PrdFeedbackLatest(BaseModel):
    baseline_id: str = Field(min_length=1)
    submitted_at: str = Field(min_length=1)
    rating_overall: int = Field(ge=1, le=5)
    rating_dimensions: PrdFeedbackDimensions
    comment: str | None = Field(default=None, max_length=2000)
