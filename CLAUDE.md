# Project Notes for Claude

## PRD Feature Status

PRD backlog and requirements features are **actively being restored** (as of 2026-03-06). The two-stage parallel generation (requirements + backlog) and the corresponding frontend tabs (Requirements, Backlog) are being re-enabled.

Key files involved:
- Backend: `backend/app/routes/idea_agents.py` — `stream_prd` and the commented `--- DISABLED: two-stage parallel generation ---` block
- Frontend: `frontend/components/prd/PrdView.tsx` — Requirements/Backlog tabs currently commented out
