import pytest
from unittest.mock import patch, MagicMock
from app.schemas.search_settings import SearchProviderConfig, SearchSettingsPayload
from app.core.search_gateway import search, SearchResult, _search_hn_algolia

def test_search_result_dataclass():
    r = SearchResult(title="Test", url="https://example.com", snippet="desc", source="exa")
    assert r.title == "Test"
    assert r.url == "https://example.com"
    assert r.source == "exa"
    assert r.published_date is None

def test_search_falls_back_to_hn_when_no_provider():
    """search() falls back to HN Algolia when no provider configured."""
    from app.core.hn_client import HNStory
    fake_stories = [
        HNStory(id="1", title="AI tools", url="https://example.com", points=100, created_at="2026-01-01"),
    ]
    with patch("app.core.search_gateway._get_active_provider") as mock_provider, \
         patch("app.core.search_gateway._search_hn_algolia") as mock_hn:
        mock_provider.side_effect = RuntimeError("No search provider configured")
        mock_hn.return_value = [SearchResult(title="AI tools", url="https://example.com", snippet="HN story · 100 points", source="hn_algolia")]
        results = search("AI tools", max_results=5)
    mock_hn.assert_called_once()
    assert len(results) == 1
    assert results[0].source == "hn_algolia"

def test_search_hn_algolia_returns_search_results():
    """_search_hn_algolia wraps HN stories into SearchResult objects."""
    from app.core.hn_client import HNStory
    fake_stories = [
        HNStory(id="42", title="Open source AI PM tool", url="https://github.com/example/tool", points=200, created_at="2026-03-01"),
        HNStory(id="43", title="No URL story", url=None, points=50, created_at="2026-03-01"),
    ]
    with patch("app.core.search_gateway.search_hn_stories", return_value=fake_stories):
        results = _search_hn_algolia("AI PM tool", max_results=5)
    assert len(results) == 2
    assert results[0].title == "Open source AI PM tool"
    assert results[0].url == "https://github.com/example/tool"
    assert results[0].source == "hn_algolia"
    # Story with no URL should get HN URL
    assert "news.ycombinator.com" in results[1].url

def test_search_dispatches_to_exa_when_configured():
    """search() calls _search_exa when active provider is exa kind."""
    from app.schemas.search_settings import SearchProviderConfig
    exa_provider = SearchProviderConfig(
        id="exa1", name="Exa", kind="exa", api_key="test-key",
        enabled=True, max_results=5, timeout_seconds=15.0
    )
    fake_results = [SearchResult(title="Result", url="https://exa.ai/r", snippet="text", source="exa")]
    with patch("app.core.search_gateway._get_active_provider", return_value=exa_provider), \
         patch("app.core.search_gateway._search_exa", return_value=fake_results) as mock_exa:
        results = search("test query")
    mock_exa.assert_called_once_with(exa_provider, "test query", max_results=5)
    assert results == fake_results
