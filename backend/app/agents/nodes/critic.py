from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def prd_reviewer_node(state: DecisionOSState) -> dict:
    """Review the generated PRD against scope and provide quality assessment."""
    prd = state.get("prd_output", {})
    scope = state.get("scope_output", {})

    markdown = prd.get("markdown", "") if prd else ""
    in_scope = scope.get("in_scope", []) if scope else []

    # Simple quality checks
    issues: list[str] = []
    if len(markdown) < 200:
        issues.append("PRD is unusually short")
    if in_scope:
        scope_titles = {item.get("title", "").lower() for item in in_scope if isinstance(item, dict)}
        md_lower = markdown.lower()
        missing = [t for t in scope_titles if t and t not in md_lower]
        if missing:
            issues.append(f"{len(missing)} scope items not mentioned in PRD")

    if issues:
        detail = f"Review found {len(issues)} issues: {'; '.join(issues)}"
    else:
        detail = "PRD passed quality review: all scope items covered, sufficient detail"

    thought: AgentThought = {
        "agent": "prd_reviewer",
        "action": "quality_review",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    logger.info("prd_reviewer idea_id=%s issues=%d", state["idea_id"], len(issues))
    return {"agent_thoughts": [thought]}
