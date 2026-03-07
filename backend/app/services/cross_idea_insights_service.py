from __future__ import annotations

import hashlib
import json
import logging

from app.agents.memory.vector_store import VectorStore, get_vector_store
from app.core import ai_gateway
from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository, InsightRecord
from app.db.repo_ideas import IdeaRepository
from app.db.repo_market_signals import MarketSignalRepository
from app.services.cross_idea_candidate_service import CrossIdeaCandidateService

logger = logging.getLogger(__name__)

_COMPOSITE_SCORE_THRESHOLD = 0.3

_LLM_PROMPT_TEMPLATE = """\
You are a product strategy analyst. Two product ideas may be related. \
Analyze their relationship and return a JSON object with these fields:

- insight_type: one of ('execution_reuse', 'merge_candidate', 'positioning_conflict', 'shared_audience', 'shared_capability', 'evidence_overlap')
- summary: 1-2 sentences describing the relationship
- why_it_matters: 1 sentence on the strategic implication
- recommended_action: one of ('review', 'compare_feasibility', 'reuse_scope', 'reuse_prd_requirements', 'merge_ideas', 'keep_separate')
- confidence: float between 0 and 1

Respond with ONLY a valid JSON object. No markdown, no explanation.

--- Pair Context ---
{pair_context}
"""

# Budget: ~1000 tokens estimated via len(text) // 4 → max 4000 chars
_TOKEN_BUDGET = 1000
_CHAR_BUDGET = _TOKEN_BUDGET * 4


class CrossIdeaInsightsService:
    def __init__(
        self,
        insight_repo: CrossIdeaInsightRepository | None = None,
        candidate_service: CrossIdeaCandidateService | None = None,
        idea_repo: IdeaRepository | None = None,
        signal_repo: MarketSignalRepository | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._idea_repo = idea_repo or IdeaRepository()
        self._signal_repo = signal_repo or MarketSignalRepository()
        self._vs = vector_store or get_vector_store()
        self._insight_repo = insight_repo or CrossIdeaInsightRepository()
        self._candidate_service = candidate_service or CrossIdeaCandidateService(
            vector_store=self._vs,
            signal_repo=self._signal_repo,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_anchor_idea(
        self,
        anchor_idea_id: str,
        workspace_id: str = "default",
    ) -> list[InsightRecord]:
        """Find related ideas for *anchor_idea_id* and analyze each strong pair."""
        idea = self._idea_repo.get_idea(anchor_idea_id)
        if idea is None:
            logger.warning("analyze_anchor_idea: idea %s not found", anchor_idea_id)
            return []

        anchor_summary = idea.idea_seed or idea.title
        candidates = self._candidate_service.find_related_ideas(
            anchor_idea_id=anchor_idea_id,
            anchor_summary=anchor_summary,
        )

        results: list[InsightRecord] = []
        for candidate in candidates:
            if candidate.composite_score <= _COMPOSITE_SCORE_THRESHOLD:
                logger.debug(
                    "Skipping weak candidate %s (score=%.3f)",
                    candidate.idea_id,
                    candidate.composite_score,
                )
                continue

            record = self.analyze_pair(
                idea_a_id=anchor_idea_id,
                idea_b_id=candidate.idea_id,
                similarity_score=candidate.similarity_score,
                workspace_id=workspace_id,
            )
            if record is not None:
                results.append(record)

        return results

    def analyze_pair(
        self,
        idea_a_id: str,
        idea_b_id: str,
        similarity_score: float,
        workspace_id: str = "default",
    ) -> InsightRecord | None:
        """Analyze a single pair of ideas using the LLM and persist the result."""
        pair_context = self.build_pair_context(idea_a_id, idea_b_id)
        prompt = _LLM_PROMPT_TEMPLATE.format(pair_context=pair_context)

        try:
            raw = ai_gateway.generate_text(task="opportunity", user_prompt=prompt)
        except Exception:
            logger.exception(
                "LLM call failed for pair (%s, %s)", idea_a_id, idea_b_id
            )
            return None

        parsed = self._parse_llm_response(raw)
        if parsed is None:
            logger.warning(
                "Could not parse LLM response for pair (%s, %s): %.200s",
                idea_a_id,
                idea_b_id,
                raw,
            )
            return None

        insight_type = parsed["insight_type"]
        summary = parsed["summary"]
        fingerprint = hashlib.md5(
            f"{insight_type}:{summary[:100]}".encode()
        ).hexdigest()

        return self._insight_repo.create_or_update_insight(
            workspace_id=workspace_id,
            idea_a_id=idea_a_id,
            idea_b_id=idea_b_id,
            insight_type=insight_type,
            summary=summary,
            why_it_matters=parsed["why_it_matters"],
            recommended_action=parsed["recommended_action"],
            confidence=parsed["confidence"],
            similarity_score=similarity_score,
            evidence_json=None,
            fingerprint=fingerprint,
        )

    def build_pair_context(self, idea_a_id: str, idea_b_id: str) -> str:
        """Build a bounded comparison text for the two ideas."""
        idea_a = self._idea_repo.get_idea(idea_a_id)
        idea_b = self._idea_repo.get_idea(idea_b_id)

        parts: list[str] = []

        # -- Core idea info (highest priority) --
        if idea_a:
            parts.append(f"Idea A: {idea_a.title}")
            if idea_a.idea_seed:
                parts.append(f"  Seed: {idea_a.idea_seed}")
            parts.append(f"  Stage: {idea_a.stage}")
        else:
            parts.append(f"Idea A: (id={idea_a_id}, not found)")

        if idea_b:
            parts.append(f"Idea B: {idea_b.title}")
            if idea_b.idea_seed:
                parts.append(f"  Seed: {idea_b.idea_seed}")
            parts.append(f"  Stage: {idea_b.stage}")
        else:
            parts.append(f"Idea B: (id={idea_b_id}, not found)")

        core_text = "\n".join(parts)

        # -- Shared competitors (medium priority) --
        comps_a = {
            link.entity_id
            for link in self._signal_repo.list_linked_competitors_for_idea(idea_a_id)
        }
        comps_b = {
            link.entity_id
            for link in self._signal_repo.list_linked_competitors_for_idea(idea_b_id)
        }
        shared_comp_ids = comps_a & comps_b

        comp_lines: list[str] = []
        if shared_comp_ids:
            from app.db.repo_competitors import CompetitorRepository

            comp_repo = CompetitorRepository()
            for cid in list(shared_comp_ids)[:5]:
                comp = comp_repo.get_competitor(cid)
                if comp:
                    comp_lines.append(f"  - {comp.name}")

        comp_section = ""
        if comp_lines:
            comp_section = "\nShared Competitors:\n" + "\n".join(comp_lines)

        # -- Shared signals (lower priority) --
        sigs_a = {
            link.entity_id
            for link in self._signal_repo.list_signals_for_idea(idea_a_id)
        }
        sigs_b = {
            link.entity_id
            for link in self._signal_repo.list_signals_for_idea(idea_b_id)
        }
        shared_sig_ids = sigs_a & sigs_b

        sig_lines: list[str] = []
        if shared_sig_ids:
            for sid in list(shared_sig_ids)[:5]:
                sig = self._signal_repo.get_signal(sid)
                if sig:
                    sig_lines.append(f"  - {sig.title}")

        sig_section = ""
        if sig_lines:
            sig_section = "\nShared Market Signals:\n" + "\n".join(sig_lines)

        # -- Assemble with budget enforcement --
        # Start with core, then add competitor section, then signal section
        context = core_text
        if comp_section and len((context + comp_section)) // 4 <= _TOKEN_BUDGET:
            context += comp_section
        if sig_section and len((context + sig_section)) // 4 <= _TOKEN_BUDGET:
            context += sig_section

        # Final trim if somehow still over budget (shouldn't happen with the guards)
        if len(context) > _CHAR_BUDGET:
            context = context[:_CHAR_BUDGET]

        return context

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_llm_response(raw: str) -> dict | None:
        """Try to extract a valid insight dict from the LLM response text."""
        text = raw.strip()

        # Strip markdown fences
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        # Direct parse
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return _validate_insight_dict(obj)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: extract first JSON object
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict):
                                return _validate_insight_dict(obj)
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

        return None


def _validate_insight_dict(obj: dict) -> dict | None:
    """Validate that the dict has the required fields with correct types."""
    required = ("insight_type", "summary", "why_it_matters", "recommended_action", "confidence")
    for key in required:
        if key not in obj:
            return None

    valid_insight_types = (
        "execution_reuse",
        "merge_candidate",
        "positioning_conflict",
        "shared_audience",
        "shared_capability",
        "evidence_overlap",
    )
    valid_actions = (
        "review",
        "compare_feasibility",
        "reuse_scope",
        "reuse_prd_requirements",
        "merge_ideas",
        "keep_separate",
    )

    if obj["insight_type"] not in valid_insight_types:
        return None
    if obj["recommended_action"] not in valid_actions:
        return None

    try:
        obj["confidence"] = float(obj["confidence"])
    except (TypeError, ValueError):
        return None

    if not (0 <= obj["confidence"] <= 1):
        return None

    return {
        "insight_type": str(obj["insight_type"]),
        "summary": str(obj["summary"]),
        "why_it_matters": str(obj["why_it_matters"]),
        "recommended_action": str(obj["recommended_action"]),
        "confidence": obj["confidence"],
    }
