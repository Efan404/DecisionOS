from __future__ import annotations

import os


from app.agents.memory.vector_store import VectorStore


def test_vector_store_add_and_query():
    vs = VectorStore(persist_directory=None)
    vs.add_idea_summary(idea_id="vs-test-1", summary="AI-powered code review tool for developers")
    vs.add_idea_summary(idea_id="vs-test-2", summary="Recipe recommendation app for home cooks")
    vs.add_idea_summary(idea_id="vs-test-3", summary="Developer productivity dashboard with metrics")
    results = vs.search_similar_ideas(query="code analysis for software engineers", n_results=2)
    assert len(results) == 2
    result_ids = [r["idea_id"] for r in results]
    assert "vs-test-1" in result_ids


def test_vector_store_add_news_and_match():
    vs = VectorStore(persist_directory=None)
    vs.add_idea_summary(idea_id="vs-test-match-1", summary="AI-powered code review tool exclusively unique test idea")
    vs.add_news_item(
        news_id="vs-test-news-1",
        title="GitHub launches AI code review feature exclusively unique test news",
        content="GitHub announced a new AI-powered code review feature exclusively unique test today.",
    )
    matches = vs.match_news_to_ideas(news_id="vs-test-news-1", n_results=2)
    assert len(matches) >= 1
    # The test's own idea should be in the top matches
    match_ids = [m["idea_id"] for m in matches]
    assert "vs-test-match-1" in match_ids
