from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from app.agents.memory.vector_store import get_vector_store
from app.core import ai_gateway
from app.core.time import utc_now_iso


class NewsMonitorState(TypedDict):
    user_id: str
    idea_ids: list[str]
    notifications: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _fetch_news(state: NewsMonitorState) -> dict[str, object]:
    vs = get_vector_store()
    all_news = vs._news.get(include=["documents", "metadatas"])
    thought = {
        "agent": "news_fetcher",
        "action": "fetched_news",
        "detail": f"Retrieved {len(all_news['ids'])} news articles from database",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _match_news_to_ideas(state: NewsMonitorState) -> dict[str, object]:
    vs = get_vector_store()
    all_news = vs._news.get(include=["documents", "metadatas"])
    notifications: list[dict] = []

    for i, news_id in enumerate(all_news["ids"]):
        matches = vs.match_news_to_ideas(news_id=news_id, n_results=2)
        for match in matches:
            if match.get("distance", 1.0) < 0.5:
                notifications.append({
                    "type": "news_match",
                    "news_id": news_id,
                    "news_title": all_news["metadatas"][i].get("title", ""),
                    "idea_id": match["idea_id"],
                    "idea_summary": match.get("summary", ""),
                    "relevance": 1.0 - match.get("distance", 0),
                })

    thought = {
        "agent": "news_matcher",
        "action": "matched_news",
        "detail": f"Found {len(notifications)} relevant news-idea matches",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": notifications, "agent_thoughts": [thought]}


def _generate_insights(state: NewsMonitorState) -> dict[str, object]:
    notifications = state.get("notifications", [])
    enriched: list[dict] = []

    for notif in notifications[:5]:
        try:
            raw = ai_gateway.generate_text(
                task="opportunity",
                user_prompt=(
                    f"A news article titled '{notif.get('news_title', '')}' is relevant to an idea about "
                    f"'{notif.get('idea_summary', '')[:100]}'. "
                    "In 1-2 sentences, explain why this news matters for this idea and suggest one action. "
                    "Return plain text, no JSON."
                ),
            )
            notif["insight"] = raw.strip()
        except Exception:
            notif["insight"] = "This news article may be relevant to your idea."
        enriched.append(notif)

    thought = {
        "agent": "insight_generator",
        "action": "generated_insights",
        "detail": f"Generated insights for {len(enriched)} news matches",
        "timestamp": utc_now_iso(),
    }
    return {"notifications": enriched, "agent_thoughts": [thought]}


def build_news_monitor_graph():
    graph = StateGraph(NewsMonitorState)
    graph.add_node("fetch_news", _fetch_news)
    graph.add_node("match_to_ideas", _match_news_to_ideas)
    graph.add_node("generate_insights", _generate_insights)
    graph.add_edge(START, "fetch_news")
    graph.add_edge("fetch_news", "match_to_ideas")
    graph.add_edge("match_to_ideas", "generate_insights")
    graph.add_edge("generate_insights", END)
    return graph.compile()
