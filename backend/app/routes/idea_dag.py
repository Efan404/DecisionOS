from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from app.core import llm
from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.db import repo_dag
from app.db.repo_decision_events import DecisionEventRepository
from app.db.repo_ideas import IdeaRepository, UpdateIdeaResult
from app.schemas.dag import (
    ConfirmPathRequest,
    CreateRootNodeRequest,
    EXPANSION_PATTERNS,
    IdeaNodeOut,
    IdeaPathOut,
    UserExpandRequest,
)

router = APIRouter(prefix="/ideas/{idea_id}", tags=["idea-dag"])
_repo = IdeaRepository()
_event_repo = DecisionEventRepository()
logger = logging.getLogger(__name__)


def _raise_if_no_provider(exc: Exception) -> None:
    """Re-raise RuntimeError from missing AI provider as HTTP 503."""
    msg = str(exc)
    if isinstance(exc, RuntimeError) and "No AI provider" in msg:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_PROVIDER_NOT_CONFIGURED",
                "message": msg,
            },
        ) from exc


def _require_idea(idea_id: str) -> None:
    idea = _repo.get_idea(idea_id)
    if idea is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": f"Idea {idea_id} not found"},
        )
    if idea.status == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )


def _chain_summary(idea_id: str, node_chain: list[str]) -> str:
    nodes = {n.id: n for n in repo_dag.list_nodes(idea_id)}
    parts = [nodes[nid].content for nid in node_chain if nid in nodes]
    return " → ".join(parts)


def _unwrap_update(result: UpdateIdeaResult) -> None:
    if result.kind == "ok":
        return

    if result.kind == "not_found":
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": "Idea not found"},
        )

    if result.kind == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    raise HTTPException(
        status_code=409,
        detail={"code": "IDEA_VERSION_CONFLICT", "message": "Idea version conflict"},
    )


@router.get("/nodes", response_model=list[IdeaNodeOut])
async def list_nodes(idea_id: str) -> list[IdeaNodeOut]:
    _require_idea(idea_id)
    nodes = repo_dag.list_nodes(idea_id)
    return [IdeaNodeOut(**n.__dict__) for n in nodes]


@router.post("/nodes", response_model=IdeaNodeOut, status_code=201)
async def create_root_node(idea_id: str, body: CreateRootNodeRequest) -> IdeaNodeOut:
    _require_idea(idea_id)
    existing = repo_dag.list_nodes(idea_id)
    if existing:
        # Root node already exists — return it instead of creating a duplicate
        root = next((n for n in existing if n.parent_id is None), existing[0])
        return IdeaNodeOut(**root.__dict__)
    node = repo_dag.create_node(idea_id=idea_id, content=body.content)
    return IdeaNodeOut(**node.__dict__)


@router.get("/nodes/{node_id}", response_model=IdeaNodeOut)
async def get_node(idea_id: str, node_id: str) -> IdeaNodeOut:
    _require_idea(idea_id)
    node = repo_dag.get_node(node_id)
    if node is None or node.idea_id != idea_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NODE_NOT_FOUND", "message": "Node not found"},
        )
    return IdeaNodeOut(**node.__dict__)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(idea_id: str, node_id: str) -> None:
    _require_idea(idea_id)
    node = repo_dag.get_node(node_id)
    if node is None or node.idea_id != idea_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NODE_NOT_FOUND", "message": "Node not found"},
        )
    if node.parent_id is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "CANNOT_DELETE_ROOT", "message": "Cannot delete the root node"},
        )
    repo_dag.delete_node_and_descendants(node_id, idea_id)


@router.post(
    "/nodes/{node_id}/expand/user",
    response_model=list[IdeaNodeOut],
    status_code=201,
)
async def expand_user(
    idea_id: str, node_id: str, body: UserExpandRequest
) -> list[IdeaNodeOut]:
    _require_idea(idea_id)
    parent = repo_dag.get_node(node_id)
    if parent is None or parent.idea_id != idea_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NODE_NOT_FOUND", "message": "Node not found"},
        )
    chain = [node_id]
    summary = _chain_summary(idea_id, chain)
    try:
        children_data = llm.generate_expand_node_user(
            parent.content, body.description, summary
        )
    except Exception as exc:
        _raise_if_no_provider(exc)
        raise HTTPException(
            status_code=502,
            detail={"code": "EXPAND_FAILED", "message": "Failed to expand node"},
        ) from exc
    results: list[IdeaNodeOut] = []
    for child in children_data:
        node = repo_dag.create_node(
            idea_id=idea_id,
            content=child["content"],
            parent_id=node_id,
            edge_label=child.get("edge_label", "用户方向"),
        )
        results.append(IdeaNodeOut(**node.__dict__))
    return results


@router.post("/nodes/{node_id}/expand/stream")
async def expand_stream(idea_id: str, node_id: str, pattern_id: str) -> StreamingResponse:
    """SSE stream: expand node with AI pattern. Query param: pattern_id"""
    _require_idea(idea_id)
    parent = repo_dag.get_node(node_id)
    if parent is None or parent.idea_id != idea_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NODE_NOT_FOUND", "message": "Node not found"},
        )
    pattern = next((p for p in EXPANSION_PATTERNS if p["id"] == pattern_id), None)
    if pattern is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNKNOWN_PATTERN", "message": f"Unknown pattern: {pattern_id}"},
        )
    chain_summary = _chain_summary(idea_id, [node_id])

    def _evt(event: str, payload: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream() -> None:
        yield _evt("progress", {"step": "generating", "pct": 10})  # type: ignore[misc]
        try:
            children_data = llm.generate_expand_nodes(
                parent.content, pattern["label"], pattern["description"], chain_summary
            )
            yield _evt("progress", {"step": "persisting", "pct": 70})  # type: ignore[misc]
            created = []
            for child in children_data:
                node = repo_dag.create_node(
                    idea_id=idea_id,
                    content=child["content"],
                    parent_id=node_id,
                    expansion_pattern=pattern_id,
                    edge_label=child.get("edge_label", pattern["label"]),
                )
                created.append({
                    "id": node.id,
                    "content": node.content,
                    "parent_id": node.parent_id,
                    "depth": node.depth,
                    "edge_label": node.edge_label,
                    "expansion_pattern": node.expansion_pattern,
                    "status": node.status,
                    "created_at": node.created_at,
                    "idea_id": node.idea_id,
                })
            yield _evt("done", {"idea_id": idea_id, "nodes": created})  # type: ignore[misc]
        except Exception as exc:
            logger.exception(
                "DAG node expand stream failed idea_id=%s node_id=%s pattern_id=%s",
                idea_id,
                node_id,
                pattern_id,
                exc_info=exc,
            )
            msg = str(exc) if "No AI provider" in str(exc) else "Failed to expand node"
            yield _evt(
                "error", {"code": "AI_PROVIDER_NOT_CONFIGURED" if "No AI provider" in str(exc) else "EXPAND_FAILED", "message": msg}
            )  # type: ignore[misc]

    return StreamingResponse(event_stream(), media_type="text/event-stream")  # type: ignore[arg-type]


@router.post("/paths", response_model=IdeaPathOut, status_code=201)
async def confirm_path(idea_id: str, body: ConfirmPathRequest, background_tasks: BackgroundTasks) -> IdeaPathOut:
    idea = _repo.get_idea(idea_id)
    if idea is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": f"Idea {idea_id} not found"},
        )
    if idea.status == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    nodes = {n.id: n for n in repo_dag.list_nodes(idea_id)}
    if not body.node_chain:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_NODE_CHAIN", "message": "node_chain cannot be empty"},
        )
    missing = [node_id for node_id in body.node_chain if node_id not in nodes]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_NODE_CHAIN", "message": "node_chain contains unknown nodes"},
        )

    confirmed_node_id = body.node_chain[-1]
    confirmed_node_content = nodes[confirmed_node_id].content

    lines = ["# Idea Path\n"]
    for i, nid in enumerate(body.node_chain):
        node = nodes.get(nid)
        if node:
            prefix = "Root" if i == 0 else (node.edge_label or f"Step {i}")
            lines.append(f"## {prefix}\n{node.content}\n")

    chain_text = " → ".join(
        nodes[nid].content for nid in body.node_chain if nid in nodes
    )

    # Persist path immediately with empty summary so the user is not blocked.
    path_json_data: dict[str, object] = {
        "idea_id": idea_id,
        "confirmed_at": utc_now_iso(),
        "node_chain": [
            {
                "id": nid,
                "content": nodes[nid].content if nid in nodes else "",
                "expansion_pattern": nodes[nid].expansion_pattern if nid in nodes else None,
                "edge_label": nodes[nid].edge_label if nid in nodes else None,
                "depth": nodes[nid].depth if nid in nodes else 0,
            }
            for nid in body.node_chain
        ],
        "summary": None,
    }
    path_md = "\n".join(lines)

    with db_session() as connection:
        path = repo_dag.create_path(
            idea_id=idea_id,
            node_chain=body.node_chain,
            path_md=path_md,
            path_json=json.dumps(path_json_data, ensure_ascii=False),
            connection=connection,
        )

        # Stamp DAG confirmation context so stage guards unlock Feasibility.
        update = _repo.apply_agent_update(
            idea_id,
            version=idea.version,
            mutate_context=lambda ctx: ctx.model_copy(
                update={
                    "confirmed_dag_path_id": path.id,
                    "confirmed_dag_node_id": confirmed_node_id,
                    "confirmed_dag_node_content": confirmed_node_content,
                    "confirmed_dag_path_summary": None,
                }
            ),
            connection=connection,
        )
        _unwrap_update(update)

    # Record decision event after successful path save
    node_contents = [
        nodes[nid].content for nid in body.node_chain if nid in nodes
    ]
    try:
        _event_repo.record(
            event_type="dag_path_confirmed",
            idea_id=idea_id,
            payload={
                "path_id": path.id,
                "node_count": len(body.node_chain),
                "leaf_content": node_contents[-1] if node_contents else "",
            },
        )
    except Exception:
        logger.warning("dag_path_confirmed event recording failed idea_id=%s", idea_id)

    # Generate path summary in the background — fills in path_json.summary and
    # context.confirmed_dag_path_summary once the LLM responds, without blocking
    # the user from navigating to the Feasibility step.
    background_tasks.add_task(
        _fill_path_summary_background, idea_id=idea_id, path_id=path.id, chain_text=chain_text
    )

    return IdeaPathOut(**path.__dict__)


def _fill_path_summary_background(*, idea_id: str, path_id: str, chain_text: str) -> None:
    """Background task: generate LLM path summary and patch the path + context."""
    logger.info("path_summary.start idea_id=%s path_id=%s", idea_id, path_id)
    try:
        summary = llm.generate_path_summary(chain_text)
    except Exception as exc:
        logger.warning("path_summary.failed idea_id=%s path_id=%s: %s", idea_id, path_id, exc)
        return

    # Patch the stored path record with the real summary.
    existing = repo_dag.get_latest_path(idea_id)
    if existing is None or existing.id != path_id:
        logger.warning("path_summary.skip idea_id=%s path_id=%s (path no longer latest)", idea_id, path_id)
        return

    try:
        path_json_data = json.loads(existing.path_json)
    except Exception:
        path_json_data = {}
    path_json_data["summary"] = summary

    updated_md = existing.path_md.rstrip("\n") + f"\n\n## 演进摘要\n{summary}\n"
    repo_dag.update_path_summary(
        path_id=path_id,
        path_md=updated_md,
        path_json=json.dumps(path_json_data, ensure_ascii=False),
    )

    # Patch context so downstream steps (Feasibility, PRD) have the summary.
    idea = _repo.get_idea(idea_id)
    if idea is None:
        return
    _repo.apply_agent_update(
        idea_id,
        version=idea.version,
        mutate_context=lambda ctx: ctx.model_copy(
            update={"confirmed_dag_path_summary": summary}
        ),
        allow_conflict_retry=True,
    )
    logger.info("path_summary.done idea_id=%s path_id=%s", idea_id, path_id)

@router.get("/paths/latest", response_model=IdeaPathOut)
async def get_latest_path(idea_id: str) -> IdeaPathOut:
    _require_idea(idea_id)
    path = repo_dag.get_latest_path(idea_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PATH_NOT_FOUND", "message": "No confirmed path yet"},
        )
    return IdeaPathOut(**path.__dict__)
