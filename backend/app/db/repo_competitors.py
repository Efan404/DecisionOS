from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class CompetitorRecord:
    id: str
    workspace_id: str
    name: str
    canonical_url: str | None
    category: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SnapshotRecord:
    id: str
    competitor_id: str
    snapshot_version: int
    summary_json: dict
    quality_score: float | None
    traction_score: float | None
    relevance_score: float | None
    underrated_score: float | None
    confidence: float | None
    created_at: str


@dataclass(frozen=True)
class EvidenceSourceRecord:
    id: str
    source_type: str
    url: str
    title: str | None
    snippet: str | None
    published_at: str | None
    fetched_at: str
    confidence: float | None
    payload_json: dict | None


class CompetitorRepository:

    def create_competitor(
        self,
        workspace_id: str,
        name: str,
        canonical_url: str | None = None,
        category: str | None = None,
        status: str = "candidate",
    ) -> CompetitorRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "INSERT INTO competitor (id, workspace_id, name, canonical_url, category, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, workspace_id, name, canonical_url, category, status, now, now),
            )
        return CompetitorRecord(
            id=record_id,
            workspace_id=workspace_id,
            name=name,
            canonical_url=canonical_url,
            category=category,
            status=status,
            created_at=now,
            updated_at=now,
        )

    def get_competitor(self, competitor_id: str) -> CompetitorRecord | None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT id, workspace_id, name, canonical_url, category, status, created_at, updated_at "
                "FROM competitor WHERE id = ?",
                (competitor_id,),
            ).fetchone()
        if row is None:
            return None
        return CompetitorRecord(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            name=str(row["name"]),
            canonical_url=str(row["canonical_url"]) if row["canonical_url"] is not None else None,
            category=str(row["category"]) if row["category"] is not None else None,
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def list_competitors(
        self,
        workspace_id: str,
        status: str | None = None,
    ) -> list[CompetitorRecord]:
        if status is not None:
            query = (
                "SELECT id, workspace_id, name, canonical_url, category, status, created_at, updated_at "
                "FROM competitor WHERE workspace_id = ? AND status = ? ORDER BY updated_at DESC"
            )
            params: tuple = (workspace_id, status)
        else:
            query = (
                "SELECT id, workspace_id, name, canonical_url, category, status, created_at, updated_at "
                "FROM competitor WHERE workspace_id = ? ORDER BY updated_at DESC"
            )
            params = (workspace_id,)
        with db_session() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CompetitorRecord(
                id=str(row["id"]),
                workspace_id=str(row["workspace_id"]),
                name=str(row["name"]),
                canonical_url=str(row["canonical_url"]) if row["canonical_url"] is not None else None,
                category=str(row["category"]) if row["category"] is not None else None,
                status=str(row["status"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def create_snapshot(
        self,
        competitor_id: str,
        summary_json: dict,
        quality_score: float | None = None,
        traction_score: float | None = None,
        relevance_score: float | None = None,
        underrated_score: float | None = None,
        confidence: float | None = None,
    ) -> SnapshotRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        with db_session() as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_version) AS max_ver FROM competitor_snapshot WHERE competitor_id = ?",
                (competitor_id,),
            ).fetchone()
            current_max = row["max_ver"] if row is not None and row["max_ver"] is not None else 0
            next_version = int(current_max) + 1
            summary_str = json.dumps(summary_json, ensure_ascii=False)
            conn.execute(
                "INSERT INTO competitor_snapshot "
                "(id, competitor_id, snapshot_version, summary_json, quality_score, traction_score, "
                "relevance_score, underrated_score, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id, competitor_id, next_version, summary_str,
                    quality_score, traction_score, relevance_score, underrated_score,
                    confidence, now,
                ),
            )
        return SnapshotRecord(
            id=record_id,
            competitor_id=competitor_id,
            snapshot_version=next_version,
            summary_json=summary_json,
            quality_score=quality_score,
            traction_score=traction_score,
            relevance_score=relevance_score,
            underrated_score=underrated_score,
            confidence=confidence,
            created_at=now,
        )

    def get_latest_snapshot(self, competitor_id: str) -> SnapshotRecord | None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT id, competitor_id, snapshot_version, summary_json, quality_score, "
                "traction_score, relevance_score, underrated_score, confidence, created_at "
                "FROM competitor_snapshot WHERE competitor_id = ? ORDER BY snapshot_version DESC LIMIT 1",
                (competitor_id,),
            ).fetchone()
        if row is None:
            return None
        return SnapshotRecord(
            id=str(row["id"]),
            competitor_id=str(row["competitor_id"]),
            snapshot_version=int(row["snapshot_version"]),
            summary_json=json.loads(str(row["summary_json"])),
            quality_score=float(row["quality_score"]) if row["quality_score"] is not None else None,
            traction_score=float(row["traction_score"]) if row["traction_score"] is not None else None,
            relevance_score=float(row["relevance_score"]) if row["relevance_score"] is not None else None,
            underrated_score=float(row["underrated_score"]) if row["underrated_score"] is not None else None,
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            created_at=str(row["created_at"]),
        )

    def create_evidence_source(
        self,
        source_type: str,
        url: str,
        title: str | None = None,
        snippet: str | None = None,
        published_at: str | None = None,
        confidence: float | None = None,
        payload_json: dict | None = None,
    ) -> EvidenceSourceRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        payload_str = json.dumps(payload_json, ensure_ascii=False) if payload_json is not None else None
        with db_session() as conn:
            conn.execute(
                "INSERT INTO evidence_source "
                "(id, source_type, url, title, snippet, published_at, fetched_at, confidence, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, source_type, url, title, snippet, published_at, now, confidence, payload_str),
            )
        return EvidenceSourceRecord(
            id=record_id,
            source_type=source_type,
            url=url,
            title=title,
            snippet=snippet,
            published_at=published_at,
            fetched_at=now,
            confidence=confidence,
            payload_json=payload_json,
        )
