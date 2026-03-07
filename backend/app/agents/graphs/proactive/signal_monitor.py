"""Signal monitor — converts web search results into MarketSignal records linked to ideas/competitors.

Runs alongside (not replacing) the existing news_monitor.py.
Uses repositories directly (not the service layer).
"""
from __future__ import annotations

import logging
import operator
from typing import TypedDict, Annotated
from urllib.parse import urlparse

from langgraph.graph import StateGraph, START, END

from app.core.search_gateway import search as search_web, SearchResult
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store
from app.db.repo_market_signals import MarketSignalRepository
from app.db.repo_competitors import CompetitorRepository
from app.db.repo_ideas import IdeaRepository

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.35  # cosine distance below this = relevant match


class SignalMonitorState(TypedDict):
    workspace_id: str
    idea_summaries: list[dict]        # [{idea_id, summary}] — populated by load node
    signals_created: list[dict]       # output: signals that were created this run
    links_created: list[dict]         # output: idea/competitor links created
    agent_thoughts: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def _load_ideas(state: SignalMonitorState) -> dict:
    """Load idea summaries from the vector store for topic extraction."""
    vs = get_vector_store()
    data = vs._ideas.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    summaries = [{"idea_id": id_, "summary": doc} for id_, doc in zip(ids, docs) if doc]
    return {
        "idea_summaries": summaries,
        "agent_thoughts": [{
            "agent": "signal_monitor",
            "action": "loaded_ideas",
            "detail": f"Loaded {len(summaries)} ideas for signal matching",
            "timestamp": utc_now_iso(),
        }],
    }


def _fetch_and_create_signals(state: SignalMonitorState) -> dict:
    """Fetch web search results, create EvidenceSource + MarketSignal for each new URL.

    Deduplicates by checking if a signal with the same URL already exists.
    """
    workspace_id = state.get("workspace_id", "default")
    summaries = state.get("idea_summaries", [])

    # Build search queries from idea summaries
    queries: list[str] = []
    for s in summaries[:5]:
        words = s["summary"].split()[:6]
        if words:
            queries.append(" ".join(words))
    if not queries:
        queries = ["AI startup product market"]

    # Use search_gateway (falls back to HN Algolia if no provider configured)
    all_results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for query in queries:
        for result in search_web(query, max_results=5):
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                all_results.append(result)

    sig_repo = MarketSignalRepository()
    comp_repo = CompetitorRepository()
    vs = get_vector_store()

    signals_created: list[dict] = []

    for result in all_results:
        url = result.url
        title = result.title or "Untitled"

        # --- Dedup: skip if we already have a signal for this URL ---
        if sig_repo.signal_exists_for_url(workspace_id, url):
            continue

        # Create EvidenceSource (raw search result)
        # source_type must be one of the DB-allowed values; map search provider kinds to "news"
        try:
            evidence = comp_repo.create_evidence_source(
                source_type="news",
                url=url,
                title=title,
                snippet=result.snippet[:200] if result.snippet else None,
                confidence=result.score,
            )
        except Exception:
            logger.warning("signal_monitor: failed to create evidence_source for %s", url, exc_info=True)
            continue

        # Compute severity from score
        score = result.score or 0.0
        severity = "high" if score > 0.8 else ("medium" if score > 0.5 else "low")

        # Create MarketSignal
        try:
            signal = sig_repo.create_signal(
                workspace_id=workspace_id,
                signal_type="market_news",
                title=title,
                summary=result.snippet or title,
                severity=severity,
                evidence_source_id=evidence.id,
                payload_json={"url": url, "source": result.source, "score": result.score, "published_date": result.published_date},
            )
        except Exception:
            logger.warning("signal_monitor: failed to create signal for %s", url, exc_info=True)
            continue

        # Store in vector store for future matching
        vs.add_market_signal_chunk(
            chunk_id=f"signal-{signal.id}",
            text=f"{title}. {result.snippet or ''}. {url}",
            metadata={
                "entity_type": "market_signal_summary",
                "entity_id": signal.id,
                "workspace_id": workspace_id,
                "source_type": result.source,
                "created_at": utc_now_iso(),
                "confidence": result.score,
            },
        )

        signals_created.append({
            "signal_id": signal.id,
            "evidence_source_id": evidence.id,
            "title": title,
            "url": url,
            "signal_type": "market_news",
            "severity": severity,
        })

    return {
        "signals_created": signals_created,
        "agent_thoughts": [{
            "agent": "signal_monitor",
            "action": "created_signals",
            "detail": f"Created {len(signals_created)} new market signals from {len(all_results)} search results",
            "timestamp": utc_now_iso(),
        }],
    }


def _link_signals_to_ideas_and_competitors(state: SignalMonitorState) -> dict:
    """Link newly created signals to ideas (vector similarity) and competitors (URL match).

    Only links to ideas that exist in the SQLite `idea` table (FK constraint).
    For competitor URL matches, links are created for each idea that the signal
    already matched, associating the competitor with those ideas.
    """
    workspace_id = state.get("workspace_id", "default")
    signals_created = state.get("signals_created", [])

    if not signals_created:
        return {
            "links_created": [],
            "agent_thoughts": [{
                "agent": "signal_monitor",
                "action": "no_signals_to_link",
                "detail": "No new signals to link",
                "timestamp": utc_now_iso(),
            }],
        }

    vs = get_vector_store()
    sig_repo = MarketSignalRepository()
    comp_repo = CompetitorRepository()
    idea_repo = IdeaRepository()

    # Build set of valid idea IDs from DB (for FK constraint safety)
    try:
        all_ideas, _ = idea_repo.list_ideas(statuses=["draft", "active", "frozen"], limit=500)
        valid_idea_ids = {idea.id for idea in all_ideas}
    except Exception:
        valid_idea_ids = set()
        logger.warning("signal_monitor: failed to load ideas from DB", exc_info=True)

    # Load all tracked competitors for URL matching
    try:
        competitors = comp_repo.list_competitors(workspace_id=workspace_id)
    except Exception:
        competitors = []
        logger.warning("signal_monitor: failed to load competitors", exc_info=True)

    links_created: list[dict] = []

    for sig_info in signals_created:
        signal_id = sig_info["signal_id"]
        signal_title = sig_info["title"]
        signal_url = sig_info.get("url", "")

        linked_idea_ids: list[str] = []  # Track which ideas this signal linked to

        # --- Link to ideas by vector similarity ---
        idea_count = vs._ideas.count()
        if idea_count > 0:
            try:
                results = vs._ideas.query(
                    query_texts=[signal_title],
                    n_results=min(3, idea_count),
                )
                ids = results.get("ids", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for idea_id, dist in zip(ids, distances):
                    if dist < SIMILARITY_THRESHOLD and idea_id in valid_idea_ids:
                        try:
                            link = sig_repo.link_idea_entity(
                                idea_id=idea_id,
                                entity_type="signal",
                                entity_id=signal_id,
                                link_reason=f"News '{signal_title[:60]}' matches idea (similarity: {1 - dist:.0%})",
                                relevance_score=round(1 - dist, 3),
                            )
                            links_created.append({
                                "link_id": link.id,
                                "idea_id": idea_id,
                                "entity_type": "signal",
                                "entity_id": signal_id,
                                "relevance_score": link.relevance_score,
                            })
                            linked_idea_ids.append(idea_id)
                        except Exception:
                            logger.warning(
                                "signal_monitor: failed to link signal %s to idea %s",
                                signal_id, idea_id, exc_info=True,
                            )
            except Exception:
                logger.warning("signal_monitor: vector query failed for signal %s", signal_id, exc_info=True)

        # --- Link to competitors by URL domain match ---
        # For each competitor whose domain matches the signal URL, create a
        # competitor link for every idea that the signal already matched.
        if signal_url and linked_idea_ids:
            signal_domain = _extract_domain(signal_url)
            for comp in competitors:
                if comp.canonical_url:
                    comp_domain = _extract_domain(comp.canonical_url)
                    if comp_domain and signal_domain and comp_domain == signal_domain:
                        for idea_id in linked_idea_ids:
                            try:
                                link = sig_repo.link_idea_entity(
                                    idea_id=idea_id,
                                    entity_type="competitor",
                                    entity_id=comp.id,
                                    link_reason=f"News URL domain '{signal_domain}' matches competitor '{comp.name}'",
                                )
                                links_created.append({
                                    "link_id": link.id,
                                    "idea_id": idea_id,
                                    "entity_type": "competitor",
                                    "entity_id": comp.id,
                                    "signal_id": signal_id,
                                })
                            except Exception:
                                logger.warning(
                                    "signal_monitor: failed to link competitor %s to idea %s for signal %s",
                                    comp.id, idea_id, signal_id, exc_info=True,
                                )

    return {
        "links_created": links_created,
        "agent_thoughts": [{
            "agent": "signal_monitor",
            "action": "linked_signals",
            "detail": f"Created {len(links_created)} links (idea + competitor)",
            "timestamp": utc_now_iso(),
        }],
    }


def _push_signal_notifications(state: SignalMonitorState) -> dict:
    """Create market_signal notifications for medium/high severity signals linked to ideas."""
    from app.db.repo_notifications import NotificationRepository
    notif_repo = NotificationRepository()

    signals_created = state.get("signals_created", [])
    links_created = state.get("links_created", [])

    # Set of signal_ids linked to at least one idea
    linked_signal_ids = {
        link["entity_id"] for link in links_created
        if link.get("entity_type") == "signal"
    }

    notifications_created = 0
    for sig_info in signals_created:
        signal_id = sig_info["signal_id"]
        severity = sig_info.get("severity", "low")

        if severity == "low" or signal_id not in linked_signal_ids:
            continue
        if notif_repo.exists_market_signal(signal_id):
            continue

        notif_repo.create(
            type="market_signal",
            title=f"Market Signal: {sig_info['title'][:60]}",
            body=f"New {severity}-relevance market signal detected that matches your ideas.",
            metadata={
                "signal_id": signal_id,
                "url": sig_info.get("url", ""),
                "severity": severity,
                "action_url": "/insights",
            },
        )
        notifications_created += 1

    return {
        "agent_thoughts": [{
            "agent": "signal_monitor",
            "action": "pushed_notifications",
            "detail": f"Created {notifications_created} market_signal notifications",
            "timestamp": utc_now_iso(),
        }],
    }


def _extract_domain(url: str) -> str:
    """Extract the registered domain from a URL (e.g. 'https://devdash.io/launch' -> 'devdash.io')."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Strip 'www.' prefix
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_signal_monitor_graph():
    graph = StateGraph(SignalMonitorState)
    graph.add_node("load_ideas", _load_ideas)
    graph.add_node("fetch_and_create_signals", _fetch_and_create_signals)
    graph.add_node("link_signals", _link_signals_to_ideas_and_competitors)
    graph.add_node("push_notifications", _push_signal_notifications)
    graph.add_edge(START, "load_ideas")
    graph.add_edge("load_ideas", "fetch_and_create_signals")
    graph.add_edge("fetch_and_create_signals", "link_signals")
    graph.add_edge("link_signals", "push_notifications")
    graph.add_edge("push_notifications", END)
    return graph.compile()
