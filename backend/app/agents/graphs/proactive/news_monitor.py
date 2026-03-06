from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core.hn_client import fetch_stories_for_topics  # keyword search, not trending feed
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store


SIMILARITY_THRESHOLD = 0.35  # cosine distance below this = relevant match


class NewsMonitorState(TypedDict):
    user_id: str
    idea_summaries: list[dict]   # [{idea_id, summary}] -- loaded from vector store
    notifications: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _load_ideas_for_topics(state: NewsMonitorState) -> dict[str, object]:
    """Load idea summaries from vector store to derive search topics."""
    vs = get_vector_store()
    data = vs._ideas.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    summaries = [{"idea_id": id_, "summary": doc} for id_, doc in zip(ids, docs) if doc]
    thought = {
        "agent": "news_monitor",
        "action": "loaded_ideas",
        "detail": f"Loaded {len(summaries)} ideas from vector store for topic extraction",
        "timestamp": utc_now_iso(),
    }
    return {"idea_summaries": summaries, "agent_thoughts": [thought]}


def _fetch_news(state: NewsMonitorState) -> dict[str, object]:
    """Fetch recent HN stories for topics derived from idea summaries.

    IMPORTANT: The Algolia API is keyword search, not a trending feed.
    We extract topic keywords from idea titles for targeted results.
    """
    summaries = state.get("idea_summaries", [])
    # Extract first 3-4 words from each idea title as search topics
    topics = []
    for s in summaries[:10]:  # cap at 10 ideas to avoid rate limits
        words = s["summary"].split()[:4]
        if words:
            topics.append(" ".join(words))

    if not topics:
        topics = ["AI startup product"]  # fallback if no ideas exist yet

    stories = fetch_stories_for_topics(topics, limit_per_topic=5)

    vs = get_vector_store()
    stored = 0
    for story in stories:
        if story.title and story.id:
            vs.add_news_item(
                news_id=f"hn-{story.id}",
                title=story.title,
                content=f"{story.title}. Points: {story.points}. URL: {story.url or ''}",
            )
            stored += 1

    thought = {
        "agent": "news_fetcher",
        "action": "fetched_news",
        "detail": f"Fetched {len(stories)} HN stories, stored {stored} in vector store",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _match_news_to_ideas(state: NewsMonitorState) -> dict[str, object]:
    """Find idea<->news matches above similarity threshold using vector search."""
    vs = get_vector_store()

    # Get all stored ideas
    idea_data = vs._ideas.get(include=["documents", "metadatas"])
    idea_ids = idea_data.get("ids") or []
    idea_docs = idea_data.get("documents") or []

    if not idea_ids:
        return {
            "notifications": [],
            "agent_thoughts": [{
                "agent": "news_matcher",
                "action": "no_ideas",
                "detail": "No ideas in vector store yet -- skip matching",
                "timestamp": utc_now_iso(),
            }],
        }

    # Get recent news items
    news_data = vs._news.get(include=["documents", "metadatas"])
    news_ids = news_data.get("ids") or []
    news_docs = news_data.get("documents") or []

    notifications = []
    matched_pairs: set[tuple[str, str]] = set()

    for news_id, news_doc in zip(news_ids[:20], news_docs[:20]):
        # Search ideas most similar to this news item
        if vs._ideas.count() == 0:
            continue
        results = vs._ideas.query(
            query_texts=[news_doc],
            n_results=min(3, vs._ideas.count()),
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idea_id, dist in zip(ids, distances):
            # ChromaDB cosine distance: 0 = identical, 1 = orthogonal
            if dist < SIMILARITY_THRESHOLD and (news_id, idea_id) not in matched_pairs:
                matched_pairs.add((news_id, idea_id))
                news_title = news_doc.split(".")[0][:80]
                notifications.append({
                    "news_id": news_id,
                    "news_title": news_title,
                    "idea_id": idea_id,
                    "distance": round(dist, 3),
                    "insight": (
                        f"Recent HN story '{news_title}' is relevant to your idea "
                        f"(similarity score: {round(1 - dist, 2):.0%})."
                    ),
                })

    thought = {
        "agent": "news_matcher",
        "action": "matched_news",
        "detail": f"Found {len(notifications)} relevant news<->idea matches above threshold",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": notifications, "agent_thoughts": [thought]}


def build_news_monitor_graph():
    graph = StateGraph(NewsMonitorState)
    graph.add_node("load_ideas_for_topics", _load_ideas_for_topics)
    graph.add_node("fetch_news", _fetch_news)
    graph.add_node("match_news_to_ideas", _match_news_to_ideas)
    graph.add_edge(START, "load_ideas_for_topics")
    graph.add_edge("load_ideas_for_topics", "fetch_news")
    graph.add_edge("fetch_news", "match_news_to_ideas")
    graph.add_edge("match_news_to_ideas", END)
    return graph.compile()
