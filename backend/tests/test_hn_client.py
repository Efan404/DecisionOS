from __future__ import annotations

from unittest.mock import patch, MagicMock

from app.core.hn_client import search_hn_stories, fetch_stories_for_topics, HNStory


def test_search_hn_stories_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "hits": [
            {"objectID": "123", "title": "AI Startup", "url": "https://example.com",
             "points": 100, "created_at": "2026-01-01"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("app.core.hn_client.httpx.get", return_value=mock_response):
        stories = search_hn_stories("AI startup")

    assert len(stories) == 1
    assert isinstance(stories[0], HNStory)
    assert stories[0].id == "123"
    assert stories[0].title == "AI Startup"


def test_search_returns_empty_on_network_error():
    with patch("app.core.hn_client.httpx.get", side_effect=Exception("network down")):
        stories = search_hn_stories("anything")
    assert stories == []


def test_fetch_stories_for_topics_deduplicates():
    """Same story returned for two queries should appear only once."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "hits": [
            {"objectID": "42", "title": "Same Story", "url": None,
             "points": 50, "created_at": "2026-01-01"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("app.core.hn_client.httpx.get", return_value=mock_response):
        stories = fetch_stories_for_topics(["topic a", "topic b"], limit_per_topic=5)

    # The same objectID="42" appears for both queries but should be deduped
    assert len(stories) == 1
    assert stories[0].id == "42"


def test_fetch_stories_for_topics_empty_topics():
    """No queries → no stories."""
    stories = fetch_stories_for_topics([])
    assert stories == []
