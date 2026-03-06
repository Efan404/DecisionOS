from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProviderKind = Literal["openai_compatible", "anthropic"]
TaskName = Literal["opportunity", "feasibility", "scope", "prd"]


class AIProviderConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: ProviderKind
    base_url: str = Field(min_length=1)
    api_key: str | None = None
    model: str | None = None
    enabled: bool = True
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class AISettingsPayload(BaseModel):
    providers: list[AIProviderConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_providers(self) -> AISettingsPayload:
        ids = [p.id for p in self.providers]
        if len(ids) != len(set(ids)):
            raise ValueError("Provider IDs must be unique")
        enabled_count = sum(1 for p in self.providers if p.enabled)
        if enabled_count > 1:
            raise ValueError("At most one provider may be enabled at a time")
        return self


class AISettingsDetail(AISettingsPayload):
    id: str
    created_at: str
    updated_at: str


class TestAIProviderRequest(BaseModel):
    provider: AIProviderConfig


class TestAIProviderResponse(BaseModel):
    ok: bool
    latency_ms: int
    message: str
