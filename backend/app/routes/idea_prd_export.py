from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app.core.contexts import parse_context_strict
from app.core.time import utc_now_iso
from app.db.repo_ideas import IdeaRepository
from app.schemas.ideas import DecisionContext
from app.schemas.prd import PRDBacklogExportJson, PRDBacklogItem

router = APIRouter(prefix="/ideas/{idea_id}/prd", tags=["idea-prd-export"])
_repo = IdeaRepository()


def _resolve_backlog_output(
    context: DecisionContext,
) -> tuple[str, list[PRDBacklogItem]]:
    """Return (baseline_id, items) from persisted PRD data.

    Prefers context.prd_bundle.output; falls back to context.prd for backward
    compatibility. Raises HTTPException(409) when no backlog is available.
    """
    if context.prd_bundle is not None:
        items = context.prd_bundle.output.backlog.items
        baseline_id = context.prd_bundle.baseline_id
        return baseline_id, items

    if context.prd is not None:
        items = context.prd.backlog.items
        baseline_id = context.prd.generation_meta.baseline_id
        return baseline_id, items

    raise HTTPException(
        status_code=409,
        detail={
            "code": "PRD_BACKLOG_NOT_READY",
            "message": "Generate PRD before exporting the backlog",
        },
    )


def _serialize_backlog_csv(items: list[PRDBacklogItem]) -> str:
    """Serialize backlog items to CSV using Python's csv module."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row — exact column order per plan
    writer.writerow(
        [
            "id",
            "title",
            "type",
            "priority",
            "summary",
            "requirement_id",
            "acceptance_criteria",
            "source_refs",
            "depends_on",
        ]
    )

    for item in items:
        writer.writerow(
            [
                item.id,
                item.title,
                item.type,
                item.priority,
                item.summary,
                item.requirement_id,
                " | ".join(item.acceptance_criteria),
                " | ".join(item.source_refs),
                " | ".join(item.depends_on),
            ]
        )

    return output.getvalue()


@router.get("/export")
async def export_prd_backlog(
    idea_id: str,
    format: str = Query(default="json"),  # noqa: A002
) -> Response:
    """Export the persisted PRD backlog as JSON or CSV."""
    # Validate format before loading the idea
    if format not in {"json", "csv"}:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXPORT_FORMAT_INVALID",
                "message": f"Unsupported export format {format!r}. Use 'json' or 'csv'.",
            },
        )

    idea = _repo.get_idea(idea_id)
    if idea is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": "Idea not found"},
        )
    if idea.status == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    context = parse_context_strict(idea.context)
    baseline_id, items = _resolve_backlog_output(context)

    if format == "csv":
        csv_body = _serialize_backlog_csv(items)
        return Response(
            content=csv_body.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="decisionos-backlog-{idea_id}.csv"',
            },
        )

    # JSON export
    export = PRDBacklogExportJson(
        idea_id=idea_id,
        baseline_id=baseline_id,
        exported_at=utc_now_iso(),
        item_count=len(items),
        items=items,
    )
    return JSONResponse(content=export.model_dump(mode="python"))
