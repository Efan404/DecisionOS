# Project Notes for Claude

## PRD Feature Status

PRD backlog and requirements features are **restored and active** via LangGraph (as of 2026-03-06).

The `stream_prd` endpoint now drives a LangGraph graph with true parallel fan-out:
- Stage A (parallel via `Send`): `requirements_writer` + `markdown_writer`
- Stage B (sequential): `backlog_writer` (reads requirement IDs from Stage A)
- Then: `prd_reviewer` → `memory_writer` → END

SSE events emitted: `agent_thought`, `requirements`, `backlog`, `progress`, `done`, `error`

Key files:
- Backend: `backend/app/agents/graphs/prd_subgraph.py` — LangGraph PRD graph
- Backend: `backend/app/routes/idea_agents.py` — `stream_prd` endpoint
- Backend: `backend/app/agents/state.py` — `DecisionOSState` with typed PRD fields
- Frontend: `frontend/components/prd/PrdView.tsx` — Requirements/Sections/Backlog tabs active
- Frontend: `frontend/components/prd/PrdPage.tsx` — SSE handler wires `requirements` and `backlog` events
