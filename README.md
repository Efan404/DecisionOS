# DecisionOS MVP

This repository now contains a DecisionOS hackathon MVP scaffold defined by `AGENTS.md`.

## Structure

```text
frontend        # Next.js App Router frontend
backend         # FastAPI backend (JSON + SSE)
```

## Frontend

- Entry: `frontend/app/page.tsx`
- Core flow pages (idea-scoped):
  - `/ideas`
  - `/ideas/[ideaId]/idea-canvas`
  - `/ideas/[ideaId]/feasibility`
  - `/ideas/[ideaId]/feasibility/[id]`
  - `/ideas/[ideaId]/scope-freeze`
  - `/ideas/[ideaId]/prd`

Run commands:

```bash
pnpm dev:web
pnpm build:web
```

## Backend

- Entry: `backend/app/main.py`
- Health: `GET /health`
- Workspace and ideas:
  - `GET /workspaces/default`
  - `GET /ideas`
  - `POST /ideas`
  - `GET /ideas/{idea_id}`
  - `PATCH /ideas/{idea_id}`
  - `PATCH /ideas/{idea_id}/context`
- DAG canvas (idea-scoped):
  - `GET /ideas/{idea_id}/nodes`
  - `POST /ideas/{idea_id}/nodes`
  - `GET /ideas/{idea_id}/nodes/{node_id}`
  - `POST /ideas/{idea_id}/nodes/{node_id}/expand/user`
  - `POST /ideas/{idea_id}/nodes/{node_id}/expand/stream` (SSE, query param: `pattern_id`)
  - `POST /ideas/{idea_id}/paths`
  - `GET /ideas/{idea_id}/paths/latest`
- JSON endpoints:
  - `POST /ideas/{idea_id}/agents/opportunity`
  - `POST /ideas/{idea_id}/agents/feasibility`
  - `POST /ideas/{idea_id}/agents/scope`
  - `POST /ideas/{idea_id}/agents/prd`
- SSE endpoints:
  - `POST /ideas/{idea_id}/agents/opportunity/stream`
  - `POST /ideas/{idea_id}/agents/feasibility/stream`
- AI aggregation settings:
  - `GET /settings/ai`
  - `PATCH /settings/ai`
  - `POST /settings/ai/test`
  - Frontend page: `/settings`

Legacy compatibility note:

- `POST /agents/*` now returns `410 Gone` and should not be used.

Setup and run:

```bash
cd backend
uv venv .venv
UV_CACHE_DIR=../.uv-cache uv pip install -r requirements.txt
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Optional env vars:

```bash
export LLM_MODE=auto  # default; set mock to force deterministic mock-only mode
export DECISIONOS_SECRET_KEY="replace-with-strong-secret"
```

AI routing behavior:

- If a task routing list is empty, backend will try all enabled providers in order as fallback.

Type checking:

```bash
cd backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python mypy app
```

## Notes

- Frontend uses Zustand persist with `skipHydration: true` and manual rehydrate.
- SSE client uses `fetch` stream parsing and supports `AbortController`.
- Backend mock outputs are deterministic by `idea_seed`.
- AI provider API keys are stored encrypted in SQLite using `DECISIONOS_SECRET_KEY` (set this in production).
- Idea Canvas is powered by a DAG (Directed Acyclic Graph) using `@xyflow/react`. Components live in `frontend/components/idea/dag/`.
- DAG expansion patterns are hardcoded in `backend/app/schemas/dag.py` (`EXPANSION_PATTERNS`): 缩小用户群体, 功能边界扩展, 场景迁移, 商业模式变体, 极简核心.
- Confirmed paths (`idea_paths`) store both `path_md` (Markdown, LLM-ready context) and `path_json` (structured, for cross-idea analysis) for use in downstream stages.
