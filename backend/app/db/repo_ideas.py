from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast
from uuid import uuid4

from app.core.contexts import (
    create_default_context,
    infer_stage_from_context,
    parse_context_strict,
)
from app.core.time import utc_now_iso
from app.db.bootstrap import DEFAULT_WORKSPACE_ID
from app.db.engine import db_session
from app.schemas.ideas import DecisionContext, IdeaStage, IdeaStatus

UpdateKind = Literal["ok", "not_found", "conflict", "archived"]


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class IdeaRecord:
    id: str
    workspace_id: str
    title: str
    idea_seed: str | None
    stage: IdeaStage
    status: IdeaStatus
    context: dict[str, object]
    version: int
    created_at: str
    updated_at: str
    archived_at: str | None


@dataclass(frozen=True)
class UpdateIdeaResult:
    kind: UpdateKind
    idea: IdeaRecord | None = None


class IdeaRepository:
    def get_default_workspace(self) -> WorkspaceRecord | None:
        with db_session() as connection:
            row = connection.execute(
                "SELECT id, name, created_at, updated_at FROM workspace WHERE id = ?",
                (DEFAULT_WORKSPACE_ID,),
            ).fetchone()
            if row is None:
                return None
            return WorkspaceRecord(
                id=str(row["id"]),
                name=str(row["name"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )

    def create_idea(self, *, title: str, idea_seed: str | None = None) -> IdeaRecord:
        idea_id = str(uuid4())
        now = utc_now_iso()
        context_model = create_default_context(idea_seed=idea_seed)
        context_payload = context_model.model_dump(mode="python", exclude_none=True)
        stage = infer_stage_from_context(context_model)

        with db_session() as connection:
            connection.execute(
                """
                INSERT INTO idea (
                    id, workspace_id, title, idea_seed, stage, status,
                    context_json, version, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idea_id,
                    DEFAULT_WORKSPACE_ID,
                    title,
                    idea_seed,
                    stage,
                    "draft",
                    json.dumps(context_payload, ensure_ascii=False),
                    1,
                    now,
                    now,
                    None,
                ),
            )
            row = _select_idea_row(connection, idea_id)

        assert row is not None
        return _row_to_idea(row)

    def get_idea(self, idea_id: str) -> IdeaRecord | None:
        with db_session() as connection:
            row = _select_idea_row(connection, idea_id)
            if row is None:
                return None
            return _row_to_idea(row)

    def delete_idea(self, idea_id: str) -> None:
        """Hard-delete idea and all associated nodes/paths. Raises KeyError if not found."""
        with db_session() as connection:
            row = connection.execute("SELECT id FROM idea WHERE id = ?", (idea_id,)).fetchone()
            if row is None:
                raise KeyError(f"Idea {idea_id!r} not found")
            connection.execute("DELETE FROM idea_nodes WHERE idea_id = ?", (idea_id,))
            connection.execute("DELETE FROM idea_paths WHERE idea_id = ?", (idea_id,))
            connection.execute("DELETE FROM idea WHERE id = ?", (idea_id,))

    def list_ideas(
        self,
        *,
        statuses: list[IdeaStatus],
        limit: int,
        cursor: tuple[str, str] | None = None,
    ) -> tuple[list[IdeaRecord], tuple[str, str] | None]:
        if not statuses:
            return [], None

        placeholders = ",".join("?" for _ in statuses)
        params: list[object] = list(statuses)
        where_sql = f"status IN ({placeholders})"

        if cursor is not None:
            updated_at, idea_id = cursor
            where_sql += " AND (updated_at < ? OR (updated_at = ? AND id < ?))"
            params.extend([updated_at, updated_at, idea_id])

        params.append(limit + 1)

        query = (
            "SELECT * FROM idea "
            f"WHERE {where_sql} "
            "ORDER BY updated_at DESC, id DESC "
            "LIMIT ?"
        )

        with db_session() as connection:
            rows = connection.execute(query, params).fetchall()

        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        items = [_row_to_idea(row) for row in visible_rows]

        next_cursor: tuple[str, str] | None = None
        if has_more and visible_rows:
            last_row = visible_rows[-1]
            next_cursor = (str(last_row["updated_at"]), str(last_row["id"]))

        return items, next_cursor

    def update_idea(
        self,
        idea_id: str,
        *,
        version: int,
        title: str | None,
        status: IdeaStatus | None,
    ) -> UpdateIdeaResult:
        with db_session() as connection:
            existing = _select_idea_row(connection, idea_id)
            if existing is None:
                return UpdateIdeaResult(kind="not_found")

            next_title = title if title is not None else str(existing["title"])
            next_status: IdeaStatus = status if status is not None else _as_status(str(existing["status"]))
            next_archived_at: str | None

            if next_status == "archived":
                next_archived_at = str(existing["archived_at"]) if existing["archived_at"] else utc_now_iso()
            else:
                next_archived_at = None

            updated_at = utc_now_iso()

            result = connection.execute(
                """
                UPDATE idea
                SET title = ?, status = ?, archived_at = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (next_title, next_status, next_archived_at, updated_at, idea_id, version),
            )
            if result.rowcount == 0:
                return UpdateIdeaResult(kind="conflict")

            updated = _select_idea_row(connection, idea_id)
            assert updated is not None
            return UpdateIdeaResult(kind="ok", idea=_row_to_idea(updated))

    def update_context(
        self,
        idea_id: str,
        *,
        version: int,
        context: dict[str, object],
    ) -> UpdateIdeaResult:
        return self._update_context_internal(
            idea_id,
            version=version,
            mutate_context=lambda _: parse_context_strict(context),
            require_not_archived=False,
        )

    def apply_agent_update(
        self,
        idea_id: str,
        *,
        version: int,
        mutate_context: Callable[[DecisionContext], DecisionContext],
    ) -> UpdateIdeaResult:
        result = self._update_context_internal(
            idea_id,
            version=version,
            mutate_context=mutate_context,
            require_not_archived=True,
        )
        if result.kind == "conflict":
            # Version was advanced by a concurrent operation (e.g. /paths write)
            # while the LLM was running. Re-read the latest version and retry once.
            # Safe because all mutate_context functions are idempotent (they only
            # write new LLM output into context fields, never diff against old state).
            latest = self.get_idea(idea_id)
            if latest is not None:
                result = self._update_context_internal(
                    idea_id,
                    version=latest.version,
                    mutate_context=mutate_context,
                    require_not_archived=True,
                )
        return result

    def _update_context_internal(
        self,
        idea_id: str,
        *,
        version: int,
        mutate_context: Callable[[DecisionContext], DecisionContext],
        require_not_archived: bool,
    ) -> UpdateIdeaResult:
        with db_session() as connection:
            existing = _select_idea_row(connection, idea_id)
            if existing is None:
                return UpdateIdeaResult(kind="not_found")

            status = str(existing["status"])
            if require_not_archived and status == "archived":
                return UpdateIdeaResult(kind="archived")

            current_context = parse_context_strict(
                json.loads(str(existing["context_json"]))
            )
            next_context_model = mutate_context(current_context.model_copy(deep=True))
            next_context = next_context_model.model_dump(mode="python", exclude_none=True)
            next_stage = infer_stage_from_context(next_context_model)

            idea_seed_value = next_context.get("idea_seed")
            next_idea_seed = str(idea_seed_value) if isinstance(idea_seed_value, str) else None
            updated_at = utc_now_iso()

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
                    updated_at,
                    idea_id,
                    version,
                ),
            )
            if result.rowcount == 0:
                return UpdateIdeaResult(kind="conflict")

            updated = _select_idea_row(connection, idea_id)
            assert updated is not None
            return UpdateIdeaResult(kind="ok", idea=_row_to_idea(updated))


def _select_idea_row(connection: sqlite3.Connection, idea_id: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
        "SELECT * FROM idea WHERE id = ?",
        (idea_id,),
        ).fetchone(),
    )


def _row_to_idea(row: sqlite3.Row) -> IdeaRecord:
    raw_context = json.loads(str(row["context_json"]))
    validated_context = parse_context_strict(raw_context)

    return IdeaRecord(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        title=str(row["title"]),
        idea_seed=str(row["idea_seed"]) if row["idea_seed"] is not None else None,
        stage=_as_stage(str(row["stage"])),
        status=_as_status(str(row["status"])),
        context=validated_context.model_dump(mode="python", exclude_none=True),
        version=int(row["version"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        archived_at=str(row["archived_at"]) if row["archived_at"] is not None else None,
    )


def _as_stage(value: str) -> IdeaStage:
    allowed: tuple[IdeaStage, ...] = ("idea_canvas", "feasibility", "scope_freeze", "prd")
    if value not in allowed:
        raise ValueError(f"Unsupported idea stage: {value}")
    return cast(IdeaStage, value)


def _as_status(value: str) -> IdeaStatus:
    allowed: tuple[IdeaStatus, ...] = ("draft", "active", "frozen", "archived")
    if value not in allowed:
        raise ValueError(f"Unsupported idea status: {value}")
    return cast(IdeaStatus, value)
