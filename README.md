# DecisionOS

A single-user, single-workspace decision management system for product ideas. DecisionOS guides you through a structured workflow from initial idea to production-ready PRD.

> 🌐 **English** | [中文](README.zh-CN.md)

## Overview

DecisionOS helps product managers and indie hackers make better decisions by providing a structured framework for:

- **Exploring ideas** via an interactive DAG (Directed Acyclic Graph) canvas
- **Evaluating feasibility** with AI-assisted analysis
- **Freezing scope** to create clear boundaries
- **Generating PRDs** with full context from previous stages

### Decision Flow

```mermaid
graph LR
    A[Idea Canvas] --> B[Feasibility]
    B --> C[Scope Freeze]
    C --> D[PRD Generation]

    A -.->|AI Expansion| A
    B -.->|AI Analysis| B
    D -.->|AI Generation| D
```

## Features

- **Idea Canvas**: Visual DAG-based ideation with AI-powered node expansion
- **Feasibility Analysis**: Compare three implementation plans generated concurrently via SSE streaming
- **Scope Management**: Define IN/OUT scope with versioned baselines
- **PRD Generation**: LangGraph-powered parallel generation of requirements, backlog, and markdown narrative with real-time agent activity streaming
- **Requirements & Backlog**: Left-right split view linking requirements to backlog items, with inline export (JSON/CSV)
- **Contextual HoverCards**: Hover tooltips across the app revealing hidden metadata — acceptance criteria, score breakdowns, full IDs, timestamps, and dependencies
- **Multi-Idea Support**: Manage multiple ideas within a single workspace

> For architecture deep-dive (LangGraph agents, proactive intelligence, memory system), see [docs/architecture.md](docs/architecture.md).

## Tech Stack

| Layer    | Technology                                               |
| -------- | -------------------------------------------------------- |
| Frontend | Next.js 14 (App Router), React, TypeScript, Tailwind CSS |
| Backend  | FastAPI, Python 3.12, Pydantic                           |
| Database | SQLite (with Postgres migration path)                    |
| AI       | ModelScope / Auto (configurable providers)               |

## Project Structure

```text
.
├── frontend/          # Next.js 14 frontend
│   ├── app/          # App Router pages
│   ├── components/   # React components
│   └── lib/          # Utilities, API clients, store
├── backend/          # FastAPI backend
│   └── app/
│       ├── core/     # Auth, settings, LLM gateway
│       ├── db/       # Models, repositories
│       ├── routes/   # API endpoints
│       └── schemas/  # Pydantic schemas
├── docker-compose.yml
└── package.json      # Root workspace config
```

## Quick Start (Local Development)

### Prerequisites

- Node.js 20+
- Python 3.12+
- pnpm
- uv (Python package manager)

### 1. Clone and Install

```bash
# Install frontend dependencies
pnpm install

# Setup Python environment
cd backend
uv venv .venv
UV_CACHE_DIR=../.uv-cache uv pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Required: Admin credentials (no defaults provided)
export DECISIONOS_SEED_ADMIN_USERNAME=admin
export DECISIONOS_SEED_ADMIN_PASSWORD=your-secure-password-here

# Optional
export LLM_MODE=mock              # mock | auto | modelscope
export DECISIONOS_SECRET_KEY=your-secret-key
```

> ⚠️ **Security**: You MUST set admin credentials via environment variables. The application will fail to start without them.

> **Local dev CORS**: The frontend proxies all `/api-proxy/*` requests to `http://127.0.0.1:8000` via Next.js rewrites, so no CORS configuration is needed locally. `NEXT_PUBLIC_API_BASE_URL` is only required for production/Docker deployments.

### 3. Start Backend

```bash
cd backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Start Frontend

```bash
pnpm dev:web
```

Visit `http://localhost:3000` and login with your configured admin credentials.

## Deployment

### Docker Compose (Recommended)

```bash
export DECISIONOS_SEED_ADMIN_USERNAME=admin
export DECISIONOS_SEED_ADMIN_PASSWORD=your-secure-password
export LLM_MODE=auto   # or mock for testing

docker compose up --build -d
```

Access:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

**How the proxy works in Docker**: the `web` container builds with `API_INTERNAL_URL=http://api:8000`. All browser requests go to `http://localhost:3000/api-proxy/...`, which Next.js forwards server-side to the `api` container over Docker's internal network — no CORS issues, no backend port exposed to the browser.

> **Note**: SQLite is persisted via named volume `decisionos_data` mounted at `/data`.

### CI/CD with GitHub Actions + Coolify (Recommended for production)

The recommended production setup uses GitHub Actions to test and build images, then Coolify to pull and run them — no build workload on your server.

**How it works:**

```
git push → GitHub Actions
               ├── run backend tests (pytest)
               ├── run frontend type-check + build
               └── on success: build & push images to ghcr.io
                       ↓
                   Coolify pulls ghcr.io/you/decisionos-api:latest
                             and ghcr.io/you/decisionos-web:latest
                             and restarts containers
```

**Step 1 — Make GHCR packages public** (one-time)

After the first push triggers the workflow, go to your GitHub profile → Packages → `decisionos-api` and `decisionos-web` → change visibility to **Public**. This lets Coolify pull without credentials.

**Step 2 — Configure Coolify to use pre-built images**

In Coolify, create a new **Docker Compose** service and paste the following compose content directly (replacing `<your-github-username>`):

```yaml
services:
  api:
    image: ghcr.io/<your-github-username>/decisionos-api:latest
    environment:
      LLM_MODE: ${LLM_MODE:-auto}
      DECISIONOS_DB_PATH: ${DECISIONOS_DB_PATH:-/data/decisionos.db}
      DECISIONOS_SECRET_KEY: ${DECISIONOS_SECRET_KEY}
      DECISIONOS_CORS_ORIGINS: ${DECISIONOS_CORS_ORIGINS:-http://localhost:3000}
      DECISIONOS_SEED_ADMIN_USERNAME: ${DECISIONOS_SEED_ADMIN_USERNAME}
      DECISIONOS_SEED_ADMIN_PASSWORD: ${DECISIONOS_SEED_ADMIN_PASSWORD}
    volumes:
      - decisionos_data:/data
    expose:
      - '8000'
    healthcheck:
      test:
        [
          'CMD',
          'python',
          '-c',
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()",
        ]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  web:
    image: ghcr.io/<your-github-username>/decisionos-web:latest
    environment:
      API_INTERNAL_URL: ${API_INTERNAL_URL:-http://api:8000}
    depends_on:
      api:
        condition: service_healthy
    ports:
      - '3000:3000'
    restart: unless-stopped

volumes:
  decisionos_data:
```

**Step 3 — Set environment variables in Coolify**

| Variable                         | Value                                  |
| -------------------------------- | -------------------------------------- |
| `DECISIONOS_SEED_ADMIN_USERNAME` | Your admin username                    |
| `DECISIONOS_SEED_ADMIN_PASSWORD` | Strong admin password                  |
| `DECISIONOS_SECRET_KEY`          | Random secret (`openssl rand -hex 32`) |
| `LLM_MODE`                       | `auto` (or `modelscope`)               |

**Step 4** — Expose only the `web` service (port 3000) with your domain. The `api` container does not need a public domain.

> **Port note**: `api` uses `expose` (not `ports`) so it is only reachable inside the Docker network — this prevents host port conflicts on shared Coolify servers.

---

### Coolify (build from source, simpler setup)

If you prefer Coolify to build images itself without GitHub Actions:

1. Create a **Docker Compose** service in Coolify pointing to this repo (`docker-compose.yml`)
2. Set the same environment variables as above
3. Expose only the `web` service on port 3000 with your domain

## Configuration

### Required Environment Variables

| Variable                         | Description    | Example         |
| -------------------------------- | -------------- | --------------- |
| `DECISIONOS_SEED_ADMIN_USERNAME` | Admin username | `admin`         |
| `DECISIONOS_SEED_ADMIN_PASSWORD` | Admin password | `change-me-now` |

### Optional Environment Variables

| Variable                              | Default                           | Description                                                             |
| ------------------------------------- | --------------------------------- | ----------------------------------------------------------------------- |
| `DECISIONOS_DB_PATH`                  | `./decisionos.db`                 | SQLite database path                                                    |
| `DECISIONOS_SECRET_KEY`               | `decisionos-dev-secret-change-me` | Encryption key for secrets                                              |
| `DECISIONOS_CORS_ORIGINS`             | `http://localhost:3000`           | Comma-separated allowed origins                                         |
| `DECISIONOS_AUTH_DISABLED`            | `false`                           | Disable auth (dev only)                                                 |
| `DECISIONOS_AUTH_SESSION_TTL_SECONDS` | `43200`                           | Session timeout (12 hours)                                              |
| `LLM_MODE`                            | `auto`                            | AI mode: `mock`, `auto`, or `modelscope`                                |
| `API_INTERNAL_URL`                    | `http://127.0.0.1:8000`           | Backend URL used by Next.js server (set to `http://api:8000` in Docker) |

### Seed Users

Two seed users are created on first startup:

- **Admin**: Required, credentials from environment variables
- **Test**: Optional, defaults to `test`/`test` (configurable via env)

## Core Concepts

### Decision Stages

1. **Idea Canvas**: Explore ideas using a visual DAG. Start with a seed, expand nodes using AI patterns (narrow audience, expand features, scenario shift, etc.), and confirm a path.

2. **Feasibility**: Evaluate three implementation approaches generated concurrently (bootstrapped, VC-funded, platform/ecosystem). Plans stream to the UI as they arrive via SSE, with animated skeleton placeholders while generation is in flight. Select one plan to proceed.

3. **Scope Freeze**: Define clear IN/OUT scope. Create versioned baselines. Once frozen, scope becomes immutable for PRD generation.

4. **PRD Generation**: Generate structured PRDs via LangGraph with parallel fan-out:
   - Markdown narrative + requirements generated concurrently (Stage A)
   - Backlog items linked to requirements (Stage B)
   - Real-time agent activity stream shows generation progress
   - Requirements & Backlog displayed in a left-right split view with inline filtering and export

### Authentication

- Bearer token-based authentication
- Sessions stored in database with configurable TTL
- Tokens are hashed using SHA-256 before storage
- Passwords use PBKDF2-SHA256 with random salt (210,000 iterations)

## API Documentation

When the backend is running, visit:

```
http://localhost:8000/docs
```

This provides interactive OpenAPI/Swagger documentation with all endpoints, request/response schemas, and authentication requirements.

### Market Evidence Operations

DecisionOS includes a market evidence layer that tracks competitors and market signals per idea. These endpoints require authentication.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ideas/{idea_id}/evidence/competitors/discover` | Trigger competitor discovery for an idea |
| `GET` | `/ideas/{idea_id}/evidence/competitors` | List competitors linked to an idea (with latest snapshots) |
| `GET` | `/ideas/{idea_id}/evidence/signals` | List market signals linked to an idea |
| `POST` | `/ideas/{idea_id}/evidence/insights/sync` | Trigger one-shot insight synthesis for an idea |
| `POST` | `/insights/signal-monitor/trigger` | Manually trigger the signal monitor (cross-idea) |

**Rebuild vector chunks from SQLite:**

If the ChromaDB cache is deleted or corrupted, competitor/signal chunks can be rebuilt programmatically via `MarketEvidenceService.rebuild_market_chunks_for_competitor(competitor_id)`. This reads canonical data from SQLite and re-indexes it into the vector store.

### Cross-Idea Insights V2

Cross-Idea Insights V2 identifies reusable assets, merge candidates, and positioning conflicts across ideas using structured analysis.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/ideas/{idea_id}/cross-insights` | List structured cross-idea insights for one idea |
| `POST` | `/ideas/{idea_id}/cross-insights/sync` | Trigger cross-idea analysis for one idea |
| `POST` | `/insights/cross-idea-analysis` | Trigger workspace-wide cross-idea analysis |
| `GET` | `/insights/cross-idea` | List all cross-idea insights (V2 + legacy) |

**Insight types**: `execution_reuse`, `merge_candidate`, `positioning_conflict`, `shared_audience`, `shared_capability`, `evidence_overlap`

**No graph database in V1** — SQLite relations plus vector recall are sufficient for current requirements.

## Development

### Frontend

```bash
pnpm dev:web      # Development server
pnpm build:web    # Production build
```

### Backend

```bash
# Type checking
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python mypy app

# Run tests
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python pytest
```

### Code Style

- Frontend: Prettier + ESLint (enforced via Husky pre-commit hooks)
- Backend: Follow PEP 8, type hints required

## Architecture Decisions

### SQLite for Single-User

SQLite is chosen for simplicity in single-user deployments. The schema is designed to be migration-friendly for future Postgres support.

### Optimistic Locking

All mutating operations use version-based optimistic locking to prevent concurrent modification issues.

### Context as JSON

Idea context is stored as JSON with schema versioning. This allows flexible evolution of the data model while maintaining backward compatibility.

## License

MIT
