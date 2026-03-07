from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class SignalRecord:
    id: str
    workspace_id: str
    signal_type: str
    title: str
    summary: str
    severity: str
    detected_at: str
    evidence_source_id: str | None
    payload_json: dict | None


@dataclass(frozen=True)
class LinkRecord:
    id: str
    idea_id: str
    entity_type: str
    entity_id: str
    link_reason: str
    relevance_score: float | None
    created_at: str


class MarketSignalRepository:

    def create_signal(
        self,
        workspace_id: str,
        signal_type: str,
        title: str,
        summary: str,
        severity: str,
        evidence_source_id: str | None = None,
        payload_json: dict | None = None,
    ) -> SignalRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        payload_str = json.dumps(payload_json, ensure_ascii=False) if payload_json is not None else None
        with db_session() as conn:
            conn.execute(
                "INSERT INTO market_signal "
                "(id, workspace_id, signal_type, title, summary, severity, detected_at, evidence_source_id, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, workspace_id, signal_type, title, summary, severity, now, evidence_source_id, payload_str),
            )
        return SignalRecord(
            id=record_id,
            workspace_id=workspace_id,
            signal_type=signal_type,
            title=title,
            summary=summary,
            severity=severity,
            detected_at=now,
            evidence_source_id=evidence_source_id,
            payload_json=payload_json,
        )

    def get_signal(self, signal_id: str) -> SignalRecord | None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT id, workspace_id, signal_type, title, summary, severity, "
                "detected_at, evidence_source_id, payload_json "
                "FROM market_signal WHERE id = ?",
                (signal_id,),
            ).fetchone()
        if row is None:
            return None
        return SignalRecord(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            signal_type=str(row["signal_type"]),
            title=str(row["title"]),
            summary=str(row["summary"]),
            severity=str(row["severity"]),
            detected_at=str(row["detected_at"]),
            evidence_source_id=str(row["evidence_source_id"]) if row["evidence_source_id"] is not None else None,
            payload_json=json.loads(str(row["payload_json"])) if row["payload_json"] is not None else None,
        )

    def list_signals(
        self,
        workspace_id: str,
        limit: int = 20,
    ) -> list[SignalRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, workspace_id, signal_type, title, summary, severity, "
                "detected_at, evidence_source_id, payload_json "
                "FROM market_signal WHERE workspace_id = ? ORDER BY detected_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        return [
            SignalRecord(
                id=str(row["id"]),
                workspace_id=str(row["workspace_id"]),
                signal_type=str(row["signal_type"]),
                title=str(row["title"]),
                summary=str(row["summary"]),
                severity=str(row["severity"]),
                detected_at=str(row["detected_at"]),
                evidence_source_id=str(row["evidence_source_id"]) if row["evidence_source_id"] is not None else None,
                payload_json=json.loads(str(row["payload_json"])) if row["payload_json"] is not None else None,
            )
            for row in rows
        ]

    def link_idea_entity(
        self,
        idea_id: str,
        entity_type: str,
        entity_id: str,
        link_reason: str,
        relevance_score: float | None = None,
    ) -> LinkRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "INSERT INTO idea_evidence_link "
                "(id, idea_id, entity_type, entity_id, link_reason, relevance_score, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, idea_id, entity_type, entity_id, link_reason, relevance_score, now),
            )
        return LinkRecord(
            id=record_id,
            idea_id=idea_id,
            entity_type=entity_type,
            entity_id=entity_id,
            link_reason=link_reason,
            relevance_score=relevance_score,
            created_at=now,
        )

    def list_linked_competitors_for_idea(self, idea_id: str) -> list[LinkRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, entity_type, entity_id, link_reason, relevance_score, created_at "
                "FROM idea_evidence_link WHERE idea_id = ? AND entity_type = 'competitor' "
                "ORDER BY created_at DESC",
                (idea_id,),
            ).fetchall()
        return [
            LinkRecord(
                id=str(row["id"]),
                idea_id=str(row["idea_id"]),
                entity_type=str(row["entity_type"]),
                entity_id=str(row["entity_id"]),
                link_reason=str(row["link_reason"]),
                relevance_score=float(row["relevance_score"]) if row["relevance_score"] is not None else None,
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def signal_exists_for_url(self, workspace_id: str, url: str) -> bool:
        """Check if a market_signal already exists whose payload_json contains the given URL."""
        with db_session() as conn:
            row = conn.execute(
                "SELECT 1 FROM market_signal "
                "WHERE workspace_id = ? AND json_extract(payload_json, '$.url') = ? LIMIT 1",
                (workspace_id, url),
            ).fetchone()
            return row is not None

    def list_signals_for_idea(self, idea_id: str) -> list[LinkRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, entity_type, entity_id, link_reason, relevance_score, created_at "
                "FROM idea_evidence_link WHERE idea_id = ? AND entity_type = 'signal' "
                "ORDER BY created_at DESC",
                (idea_id,),
            ).fetchall()
        return [
            LinkRecord(
                id=str(row["id"]),
                idea_id=str(row["idea_id"]),
                entity_type=str(row["entity_type"]),
                entity_id=str(row["entity_id"]),
                link_reason=str(row["link_reason"]),
                relevance_score=float(row["relevance_score"]) if row["relevance_score"] is not None else None,
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]
