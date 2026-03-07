"""Tests for signal_monitor — the LangGraph-based market signal monitor.

Follows TDD: tests written before implementation.
"""
from __future__ import annotations

import os

os.environ.setdefault("DECISIONOS_CHROMA_PATH", "")  # force in-memory ChromaDB

import pytest
from unittest.mock import patch, MagicMock

from tests._test_env import ensure_required_seed_env


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Create a fresh SQLite database for each test."""
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    from app.db.bootstrap import initialize_database
    initialize_database()


@pytest.fixture(autouse=True)
def fresh_vector_store(monkeypatch):
    """Provide a fully isolated VectorStore for each test.

    Creates a brand-new in-memory VectorStore and patches get_vector_store
    everywhere so that no stale singleton data from other test modules leaks
    into signal monitor tests.
    """
    import app.agents.memory.vector_store as vs_mod
    from app.agents.memory.vector_store import VectorStore

    isolated = VectorStore(persist_directory=None)
    vs_mod._singleton = None

    monkeypatch.setattr(vs_mod, "get_vector_store", lambda: isolated)
    monkeypatch.setattr(
        "app.agents.graphs.proactive.signal_monitor.get_vector_store",
        lambda: isolated,
    )
    yield isolated
    vs_mod._singleton = None


def _mock_hn_response(hits: list[dict]) -> MagicMock:
    """Build a mock httpx response returning the given Algolia hits."""
    resp = MagicMock()
    resp.json.return_value = {"hits": hits}
    resp.raise_for_status.return_value = None
    return resp


FAKE_HIT_1 = {
    "objectID": "111",
    "title": "AI code review startup raises $10M",
    "url": "https://example.com/ai-code-review",
    "points": 200,
    "created_at": "2026-03-07T00:00:00Z",
}

FAKE_HIT_2 = {
    "objectID": "222",
    "title": "New competitor launches developer dashboard",
    "url": "https://devdash.io/launch",
    "points": 150,
    "created_at": "2026-03-07T01:00:00Z",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _make_idea(title: str, idea_seed: str) -> object:
    """Create an idea in the DB and add its summary to the vector store."""
    from app.db.repo_ideas import IdeaRepository
    from app.agents.memory.vector_store import get_vector_store
    repo = IdeaRepository()
    idea = repo.create_idea(title=title, idea_seed=idea_seed)
    vs = get_vector_store()
    vs.add_idea_summary(idea.id, idea_seed)
    return idea


@patch("app.core.hn_client.httpx.get")
def test_news_item_becomes_market_signal(mock_http_get):
    """Given a fake HN story, verify a MarketSignal record is created."""
    mock_http_get.return_value = _mock_hn_response([FAKE_HIT_1])

    _make_idea("AI code review tool", "AI code review tool for developers")

    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
    graph = build_signal_monitor_graph()
    result = graph.invoke({
        "workspace_id": "default",
        "idea_summaries": [],
        "signals_created": [],
        "links_created": [],
        "agent_thoughts": [],
    })

    signals = result.get("signals_created", [])
    assert len(signals) >= 1
    sig = signals[0]
    assert sig["title"] == "AI code review startup raises $10M"
    assert sig["signal_type"] == "market_news"

    # Verify the signal was persisted in SQLite
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    db_signals = repo.list_signals(workspace_id="default")
    assert any(s.title == "AI code review startup raises $10M" for s in db_signals)


@patch("app.core.hn_client.httpx.get")
def test_signal_links_to_idea_by_similarity(mock_http_get):
    """Verify that a signal gets linked to a relevant idea via vector similarity."""
    mock_http_get.return_value = _mock_hn_response([FAKE_HIT_1])

    # Use a seed identical to the news title so cosine distance stays well below threshold
    idea = _make_idea("AI code review startup raises $10M", "AI code review startup raises $10M")

    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
    graph = build_signal_monitor_graph()
    result = graph.invoke({
        "workspace_id": "default",
        "idea_summaries": [],
        "signals_created": [],
        "links_created": [],
        "agent_thoughts": [],
    })

    links = result.get("links_created", [])
    assert len(links) >= 1
    # At least one link should reference the idea
    idea_ids_linked = [lk["idea_id"] for lk in links]
    assert idea.id in idea_ids_linked

    # Verify the link was persisted in SQLite
    from app.db.repo_market_signals import MarketSignalRepository
    sig_repo = MarketSignalRepository()
    signal_links = sig_repo.list_signals_for_idea(idea.id)
    assert len(signal_links) >= 1
    assert signal_links[0].entity_type == "signal"


@patch("app.core.hn_client.httpx.get")
def test_signal_links_to_competitor_by_url_match(mock_http_get):
    """Verify that if the news URL matches a tracked competitor's canonical_url,
    the signal is also linked to that competitor via a matched idea."""
    mock_http_get.return_value = _mock_hn_response([FAKE_HIT_2])

    # Create a real idea with seed identical to news title for reliable similarity match
    idea = _make_idea("New competitor launches developer dashboard", "New competitor launches developer dashboard")

    # Create a tracked competitor whose canonical_url matches the news URL domain
    from app.db.repo_competitors import CompetitorRepository
    comp_repo = CompetitorRepository()
    comp = comp_repo.create_competitor(
        workspace_id="default",
        name="DevDash",
        canonical_url="https://devdash.io",
        status="tracked",
    )

    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
    graph = build_signal_monitor_graph()
    result = graph.invoke({
        "workspace_id": "default",
        "idea_summaries": [],
        "signals_created": [],
        "links_created": [],
        "agent_thoughts": [],
    })

    links = result.get("links_created", [])
    # Find competitor links
    comp_links = [lk for lk in links if lk.get("entity_type") == "competitor"]
    assert len(comp_links) >= 1
    assert comp_links[0]["entity_id"] == comp.id
    # The competitor link should reference a valid idea, not the competitor itself
    assert comp_links[0]["idea_id"] == idea.id


@patch("app.core.hn_client.httpx.get")
def test_deduplication_prevents_repeat_signals(mock_http_get):
    """Same news URL processed twice should produce only one signal."""
    mock_http_get.return_value = _mock_hn_response([FAKE_HIT_1])

    _make_idea("AI code review tool", "AI code review tool for developers")

    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
    graph = build_signal_monitor_graph()

    init_state = {
        "workspace_id": "default",
        "idea_summaries": [],
        "signals_created": [],
        "links_created": [],
        "agent_thoughts": [],
    }

    # Run 1
    result1 = graph.invoke(init_state)
    count1 = len(result1.get("signals_created", []))

    # Run 2 (same stories)
    result2 = graph.invoke(init_state)
    count2 = len(result2.get("signals_created", []))

    # Second run should create 0 new signals because the URL is already recorded
    assert count1 >= 1
    assert count2 == 0

    # DB should have exactly count1 signals total
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    all_signals = repo.list_signals(workspace_id="default", limit=100)
    assert len(all_signals) == count1
