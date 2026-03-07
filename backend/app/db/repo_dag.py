from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.time import utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class IdeaNode:
    id: str
    idea_id: str
    parent_id: str | None
    content: str
    expansion_pattern: str | None
    edge_label: str | None
    depth: int
    status: str
    created_at: str


@dataclass(frozen=True)
class IdeaPath:
    id: str
    idea_id: str
    node_chain: list[str]
    path_md: str
    path_json: str
    created_at: str


def create_node(
    idea_id: str,
    content: str,
    parent_id: str | None = None,
    expansion_pattern: str | None = None,
    edge_label: str | None = None,
) -> IdeaNode:
    depth = 0
    if parent_id is not None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT depth FROM idea_nodes WHERE id = ?", (parent_id,)
            ).fetchone()
            if row is not None:
                depth = int(row["depth"]) + 1

    node_id = str(uuid4())
    now = utc_now_iso()

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO idea_nodes
                (id, idea_id, parent_id, content, expansion_pattern, edge_label, depth, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (node_id, idea_id, parent_id, content, expansion_pattern, edge_label, depth, "active", now),
        )

    return IdeaNode(
        id=node_id,
        idea_id=idea_id,
        parent_id=parent_id,
        content=content,
        expansion_pattern=expansion_pattern,
        edge_label=edge_label,
        depth=depth,
        status="active",
        created_at=now,
    )


def list_nodes(idea_id: str) -> list[IdeaNode]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, idea_id, parent_id, content, expansion_pattern,
                   edge_label, depth, status, created_at
            FROM idea_nodes
            WHERE idea_id = ?
            ORDER BY depth, created_at
            """,
            (idea_id,),
        ).fetchall()

    return [_row_to_node(r) for r in rows]


def get_node(node_id: str) -> IdeaNode | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, idea_id, parent_id, content, expansion_pattern,
                   edge_label, depth, status, created_at
            FROM idea_nodes
            WHERE id = ?
            """,
            (node_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_node(row)


def delete_node_and_descendants(node_id: str, idea_id: str) -> int:
    """Delete a node and all its descendants. Returns count of deleted nodes."""
    with db_session() as conn:
        # Collect node and all descendants via recursive walk
        to_delete = [node_id]
        queue = [node_id]
        while queue:
            parent = queue.pop(0)
            children = conn.execute(
                "SELECT id FROM idea_nodes WHERE parent_id = ? AND idea_id = ?",
                (parent, idea_id),
            ).fetchall()
            for child in children:
                child_id = str(child["id"])
                to_delete.append(child_id)
                queue.append(child_id)

        placeholders = ",".join("?" * len(to_delete))
        conn.execute(
            f"DELETE FROM idea_nodes WHERE id IN ({placeholders}) AND idea_id = ?",
            (*to_delete, idea_id),
        )
        return len(to_delete)


def create_path(
    idea_id: str,
    node_chain: list[str],
    path_md: str,
    path_json: str,
) -> IdeaPath:
    path_id = str(uuid4())
    now = utc_now_iso()
    chain_json = json.dumps(node_chain)

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO idea_paths
                (id, idea_id, node_chain, path_md, path_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (path_id, idea_id, chain_json, path_md, path_json, now),
        )

    return IdeaPath(
        id=path_id,
        idea_id=idea_id,
        node_chain=node_chain,
        path_md=path_md,
        path_json=path_json,
        created_at=now,
    )


def update_path_summary(path_id: str, path_md: str, path_json: str) -> None:
    """Patch path_md and path_json in-place (used by background summary generation)."""
    with db_session() as conn:
        conn.execute(
            "UPDATE idea_paths SET path_md = ?, path_json = ? WHERE id = ?",
            (path_md, path_json, path_id),
        )


def get_latest_path(idea_id: str) -> IdeaPath | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, idea_id, node_chain, path_md, path_json, created_at
            FROM idea_paths
            WHERE idea_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (idea_id,),
        ).fetchone()

    if row is None:
        return None
    return IdeaPath(
        id=str(row["id"]),
        idea_id=str(row["idea_id"]),
        node_chain=json.loads(str(row["node_chain"])),
        path_md=str(row["path_md"]),
        path_json=str(row["path_json"]),
        created_at=str(row["created_at"]),
    )


def _row_to_node(row: object) -> IdeaNode:
    return IdeaNode(
        id=str(row["id"]),  # type: ignore[index]
        idea_id=str(row["idea_id"]),  # type: ignore[index]
        parent_id=str(row["parent_id"]) if row["parent_id"] is not None else None,  # type: ignore[index]
        content=str(row["content"]),  # type: ignore[index]
        expansion_pattern=str(row["expansion_pattern"]) if row["expansion_pattern"] is not None else None,  # type: ignore[index]
        edge_label=str(row["edge_label"]) if row["edge_label"] is not None else None,  # type: ignore[index]
        depth=int(row["depth"]),  # type: ignore[index]
        status=str(row["status"]),  # type: ignore[index]
        created_at=str(row["created_at"]),  # type: ignore[index]
    )
