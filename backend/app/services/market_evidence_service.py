from __future__ import annotations

from uuid import uuid4

from app.db.repo_competitors import CompetitorRepository, CompetitorRecord, SnapshotRecord, EvidenceSourceRecord
from app.db.repo_market_signals import MarketSignalRepository, SignalRecord, LinkRecord
from app.agents.memory.vector_store import VectorStore


class MarketEvidenceService:
    """Orchestrates competitor repos, market-signal repos, and the vector store.

    Kept intentionally thin — just wiring, no business logic beyond
    dedup-by-canonical-url and chunk mirroring.
    """

    def __init__(
        self,
        competitor_repo: CompetitorRepository,
        signal_repo: MarketSignalRepository,
        vector_store: VectorStore,
    ) -> None:
        self._comp_repo = competitor_repo
        self._signal_repo = signal_repo
        self._vs = vector_store

    # ------------------------------------------------------------------
    # Competitors
    # ------------------------------------------------------------------

    def upsert_competitor_card(
        self,
        workspace_id: str,
        name: str,
        canonical_url: str | None,
        category: str | None,
        summary_json: dict,
        scores: dict,
        confidence: float | None = None,
    ) -> tuple[CompetitorRecord, SnapshotRecord]:
        """Create or reuse a competitor (matched by canonical_url), then
        append a new snapshot and mirror chunks to the vector store."""

        # --- find existing competitor by canonical_url ---
        competitor: CompetitorRecord | None = None
        if canonical_url is not None:
            existing = self._comp_repo.list_competitors(workspace_id=workspace_id)
            for c in existing:
                if c.canonical_url == canonical_url:
                    competitor = c
                    break

        if competitor is None:
            competitor = self._comp_repo.create_competitor(
                workspace_id=workspace_id,
                name=name,
                canonical_url=canonical_url,
                category=category,
            )

        # --- create snapshot ---
        snapshot = self._comp_repo.create_snapshot(
            competitor_id=competitor.id,
            summary_json=summary_json,
            quality_score=scores.get("quality_score"),
            traction_score=scores.get("traction_score"),
            relevance_score=scores.get("relevance_score"),
            underrated_score=scores.get("underrated_score"),
            confidence=confidence,
        )

        # --- mirror to vector store ---
        self._index_snapshot_chunks(competitor, snapshot)

        return competitor, snapshot

    # ------------------------------------------------------------------
    # Market signals
    # ------------------------------------------------------------------

    def record_market_signal(
        self,
        workspace_id: str,
        signal_type: str,
        title: str,
        summary: str,
        severity: str,
        url: str | None = None,
        evidence_source_id: str | None = None,
    ) -> SignalRecord:
        """Record a market signal, optionally creating an evidence source
        from a URL, and mirror to the vector store."""

        if url is not None and evidence_source_id is None:
            ev_source = self._comp_repo.create_evidence_source(
                source_type="website",
                url=url,
                title=title,
            )
            evidence_source_id = ev_source.id

        signal = self._signal_repo.create_signal(
            workspace_id=workspace_id,
            signal_type=signal_type,
            title=title,
            summary=summary,
            severity=severity,
            evidence_source_id=evidence_source_id,
        )

        # mirror to vector store
        chunk_id = f"signal-{signal.id}"
        self._vs.add_market_signal_chunk(
            chunk_id=chunk_id,
            text=f"{title}. {summary}",
            metadata={
                "chunk_type": "market_signal",
                "signal_id": signal.id,
                "signal_type": signal_type,
                "severity": severity,
                "workspace_id": workspace_id,
            },
        )

        return signal

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------

    def link_evidence_to_idea(
        self,
        idea_id: str,
        entity_type: str,
        entity_id: str,
        link_reason: str,
        relevance_score: float | None = None,
    ) -> LinkRecord:
        """Delegate to the signal repo to create an idea-evidence link."""
        return self._signal_repo.link_idea_entity(
            idea_id=idea_id,
            entity_type=entity_type,
            entity_id=entity_id,
            link_reason=link_reason,
            relevance_score=relevance_score,
        )

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def build_and_store_insight(
        self,
        workspace_id: str,
        idea_id: str,
        insight_text: str,
        confidence: float = 0.5,
    ) -> str:
        """Store an evidence insight in the vector store and link it to
        the given idea.  Returns the chunk_id."""

        chunk_id = f"insight-{uuid4()}"

        self._vs.add_evidence_insight_chunk(
            chunk_id=chunk_id,
            text=insight_text,
            metadata={
                "chunk_type": "evidence_insight",
                "workspace_id": workspace_id,
                "idea_id": idea_id,
                "confidence": confidence,
            },
        )

        self.link_evidence_to_idea(
            idea_id=idea_id,
            entity_type="insight",
            entity_id=chunk_id,
            link_reason="auto-generated market insight",
            relevance_score=confidence,
        )

        return chunk_id

    # ------------------------------------------------------------------
    # Rebuild / re-index
    # ------------------------------------------------------------------

    def rebuild_market_chunks_for_competitor(self, competitor_id: str) -> int:
        """Re-index all chunks from the latest snapshot for a competitor.
        Returns the number of chunks written (0 if no snapshot)."""

        snapshot = self._comp_repo.get_latest_snapshot(competitor_id)
        if snapshot is None:
            return 0

        competitor = self._comp_repo.get_competitor(competitor_id)
        if competitor is None:
            return 0

        return self._index_snapshot_chunks(competitor, snapshot)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_snapshot_chunks(
        self,
        competitor: CompetitorRecord,
        snapshot: SnapshotRecord,
    ) -> int:
        """Write one vector-store chunk per key in the snapshot's
        summary_json.  Returns the number of chunks written."""
        count = 0
        for key, value in snapshot.summary_json.items():
            chunk_id = f"comp-{competitor.id}-{key}"
            text = f"{competitor.name} — {key}: {value}"
            self._vs.add_competitor_chunk(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    "chunk_type": "competitor",
                    "competitor_id": competitor.id,
                    "snapshot_id": snapshot.id,
                    "section": key,
                    "workspace_id": competitor.workspace_id,
                },
            )
            count += 1
        return count
