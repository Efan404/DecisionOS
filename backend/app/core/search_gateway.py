from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from urllib import request

from app.core.hn_client import search_hn_stories
from app.db.repo_search import SearchSettingsRepository
from app.schemas.search_settings import SearchProviderConfig

logger = logging.getLogger(__name__)

_settings_repo = SearchSettingsRepository()
_POST_JSON_MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str  # "exa" | "tavily" | "hn_algolia"
    published_date: str | None = None
    score: float | None = None


def _get_active_provider() -> SearchProviderConfig:
    settings = _settings_repo.get_settings().config
    enabled = [p for p in settings.providers if p.enabled]
    if not enabled:
        raise RuntimeError(
            "No search provider configured. Go to Settings → Search Provider to add one."
        )
    return enabled[0]


def search(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search using active provider. Gracefully falls back to HN Algolia if none configured."""
    try:
        provider = _get_active_provider()
    except RuntimeError:
        logger.info("search_gateway: no provider configured, falling back to HN Algolia")
        return _search_hn_algolia(query, max_results=max_results)

    logger.info("search_gateway.search provider=%s kind=%s query=%r", provider.id, provider.kind, query)
    if provider.kind == "exa":
        return _search_exa(provider, query, max_results=max_results)
    if provider.kind == "tavily":
        return _search_tavily(provider, query, max_results=max_results)
    if provider.kind == "hn_algolia":
        return _search_hn_algolia(query, max_results=max_results)
    raise RuntimeError(f"Unsupported search provider kind: {provider.kind}")


def _search_exa(provider: SearchProviderConfig, query: str, max_results: int) -> list[SearchResult]:
    body = {
        "query": query,
        "numResults": max_results,
        "contents": {"text": {"maxCharacters": 200}},
        "type": "neural",
    }
    try:
        data = _post_json(
            url="https://api.exa.ai/search",
            body=body,
            api_key=provider.api_key,
            timeout_seconds=provider.timeout_seconds,
            auth_header="Authorization",
            auth_prefix="Bearer ",
        )
        results = []
        for item in (data.get("results") or [])[:max_results]:
            results.append(SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str((item.get("text") or item.get("summary") or ""))[:300],
                source="exa",
                published_date=item.get("publishedDate"),
                score=item.get("score"),
            ))
        return results
    except Exception as exc:
        logger.warning("search_gateway.exa.failed query=%r exc=%s", query, exc)
        return []


def _search_tavily(provider: SearchProviderConfig, query: str, max_results: int) -> list[SearchResult]:
    body = {
        "api_key": provider.api_key or "",
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        data = _post_json(
            url="https://api.tavily.com/search",
            body=body,
            api_key=None,  # Tavily uses body api_key
            timeout_seconds=provider.timeout_seconds,
        )
        results = []
        for item in (data.get("results") or [])[:max_results]:
            results.append(SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or "")[:300],
                source="tavily",
                published_date=item.get("published_date"),
                score=item.get("score"),
            ))
        return results
    except Exception as exc:
        logger.warning("search_gateway.tavily.failed query=%r exc=%s", query, exc)
        return []


def _search_hn_algolia(query: str, max_results: int = 5) -> list[SearchResult]:
    stories = search_hn_stories(query=query, limit=max_results)
    return [
        SearchResult(
            title=s.title,
            url=s.url or f"https://news.ycombinator.com/item?id={s.id}",
            snippet=f"HN story · {s.points} points",
            source="hn_algolia",
            published_date=s.created_at,
        )
        for s in stories
    ]


def test_provider_connection(provider: SearchProviderConfig) -> tuple[bool, int, str, list[dict]]:
    started = time.perf_counter()
    try:
        if provider.kind == "hn_algolia":
            results = _search_hn_algolia("AI product", max_results=2)
        elif provider.kind == "exa":
            results = _search_exa(provider, "AI product", max_results=2)
        elif provider.kind == "tavily":
            results = _search_tavily(provider, "AI product", max_results=2)
        else:
            raise RuntimeError(f"Unknown kind: {provider.kind}")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        sample = [{"title": r.title, "url": r.url} for r in results]
        return True, elapsed_ms, f"OK — {len(results)} results returned", sample
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, elapsed_ms, str(exc), []


def _post_json(
    *,
    url: str,
    body: dict[str, object],
    api_key: str | None,
    timeout_seconds: float,
    auth_header: str = "Authorization",
    auth_prefix: str = "Bearer ",
) -> dict[str, object]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers[auth_header] = f"{auth_prefix}{api_key}"
    req = request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read(_POST_JSON_MAX_RESPONSE_BYTES).decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response shape from {url}")
    return data  # type: ignore[return-value]
