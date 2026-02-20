from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, Literal, cast
from uuid import uuid4

from app.core.contexts import infer_stage_from_context
from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.schemas.ideas import DecisionContext
from app.schemas.scope import InScopeItem, OutScopeItem, ScopeOutput

ScopeLane = Literal["in", "out"]
ScopeBaselineStatus = Literal["draft", "frozen", "superseded"]
ScopeUpdateKind = Literal[
    "ok",
    "not_found",
    "conflict",
    "archived",
    "draft_not_found",
    "baseline_not_found",
]


@dataclass(frozen=True)
class ScopeDraftItemInput:
    lane: ScopeLane
    content: str


@dataclass(frozen=True)
class ScopeBaselineItemRecord:
    id: str
    baseline_id: str
    lane: ScopeLane
    content: str
    display_order: int
    created_at: str


@dataclass(frozen=True)
class ScopeBaselineRecord:
    id: str
    idea_id: str
    version: int
    status: ScopeBaselineStatus
    source_baseline_id: str | None
    created_at: str
    frozen_at: str | None
    items: list[ScopeBaselineItemRecord]


@dataclass(frozen=True)
class ScopeMutationResult:
    kind: ScopeUpdateKind
    idea_version: int | None = None
    baseline: ScopeBaselineRecord | None = None


class ScopeRepository:
    def get_draft(self, idea_id: str) -> ScopeBaselineRecord | None:
        with db_session() as connection:
            row = _select_latest_baseline_row(connection, idea_id=idea_id, status="draft")
            if row is None:
                return None
            return _row_to_baseline(connection, row)

    def get_baseline(self, idea_id: str, baseline_id: str) -> ScopeBaselineRecord | None:
        with db_session() as connection:
            row = connection.execute(
                """
                SELECT id, idea_id, version, status, source_baseline_id, created_at, frozen_at
                FROM scope_baselines
                WHERE id = ? AND idea_id = ?
                """,
                (baseline_id, idea_id),
            ).fetchone()
            if row is None:
                return None
            return _row_to_baseline(connection, row)

    def bootstrap_draft(
        self,
        idea_id: str,
        *,
        version: int,
        items: Sequence[ScopeDraftItemInput] = (),
    ) -> ScopeMutationResult:
        with db_session() as connection:
            guard = _check_idea_guard(connection, idea_id=idea_id, version=version)
            if guard is not None:
                return ScopeMutationResult(kind=guard)

            existing_draft = _select_latest_baseline_row(connection, idea_id=idea_id, status="draft")
            if existing_draft is not None:
                baseline = _row_to_baseline(connection, existing_draft)
                return ScopeMutationResult(
                    kind="ok",
                    idea_version=version,
                    baseline=baseline,
                )

            baseline_version = _next_baseline_version(connection, idea_id)
            now = utc_now_iso()
            baseline_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO scope_baselines (
                    id, idea_id, version, status, source_baseline_id, created_at, frozen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (baseline_id, idea_id, baseline_version, "draft", None, now, None),
            )
            _replace_items(connection, baseline_id=baseline_id, items=items)

            baseline = _must_get_baseline(connection, idea_id=idea_id, baseline_id=baseline_id)
            next_idea_version = _update_idea_context(
                connection,
                idea_id=idea_id,
                expected_version=version,
                mutate_context=lambda context: context.model_copy(
                    update={
                        "current_scope_baseline_id": baseline.id,
                        "current_scope_baseline_version": baseline.version,
                        "scope_frozen": False,
                    }
                ),
            )
            if next_idea_version is None:
                return ScopeMutationResult(kind="conflict")

            return ScopeMutationResult(kind="ok", idea_version=next_idea_version, baseline=baseline)

    def patch_draft(
        self,
        idea_id: str,
        *,
        version: int,
        items: Sequence[ScopeDraftItemInput],
    ) -> ScopeMutationResult:
        with db_session() as connection:
            guard = _check_idea_guard(connection, idea_id=idea_id, version=version)
            if guard is not None:
                return ScopeMutationResult(kind=guard)

            draft_row = _select_latest_baseline_row(connection, idea_id=idea_id, status="draft")
            if draft_row is None:
                return ScopeMutationResult(kind="draft_not_found")

            baseline_id = str(draft_row["id"])
            _replace_items(connection, baseline_id=baseline_id, items=items)
            baseline = _must_get_baseline(connection, idea_id=idea_id, baseline_id=baseline_id)

            next_idea_version = _update_idea_context(
                connection,
                idea_id=idea_id,
                expected_version=version,
                mutate_context=lambda context: context.model_copy(
                    update={
                        "current_scope_baseline_id": baseline.id,
                        "current_scope_baseline_version": baseline.version,
                        "scope_frozen": False,
                    }
                ),
            )
            if next_idea_version is None:
                return ScopeMutationResult(kind="conflict")

            return ScopeMutationResult(kind="ok", idea_version=next_idea_version, baseline=baseline)

    def freeze_draft(self, idea_id: str, *, version: int) -> ScopeMutationResult:
        with db_session() as connection:
            guard = _check_idea_guard(connection, idea_id=idea_id, version=version)
            if guard is not None:
                return ScopeMutationResult(kind=guard)

            draft_row = _select_latest_baseline_row(connection, idea_id=idea_id, status="draft")
            if draft_row is None:
                return ScopeMutationResult(kind="draft_not_found")

            baseline_id = str(draft_row["id"])
            now = utc_now_iso()
            connection.execute(
                """
                UPDATE scope_baselines
                SET status = 'superseded'
                WHERE idea_id = ? AND status = 'frozen' AND id != ?
                """,
                (idea_id, baseline_id),
            )
            connection.execute(
                """
                UPDATE scope_baselines
                SET status = 'frozen', frozen_at = ?
                WHERE id = ?
                """,
                (now, baseline_id),
            )
            baseline = _must_get_baseline(connection, idea_id=idea_id, baseline_id=baseline_id)

            next_idea_version = _update_idea_context(
                connection,
                idea_id=idea_id,
                expected_version=version,
                mutate_context=lambda context: context.model_copy(
                    update={
                        "current_scope_baseline_id": baseline.id,
                        "current_scope_baseline_version": baseline.version,
                        "scope_frozen": True,
                        "scope": _build_legacy_scope_output(baseline.items),
                    }
                ),
            )
            if next_idea_version is None:
                return ScopeMutationResult(kind="conflict")

            return ScopeMutationResult(kind="ok", idea_version=next_idea_version, baseline=baseline)

    def new_version(self, idea_id: str, *, version: int) -> ScopeMutationResult:
        with db_session() as connection:
            guard = _check_idea_guard(connection, idea_id=idea_id, version=version)
            if guard is not None:
                return ScopeMutationResult(kind=guard)

            source_row = _select_latest_baseline_row(connection, idea_id=idea_id, status="frozen")
            if source_row is None:
                return ScopeMutationResult(kind="baseline_not_found")

            existing_draft = _select_latest_baseline_row(connection, idea_id=idea_id, status="draft")
            if existing_draft is not None:
                connection.execute(
                    "UPDATE scope_baselines SET status = 'superseded' WHERE id = ?",
                    (str(existing_draft["id"]),),
                )

            source_baseline = _row_to_baseline(connection, source_row)
            next_version = _next_baseline_version(connection, idea_id)
            now = utc_now_iso()
            baseline_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO scope_baselines (
                    id, idea_id, version, status, source_baseline_id, created_at, frozen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    baseline_id,
                    idea_id,
                    next_version,
                    "draft",
                    source_baseline.id,
                    now,
                    None,
                ),
            )
            _replace_items(
                connection,
                baseline_id=baseline_id,
                items=[
                    ScopeDraftItemInput(lane=item.lane, content=item.content)
                    for item in source_baseline.items
                ],
            )

            baseline = _must_get_baseline(connection, idea_id=idea_id, baseline_id=baseline_id)
            next_idea_version = _update_idea_context(
                connection,
                idea_id=idea_id,
                expected_version=version,
                mutate_context=lambda context: context.model_copy(
                    update={
                        "current_scope_baseline_id": baseline.id,
                        "current_scope_baseline_version": baseline.version,
                        "scope_frozen": False,
                    }
                ),
            )
            if next_idea_version is None:
                return ScopeMutationResult(kind="conflict")

            return ScopeMutationResult(kind="ok", idea_version=next_idea_version, baseline=baseline)


def _select_idea_row(connection: sqlite3.Connection, idea_id: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute("SELECT * FROM idea WHERE id = ?", (idea_id,)).fetchone(),
    )


def _check_idea_guard(connection: sqlite3.Connection, *, idea_id: str, version: int) -> ScopeUpdateKind | None:
    row = _select_idea_row(connection, idea_id)
    if row is None:
        return "not_found"
    if str(row["status"]) == "archived":
        return "archived"
    if int(row["version"]) != version:
        return "conflict"
    return None


def _select_latest_baseline_row(
    connection: sqlite3.Connection,
    *,
    idea_id: str,
    status: ScopeBaselineStatus,
) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            """
            SELECT id, idea_id, version, status, source_baseline_id, created_at, frozen_at
            FROM scope_baselines
            WHERE idea_id = ? AND status = ?
            ORDER BY version DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (idea_id, status),
        ).fetchone(),
    )


def _next_baseline_version(connection: sqlite3.Connection, idea_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS max_version FROM scope_baselines WHERE idea_id = ?",
        (idea_id,),
    ).fetchone()
    max_version = int(row["max_version"]) if row is not None else 0
    return max_version + 1


def _must_get_baseline(
    connection: sqlite3.Connection,
    *,
    idea_id: str,
    baseline_id: str,
) -> ScopeBaselineRecord:
    row = connection.execute(
        """
        SELECT id, idea_id, version, status, source_baseline_id, created_at, frozen_at
        FROM scope_baselines
        WHERE id = ? AND idea_id = ?
        """,
        (baseline_id, idea_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"Scope baseline {baseline_id!r} not found for idea {idea_id!r}")
    return _row_to_baseline(connection, row)


def _row_to_baseline(connection: sqlite3.Connection, row: sqlite3.Row) -> ScopeBaselineRecord:
    status = str(row["status"])
    if status not in ("draft", "frozen", "superseded"):
        raise ValueError(f"Unsupported scope baseline status: {status}")
    items = _list_items(connection, baseline_id=str(row["id"]))
    return ScopeBaselineRecord(
        id=str(row["id"]),
        idea_id=str(row["idea_id"]),
        version=int(row["version"]),
        status=cast(ScopeBaselineStatus, status),
        source_baseline_id=str(row["source_baseline_id"])
        if row["source_baseline_id"] is not None
        else None,
        created_at=str(row["created_at"]),
        frozen_at=str(row["frozen_at"]) if row["frozen_at"] is not None else None,
        items=items,
    )


def _list_items(connection: sqlite3.Connection, *, baseline_id: str) -> list[ScopeBaselineItemRecord]:
    rows = connection.execute(
        """
        SELECT id, baseline_id, lane, content, display_order, created_at
        FROM scope_baseline_items
        WHERE baseline_id = ?
        ORDER BY rowid ASC
        """,
        (baseline_id,),
    ).fetchall()
    items: list[ScopeBaselineItemRecord] = []
    for row in rows:
        lane = str(row["lane"])
        if lane not in ("in", "out"):
            raise ValueError(f"Unsupported scope lane: {lane}")
        items.append(
            ScopeBaselineItemRecord(
                id=str(row["id"]),
                baseline_id=str(row["baseline_id"]),
                lane=cast(ScopeLane, lane),
                content=str(row["content"]),
                display_order=int(row["display_order"]),
                created_at=str(row["created_at"]),
            )
        )
    return items


def _replace_items(
    connection: sqlite3.Connection,
    *,
    baseline_id: str,
    items: Sequence[ScopeDraftItemInput],
) -> None:
    connection.execute("DELETE FROM scope_baseline_items WHERE baseline_id = ?", (baseline_id,))
    lane_order = {"in": 0, "out": 0}
    for item in items:
        display_order = lane_order[item.lane]
        lane_order[item.lane] += 1
        connection.execute(
            """
            INSERT INTO scope_baseline_items (
                id, baseline_id, lane, content, display_order, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), baseline_id, item.lane, item.content, display_order, utc_now_iso()),
        )


def _update_idea_context(
    connection: sqlite3.Connection,
    *,
    idea_id: str,
    expected_version: int,
    mutate_context: Callable[[DecisionContext], DecisionContext],
) -> int | None:
    row = _select_idea_row(connection, idea_id)
    if row is None:
        return None
    context = DecisionContext.model_validate(json.loads(str(row["context_json"])))
    next_context_model = mutate_context(context)
    next_context = next_context_model.model_dump(mode="python", exclude_none=True)
    next_stage = infer_stage_from_context(next_context_model)
    idea_seed_value = next_context.get("idea_seed")
    next_idea_seed = str(idea_seed_value) if isinstance(idea_seed_value, str) else None
    result = connection.execute(
        """
        UPDATE idea
        SET context_json = ?, stage = ?, idea_seed = ?, updated_at = ?, version = version + 1
        WHERE id = ? AND version = ?
        """,
        (
            json.dumps(next_context, ensure_ascii=False),
            next_stage,
            next_idea_seed,
            utc_now_iso(),
            idea_id,
            expected_version,
        ),
    )
    if result.rowcount == 0:
        return None
    return expected_version + 1


def _build_legacy_scope_output(items: Sequence[ScopeBaselineItemRecord]) -> ScopeOutput:
    in_scope: list[InScopeItem] = []
    out_scope: list[OutScopeItem] = []
    for item in items:
        if item.lane == "in":
            in_scope.append(
                InScopeItem(id=item.id, title=item.content, desc="", priority="P1")
            )
        else:
            out_scope.append(
                OutScopeItem(id=item.id, title=item.content, desc="", reason="")
            )
    return ScopeOutput(in_scope=in_scope, out_scope=out_scope)
