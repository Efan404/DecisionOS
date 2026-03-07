from __future__ import annotations

from fastapi import APIRouter

from app.core.search_gateway import test_provider_connection
from app.db.repo_search import SearchSettingsRepository, _MASK_SENTINEL, to_schema
from app.schemas.search_settings import (
    SearchSettingsDetail,
    SearchSettingsPayload,
    TestSearchProviderRequest,
    TestSearchProviderResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])
_repo = SearchSettingsRepository()


@router.get("/search", response_model=SearchSettingsDetail)
async def get_search_settings() -> SearchSettingsDetail:
    return to_schema(_repo.get_settings())


@router.patch("/search", response_model=SearchSettingsDetail)
async def patch_search_settings(payload: SearchSettingsPayload) -> SearchSettingsDetail:
    existing = _repo.get_settings()
    existing_keys = {p.id: p.api_key for p in existing.config.providers}
    for provider in payload.providers:
        if provider.api_key and _MASK_SENTINEL in provider.api_key:
            provider.api_key = existing_keys.get(provider.id)
    return to_schema(_repo.update_settings(payload))


@router.post("/search/test", response_model=TestSearchProviderResponse)
async def test_search_provider(payload: TestSearchProviderRequest) -> TestSearchProviderResponse:
    ok, latency_ms, message, sample_results = test_provider_connection(payload.provider)
    return TestSearchProviderResponse(
        ok=ok, latency_ms=latency_ms, message=message, sample_results=sample_results
    )
