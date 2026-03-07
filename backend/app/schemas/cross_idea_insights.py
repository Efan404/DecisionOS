from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CrossIdeaInsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    idea_a_id: str
    idea_b_id: str
    insight_type: str
    summary: str
    why_it_matters: str
    recommended_action: str
    confidence: float | None = None
    similarity_score: float | None = None
    evidence_json: dict | None = None
    fingerprint: str
    created_at: str
    updated_at: str
    idea_a_title: str | None = None
    idea_b_title: str | None = None
