from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class MarketInsightRecord:
    id: str
    idea_id: str
    summary: str
    decision_impact: str
    recommended_actions: list[str]
    signal_count: int
    generated_at: str


class MarketInsightRepository:

    def create(
        self,
        idea_id: str,
        summary: str,
        decision_impact: str,
        recommended_actions: list[str],
        signal_count: int,
    ) -> MarketInsightRecord:
        record_id = str(uuid4())
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "INSERT INTO market_insight "
                "(id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id, idea_id, summary, decision_impact,
                    json.dumps(recommended_actions, ensure_ascii=False),
                    signal_count, now,
                ),
            )
        return MarketInsightRecord(
            id=record_id, idea_id=idea_id, summary=summary,
            decision_impact=decision_impact, recommended_actions=recommended_actions,
            signal_count=signal_count, generated_at=now,
        )

    def list_for_idea(self, idea_id: str, limit: int = 10) -> list[MarketInsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at "
                "FROM market_insight WHERE idea_id = ? ORDER BY generated_at DESC LIMIT ?",
                (idea_id, limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[MarketInsightRecord]:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id, idea_id, summary, decision_impact, recommended_actions, signal_count, generated_at "
                "FROM market_insight ORDER BY generated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def _row_to_record(self, r: object) -> MarketInsightRecord:
        return MarketInsightRecord(
            id=str(r["id"]),
            idea_id=str(r["idea_id"]),
            summary=str(r["summary"]),
            decision_impact=str(r["decision_impact"]),
            recommended_actions=json.loads(str(r["recommended_actions"])),
            signal_count=int(r["signal_count"]),
            generated_at=str(r["generated_at"]),
        )
