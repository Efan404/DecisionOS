import uuid
import pytest
from unittest.mock import patch, MagicMock
from app.core.search_gateway import SearchResult


def test_signal_monitor_uses_search_gateway_not_hn_directly():
    """signal_monitor must call search_gateway.search, not fetch_stories_for_topics directly."""
    from app.agents.graphs.proactive import signal_monitor
    import inspect
    source = inspect.getsource(signal_monitor)
    assert "search_web(" in source or "search as search_web" in source, \
        "signal_monitor must use search_gateway.search (search_web) not HN directly"
    assert "fetch_stories_for_topics" not in source, \
        "signal_monitor must NOT call fetch_stories_for_topics directly"


def test_push_node_exists_in_signal_monitor():
    """build_signal_monitor_graph must include push_notifications node."""
    from app.db.bootstrap import initialize_database
    initialize_database()
    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph
    graph = build_signal_monitor_graph()
    node_names = list(graph.nodes)
    assert "push_notifications" in node_names, \
        f"Expected 'push_notifications' node, got: {node_names}"


def test_exists_market_signal_dedup():
    """NotificationRepository.exists_market_signal returns correct dedup result."""
    from app.db.bootstrap import initialize_database
    initialize_database()
    from app.db.repo_notifications import NotificationRepository
    repo = NotificationRepository()

    # Use unique IDs per run to avoid cross-test pollution
    signal_id = f"signal-test-{uuid.uuid4().hex}"
    other_signal_id = f"signal-other-{uuid.uuid4().hex}"

    # Before creating: should not exist
    assert repo.exists_market_signal(signal_id) is False

    # Create a market_signal notification
    repo.create(
        type="market_signal",
        title="Test signal",
        body="Test body",
        metadata={"signal_id": signal_id, "action_url": "/insights"},
    )

    # After creating: should exist
    assert repo.exists_market_signal(signal_id) is True

    # Different signal_id: should not exist
    assert repo.exists_market_signal(other_signal_id) is False
