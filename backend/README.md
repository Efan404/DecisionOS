# Backend

FastAPI + SQLite backend for DecisionOS.

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Setup

```bash
cd backend
uv venv .venv
UV_CACHE_DIR=../.uv-cache uv pip install -r requirements.txt
```

## Environment Variables

The following variables must be set before starting the server:

| Variable                         | Required | Description                                      |
| -------------------------------- | -------- | ------------------------------------------------ |
| `DECISIONOS_SEED_ADMIN_USERNAME` | Yes      | Admin username (seeded on first start)           |
| `DECISIONOS_SEED_ADMIN_PASSWORD` | Yes      | Admin password                                   |
| `LLM_MODE`                       | No       | `mock` / `auto` / `modelscope` (default: `auto`) |
| `DECISIONOS_SECRET_KEY`          | No       | JWT secret key                                   |
| `DECISIONOS_DB_PATH`             | No       | SQLite file path (default: `./decisionos.db`)    |
| `DECISIONOS_AUTH_DISABLED`       | No       | Set `1` to disable auth (dev only)               |

## Start (Development)

Run from the **backend/** directory:

```bash
DECISIONOS_SEED_ADMIN_USERNAME=admin \
DECISIONOS_SEED_ADMIN_PASSWORD=admin \
UV_CACHE_DIR=../.uv-cache \
uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or export variables first:

```bash
export DECISIONOS_SEED_ADMIN_USERNAME=admin
export DECISIONOS_SEED_ADMIN_PASSWORD=admin
export UV_CACHE_DIR=../.uv-cache
uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Server runs at `http://127.0.0.1:8000`. Health check: `GET /health`.

## Run in Background

```bash
DECISIONOS_SEED_ADMIN_USERNAME=admin \
DECISIONOS_SEED_ADMIN_PASSWORD=admin \
UV_CACHE_DIR=../.uv-cache \
nohup uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &
```

Check logs: `tail -f /tmp/backend.log`
