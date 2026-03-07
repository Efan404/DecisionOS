"""Rule-based strategy router for feasibility analysis.

Inspects idea_seed keywords to recommend a primary business archetype
(bootstrapped / vc_funded / platform) before plan generation begins.

Zero LLM calls — pure keyword scoring, ~0.1ms latency.
The recommendation is stored in state.recommended_strategy and used by
the plan_generator to surface the most relevant archetype first.
"""
from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)

# keyword groups → strategy weight
_RULES: list[tuple[list[str], str]] = [
    # Platform / ecosystem signals
    (["marketplace", "platform", "network", "two-sided", "ecosystem", "partner", "integration"], "platform"),
    # VC / growth signals
    (["saas", "subscription", "b2b", "enterprise", "api", "consumer", "social", "viral",
      "growth", "user acquisition", "funding", "scale"], "vc_funded"),
    # Bootstrapped / indie signals
    (["tool", "plugin", "utility", "indie", "personal", "niche", "self-hosted",
      "open source", "community", "developer", "github", "cli", "productivity"], "bootstrapped"),
]

_ARCHETYPE_LABELS = {
    "bootstrapped": "Bootstrapped / Capital-Light",
    "vc_funded": "VC-Funded / Growth-First",
    "platform": "Platform / Ecosystem / Partner-Led",
}


def strategy_router_node(state: DecisionOSState) -> dict[str, object]:
    """Recommend a primary feasibility archetype via keyword rule matching.

    Scores each strategy based on keyword matches in idea_seed.
    Ties default to 'bootstrapped' (lowest burn, safest assumption for unknowns).
    The recommendation is advisory — plan_generator still generates all 3 archetypes,
    but surfaces the recommended one first in the SSE stream.
    """
    idea_seed = (state.get("idea_seed") or "").lower()

    scores: dict[str, int] = {"bootstrapped": 0, "vc_funded": 0, "platform": 0}
    matched_rules: list[str] = []

    for keywords, strategy in _RULES:
        hits = [kw for kw in keywords if kw in idea_seed]
        if hits:
            scores[strategy] += len(hits)
            matched_rules.append(f"{hits[0]}→{strategy}")

    # Max score wins; ties (including zero-signal) default to bootstrapped (safest assumption)
    # Tiebreak: bootstrapped=2, vc_funded=1, platform=0 — higher tiebreak wins on equal score
    tiebreak = {"bootstrapped": 2, "vc_funded": 1, "platform": 0}
    recommended = max(scores, key=lambda s: (scores[s], tiebreak[s]))

    label = _ARCHETYPE_LABELS[recommended]
    signal_summary = (
        ", ".join(matched_rules) if matched_rules
        else "no strong keyword signal — defaulting to bootstrapped"
    )

    thought: AgentThought = {
        "agent": "strategy_router",
        "action": "rule_based_routing",
        "detail": (
            f"Strategy scores: bootstrapped={scores['bootstrapped']} "
            f"vc_funded={scores['vc_funded']} platform={scores['platform']}. "
            f"Recommended: {label}. Signals: {signal_summary}."
        ),
        "timestamp": utc_now_iso(),
    }

    logger.info(
        "strategy_router idea_id=%s recommended=%s scores=%s",
        state.get("idea_id"), recommended, scores,
    )
    return {"recommended_strategy": recommended, "agent_thoughts": [thought]}
