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

| Variable                         | Required | Description                                      |
| -------------------------------- | -------- | ------------------------------------------------ |
| `LLM_MODE`                       | No       | `mock` / `auto` / `modelscope` (default: `auto`) |
| `DECISIONOS_SECRET_KEY`          | No       | JWT secret key                                   |
| `DECISIONOS_DB_PATH`             | No       | SQLite file path (default: `./decisionos.db`)    |
| `DECISIONOS_AUTH_DISABLED`       | No       | Set `1` to disable auth (dev only)               |

## Start (Development)

Run from the **backend/** directory:

```bash
UV_CACHE_DIR=../.uv-cache \
uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Server runs at `http://127.0.0.1:8000`. Health check: `GET /health`.

Default credentials: `admin` / `admin`.

## Run in Background

```bash
UV_CACHE_DIR=../.uv-cache \
nohup uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &
```

Check logs: `tail -f /tmp/backend.log`
