from __future__ import annotations

from pydantic import BaseModel, Field


class IdeaNodeOut(BaseModel):
    id: str
    idea_id: str
    parent_id: str | None
    content: str
    expansion_pattern: str | None
    edge_label: str | None
    depth: int
    status: str
    created_at: str


class CreateRootNodeRequest(BaseModel):
    content: str = Field(min_length=1)


class UserExpandRequest(BaseModel):
    description: str = Field(max_length=2000)


class ConfirmPathRequest(BaseModel):
    node_chain: list[str]


class IdeaPathOut(BaseModel):
    id: str
    idea_id: str
    node_chain: list[str]
    path_md: str
    path_json: str
    created_at: str


EXPANSION_PATTERNS: list[dict[str, str]] = [
    {"id": "narrow_users", "label": "Narrow the Audience", "description": "Redefine the problem for a more precise user segment"},
    {"id": "expand_features", "label": "Expand Feature Scope", "description": "Extend adjacent capabilities beyond the core feature"},
    {"id": "shift_scenario", "label": "Shift the Scenario", "description": "Apply this idea to a different usage context"},
    {"id": "monetize", "label": "Monetization Variants", "description": "Explore alternative business model paths"},
    {"id": "simplify", "label": "Simplify to Core", "description": "Strip everything away — keep only the minimal viable kernel"},
]
