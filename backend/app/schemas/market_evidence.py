from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    canonical_url: str | None = None
    category: str | None = None
    status: str
    created_at: str
    updated_at: str


class CompetitorSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    competitor_id: str
    snapshot_version: int
    summary_json: dict
    quality_score: float | None = None
    traction_score: float | None = None
    relevance_score: float | None = None
    underrated_score: float | None = None
    confidence: float | None = None
    created_at: str


class EvidenceSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    url: str
    title: str | None = None
    snippet: str | None = None
    published_at: str | None = None
    fetched_at: str
    confidence: float | None = None
    payload_json: dict | None = None


class MarketSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    signal_type: str
    title: str
    summary: str
    severity: str
    detected_at: str
    evidence_source_id: str | None = None
    payload_json: dict | None = None


class IdeaEvidenceLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idea_id: str
    entity_type: str
    entity_id: str
    link_reason: str
    relevance_score: float | None = None
    created_at: str
