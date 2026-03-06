from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")
os.environ.setdefault("DECISIONOS_CHROMA_PATH", "")  # force in-memory ChromaDB in tests

from unittest.mock import patch

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph


def _mock_generate_text(**kwargs):
    return '{"insight": "This news is relevant to your AI code review idea because it validates market demand."}'


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
@patch("app.core.hn_client.httpx.get")
def test_news_monitor_graph_runs(mock_http_get, mock_text):
    """News monitor graph executes without errors and produces notifications."""
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.json.return_value = {"hits": []}
    mock_response.raise_for_status.return_value = None
    mock_http_get.return_value = mock_response

    graph = build_news_monitor_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [],
        "notifications": [],
        "agent_thoughts": [],
    })
    assert "notifications" in result


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
def test_cross_idea_graph_runs(mock_text):
    """Cross-idea analyzer graph executes and produces insights."""
    graph = build_cross_idea_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [
            {"idea_id": "1", "summary": "AI code review"},
            {"idea_id": "2", "summary": "Developer dashboard"},
        ],
        "insights": [],
        "agent_thoughts": [],
    })
    assert "insights" in result


@patch("app.core.ai_gateway.generate_text", side_effect=_mock_generate_text)
def test_pattern_learner_graph_runs(mock_text):
    """Pattern learner graph executes and produces learned preferences."""
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI tool"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    assert "learned_preferences" in result
