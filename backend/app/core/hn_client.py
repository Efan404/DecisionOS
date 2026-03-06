from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class HNStory:
    id: str          # objectID from Algolia
    title: str
    url: str | None
    points: int
    created_at: str


def search_hn_stories(query: str, limit: int = 10) -> list[HNStory]:
    """Fetch HN stories matching a keyword query via Algolia search.

    NOTE: This is a KEYWORD SEARCH, not a "top stories" or trending feed.
    The Algolia API returns stories matching the query text, not HN frontpage rankings.
    Use specific topic keywords (e.g. "mobile payment wallet") for best results.

    Returns empty list on any network/parse error (fail-open).
    """
    try:
        resp = httpx.get(
            HN_ALGOLIA_URL,
            params={"query": query, "tags": "story", "hitsPerPage": limit},
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        stories = []
        for hit in data.get("hits", []):
            stories.append(HNStory(
                id=str(hit.get("objectID", "")),
                title=str(hit.get("title", "")),
                url=hit.get("url"),
                points=int(hit.get("points") or 0),
                created_at=str(hit.get("created_at", "")),
            ))
        return stories
    except Exception as exc:
        logger.warning("hn_client.fetch_failed query=%r exc=%s", query, exc)
        return []


def fetch_stories_for_topics(topics: list[str], limit_per_topic: int = 5) -> list[HNStory]:
    """Fetch HN stories for each topic keyword and deduplicate by story ID.

    NOTE: The Algolia API is a keyword search, NOT a "top stories" or trending feed.
    Use specific topic keywords derived from your idea titles/seeds for best results.
    A generic query like 'product startup AI' returns different (and often irrelevant) results
    compared to topic-specific queries like 'mobile payment wallet India'.
    """
    seen: dict[str, HNStory] = {}
    for topic in topics:
        for story in search_hn_stories(query=topic, limit=limit_per_topic):
            if story.id not in seen:
                seen[story.id] = story
    return list(seen.values())
