from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import PriorityLevel
from app.schemas.feasibility import ConfirmedDAGContextInput, FeasibilityOutput


class InScopeItem(BaseModel):
    id: str
    title: str
    desc: str
    priority: PriorityLevel


class OutScopeItem(BaseModel):
    id: str
    title: str
    desc: str
    reason: str


class ScopeInput(ConfirmedDAGContextInput):
    idea_seed: str = Field(min_length=1)
    selected_plan_id: str = Field(min_length=1)
    feasibility: FeasibilityOutput


class ScopeOutput(BaseModel):
    in_scope: list[InScopeItem]
    out_scope: list[OutScopeItem]


ScopeBaselineStatus = Literal["draft", "frozen", "superseded"]
ScopeBaselineLane = Literal["in", "out"]


class ScopeBaselineItemIn(BaseModel):
    lane: ScopeBaselineLane
    content: str = Field(min_length=1)


class ScopeBaselineItemOut(BaseModel):
    id: str
    baseline_id: str
    lane: ScopeBaselineLane
    content: str
    display_order: int = Field(ge=0)
    created_at: str


class ScopeBaselineOut(BaseModel):
    id: str
    idea_id: str
    version: int = Field(ge=1)
    status: ScopeBaselineStatus
    source_baseline_id: str | None = None
    created_at: str
    frozen_at: str | None = None
    items: list[ScopeBaselineItemOut]


class ScopeBootstrapDraftRequest(BaseModel):
    version: int = Field(ge=1)
    items: list[ScopeBaselineItemIn] = Field(default_factory=list)


class ScopePatchDraftRequest(BaseModel):
    version: int = Field(ge=1)
    items: list[ScopeBaselineItemIn]


class ScopeFreezeRequest(BaseModel):
    version: int = Field(ge=1)


class ScopeNewVersionRequest(BaseModel):
    version: int = Field(ge=1)


class ScopeMutationResponse(BaseModel):
    idea_id: str
    idea_version: int = Field(ge=1)
    data: ScopeBaselineOut
