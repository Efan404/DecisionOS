from __future__ import annotations

from fastapi import APIRouter

from app.core.ai_gateway import test_provider_connection
from app.db.repo_ai import AISettingsRepository, _MASK_SENTINEL, to_schema
from app.schemas.ai_settings import (
    AISettingsDetail,
    AISettingsPayload,
    TestAIProviderRequest,
    TestAIProviderResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])
_repo = AISettingsRepository()


@router.get("/ai", response_model=AISettingsDetail)
async def get_ai_settings() -> AISettingsDetail:
    return to_schema(_repo.get_settings())


@router.patch("/ai", response_model=AISettingsDetail)
async def patch_ai_settings(payload: AISettingsPayload) -> AISettingsDetail:
    existing = _repo.get_settings()
    existing_keys = {p.id: p.api_key for p in existing.config.providers}
    for provider in payload.providers:
        if provider.api_key and _MASK_SENTINEL in provider.api_key:
            provider.api_key = existing_keys.get(provider.id)
    return to_schema(_repo.update_settings(payload))


@router.post("/ai/test", response_model=TestAIProviderResponse)
async def test_ai_provider(payload: TestAIProviderRequest) -> TestAIProviderResponse:
    ok, latency_ms, message = test_provider_connection(payload.provider)
    return TestAIProviderResponse(ok=ok, latency_ms=latency_ms, message=message)
