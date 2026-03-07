from __future__ import annotations

from dataclasses import dataclass

from app.agents.memory.vector_store import VectorStore
from app.db.repo_market_signals import MarketSignalRepository


@dataclass(frozen=True)
class CandidateIdea:
    idea_id: str
    similarity_score: float  # 0-1 (1 = most similar)
    shared_competitor_count: int
    shared_signal_count: int
    composite_score: float  # weighted combination


class CrossIdeaCandidateService:
    def __init__(
        self,
        vector_store: VectorStore,
        signal_repo: MarketSignalRepository,
    ) -> None:
        self._vs = vector_store
        self._signal_repo = signal_repo

    def find_related_ideas(
        self,
        anchor_idea_id: str,
        anchor_summary: str,
        limit: int = 5,
    ) -> list[CandidateIdea]:
        """Find candidate related ideas for an anchor idea.

        Steps:
        1. Vector similarity recall (search_similar_ideas)
        2. For each candidate, count shared competitors and signals
        3. Compute composite score = similarity + relational boosts
        4. Sort by composite score, limit results
        """
        # Step 1: Vector recall
        similar = self._vs.search_similar_ideas(
            query=anchor_summary,
            n_results=min(limit * 2, 10),  # over-fetch to allow filtering
            exclude_id=anchor_idea_id,
        )

        if not similar:
            return []

        # Step 2: Get anchor's linked entities for relational boosting
        anchor_competitors = {
            link.entity_id
            for link in self._signal_repo.list_linked_competitors_for_idea(anchor_idea_id)
        }
        anchor_signals = {
            link.entity_id
            for link in self._signal_repo.list_signals_for_idea(anchor_idea_id)
        }

        # Step 3: Score each candidate
        candidates: list[CandidateIdea] = []
        for item in similar:
            candidate_id = item["idea_id"]
            similarity = 1.0 - item["distance"]  # convert distance to similarity

            # Count shared entities
            candidate_competitors = {
                link.entity_id
                for link in self._signal_repo.list_linked_competitors_for_idea(candidate_id)
            }
            candidate_signals = {
                link.entity_id
                for link in self._signal_repo.list_signals_for_idea(candidate_id)
            }

            shared_comp = len(anchor_competitors & candidate_competitors)
            shared_sig = len(anchor_signals & candidate_signals)

            # Composite: base similarity + 0.1 per shared competitor + 0.05 per shared signal
            composite = similarity + (shared_comp * 0.1) + (shared_sig * 0.05)

            candidates.append(
                CandidateIdea(
                    idea_id=candidate_id,
                    similarity_score=round(similarity, 4),
                    shared_competitor_count=shared_comp,
                    shared_signal_count=shared_sig,
                    composite_score=round(composite, 4),
                )
            )

        # Step 4: Sort and limit
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        return candidates[:limit]
