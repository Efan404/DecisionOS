from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core import llm
from app.core.time import utc_now_iso
from app.db import repo_dag
from app.db.repo_ideas import IdeaRepository
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


@router.get("/nodes", response_model=list[IdeaNodeOut])
async def list_nodes(idea_id: str) -> list[IdeaNodeOut]:
    _require_idea(idea_id)
    nodes = repo_dag.list_nodes(idea_id)
    return [IdeaNodeOut(**n.__dict__) for n in nodes]


@router.post("/nodes", response_model=IdeaNodeOut, status_code=201)
async def create_root_node(idea_id: str, body: CreateRootNodeRequest) -> IdeaNodeOut:
    _require_idea(idea_id)
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
    children_data = llm.generate_expand_node_user(
        parent.content, body.description, summary
    )
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
            yield _evt("error", {"code": "EXPAND_FAILED", "message": str(exc)})  # type: ignore[misc]

    return StreamingResponse(event_stream(), media_type="text/event-stream")  # type: ignore[arg-type]


@router.post("/paths", response_model=IdeaPathOut, status_code=201)
async def confirm_path(idea_id: str, body: ConfirmPathRequest) -> IdeaPathOut:
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

    lines = ["# Idea Path\n"]
    for i, nid in enumerate(body.node_chain):
        node = nodes.get(nid)
        if node:
            prefix = "Root" if i == 0 else (node.edge_label or f"Step {i}")
            lines.append(f"## {prefix}\n{node.content}\n")

    chain_text = " → ".join(
        nodes[nid].content for nid in body.node_chain if nid in nodes
    )
    summary = llm.generate_path_summary(chain_text)
    lines.append(f"## 演进摘要\n{summary}\n")
    path_md = "\n".join(lines)

    path_json_data = {
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
        "summary": summary,
    }

    path = repo_dag.create_path(
        idea_id=idea_id,
        node_chain=body.node_chain,
        path_md=path_md,
        path_json=json.dumps(path_json_data, ensure_ascii=False),
    )

    # Stamp confirmed_dag_path_id onto the idea context so guards unlock Feasibility
    _repo.apply_agent_update(
        idea_id,
        version=idea.version,
        mutate_context=lambda ctx: ctx.model_copy(update={"confirmed_dag_path_id": path.id}),
    )

    return IdeaPathOut(**path.__dict__)


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
