from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

SearchProviderKind = Literal["exa", "tavily", "hn_algolia"]


class SearchProviderConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SearchProviderKind
    api_key: str | None = None
    enabled: bool = True
    max_results: int = Field(default=5, ge=1, le=20)
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)


class SearchSettingsPayload(BaseModel):
    providers: list[SearchProviderConfig] = Field(default_factory=list)


class SearchSettingsDetail(SearchSettingsPayload):
    id: str
    created_at: str
    updated_at: str


class TestSearchProviderRequest(BaseModel):
    provider: SearchProviderConfig


class TestSearchProviderResponse(BaseModel):
    ok: bool
    latency_ms: int
    message: str
    sample_results: list[dict] = Field(default_factory=list)
