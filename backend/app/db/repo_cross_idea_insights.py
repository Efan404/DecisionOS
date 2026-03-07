from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class InsightRecord:
    id: str
    workspace_id: str
    idea_a_id: str
    idea_b_id: str
    insight_type: str
    summary: str
    why_it_matters: str
    recommended_action: str
    confidence: float | None
    similarity_score: float | None
    evidence_json: dict | None
    fingerprint: str
    created_at: str
    updated_at: str


def _row_to_record(row) -> InsightRecord:
    evidence_raw = row["evidence_json"]
    evidence = json.loads(evidence_raw) if evidence_raw is not None else None
    return InsightRecord(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        idea_a_id=str(row["idea_a_id"]),
        idea_b_id=str(row["idea_b_id"]),
        insight_type=str(row["insight_type"]),
        summary=str(row["summary"]),
        why_it_matters=str(row["why_it_matters"]),
        recommended_action=str(row["recommended_action"]),
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        similarity_score=float(row["similarity_score"]) if row["similarity_score"] is not None else None,
        evidence_json=evidence,
        fingerprint=str(row["fingerprint"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class CrossIdeaInsightRepository:

    def create_or_update_insight(
        self,
        workspace_id: str,
        idea_a_id: str,
        idea_b_id: str,
        insight_type: str,
        summary: str,
        why_it_matters: str,
        recommended_action: str,
        confidence: float | None,
        similarity_score: float | None,
        evidence_json: dict | None,
        fingerprint: str,
    ) -> InsightRecord:
        # Canonical ordering: smaller id first
        a, b = sorted([idea_a_id, idea_b_id])
        record_id = str(uuid4())
        now = utc_now_iso()
        evidence_str = json.dumps(evidence_json, ensure_ascii=False) if evidence_json is not None else None

        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO cross_idea_insight (
                    id, workspace_id, idea_a_id, idea_b_id,
                    insight_type, summary, why_it_matters, recommended_action,
                    confidence, similarity_score, evidence_json,
                    fingerprint, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idea_a_id, idea_b_id, fingerprint) DO UPDATE SET
                    insight_type = excluded.insight_type,
                    summary = excluded.summary,
                    why_it_matters = excluded.why_it_matters,
                    recommended_action = excluded.recommended_action,
                    confidence = excluded.confidence,
                    similarity_score = excluded.similarity_score,
                    evidence_json = excluded.evidence_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record_id, workspace_id, a, b,
                    insight_type, summary, why_it_matters, recommended_action,
                    confidence, similarity_score, evidence_str,
                    fingerprint, now, now,
                ),
            )
            # Fetch the actual row (may be the existing one on conflict)
            row = conn.execute(
                "SELECT * FROM cross_idea_insight "
                "WHERE idea_a_id = ? AND idea_b_id = ? AND fingerprint = ?",
                (a, b, fingerprint),
            ).fetchone()

        return _row_to_record(row)

    def list_for_idea(self, idea_id: str) -> list[InsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM cross_idea_insight "
                "WHERE idea_a_id = ? OR idea_b_id = ? "
                "ORDER BY updated_at DESC",
                (idea_id, idea_id),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def list_recent_for_workspace(
        self,
        workspace_id: str,
        limit: int = 20,
    ) -> list[InsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM cross_idea_insight "
                "WHERE workspace_id = ? "
                "ORDER BY updated_at DESC "
                "LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        return [_row_to_record(row) for row in rows]
