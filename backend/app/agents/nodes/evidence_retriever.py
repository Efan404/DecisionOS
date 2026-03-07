"""Market evidence retrieval helper for prompt injection.

Retrieves relevant market evidence (competitors, signals, insights) from the
vector store and formats them into a concise text summary respecting a hard
token budget cap.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Hard token budget: estimated as len(text) // 4
_TOKEN_BUDGET = 800
_CHAR_BUDGET = _TOKEN_BUDGET * 4  # 3200 chars


def retrieve_market_evidence_context(query: str, n_results: int = 5) -> str:
    """Retrieve market evidence from the vector store and format as context text.

    Args:
        query: The idea seed or summary text to use as the search query.
        n_results: Maximum number of evidence chunks to retrieve.

    Returns:
        A formatted string of market evidence context, or empty string if none
        found or on error. Never raises.
    """
    try:
        from app.agents.memory.vector_store import get_vector_store
        vs = get_vector_store()
        results = vs.search_market_evidence(query=query, n_results=n_results)

        if not results:
            return ""

        return _format_evidence(results)

    except Exception:
        logger.warning("Market evidence retrieval failed — continuing without evidence", exc_info=True)
        return ""


def _format_evidence(results: list[dict]) -> str:
    """Format evidence results into a text summary within the token budget.

    Strategy:
    1. Try all results (up to n_results).
    2. If over budget, fall back to top-2 entries.
    3. If still over budget, trim individual summaries.
    """
    text = _build_evidence_text(results)

    if len(text) // 4 <= _TOKEN_BUDGET:
        return text

    # Fall back to top-2 entries
    text = _build_evidence_text(results[:2])

    if len(text) // 4 <= _TOKEN_BUDGET:
        return text

    # Still over budget — trim individual entries
    trimmed: list[dict] = []
    for entry in results[:2]:
        trimmed_entry = dict(entry)
        entry_text = entry.get("text", "")
        # Trim text to fit roughly half the char budget per entry
        max_per_entry = _CHAR_BUDGET // 2 - 50  # leave room for formatting
        if len(entry_text) > max_per_entry:
            trimmed_entry["text"] = entry_text[:max_per_entry] + "..."
        trimmed.append(trimmed_entry)

    text = _build_evidence_text(trimmed)

    # Final safety: hard truncate if still over
    if len(text) > _CHAR_BUDGET:
        text = text[:_CHAR_BUDGET]

    return text


def _build_evidence_text(results: list[dict]) -> str:
    """Build formatted evidence text from a list of evidence results."""
    if not results:
        return ""

    lines: list[str] = []
    for i, entry in enumerate(results, start=1):
        text = entry.get("text", "").strip()
        meta = entry.get("metadata", {})
        source_type = meta.get("source_type", "evidence")
        label_parts: list[str] = [source_type]
        if meta.get("competitor_name"):
            label_parts.append(meta["competitor_name"])
        label = " | ".join(label_parts)

        lines.append(f"[{i}] ({label}) {text}")

    return "\n".join(lines)
