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
| `DECISIONOS_CHROMA_PATH`         | No       | Chroma persistence path (default: `./chroma_data`) |
| `DECISIONOS_AUTH_DISABLED`       | No       | Set `1` to disable auth (dev only)               |

## Start (Development)

Run from the **backend/** directory:

```bash
UV_CACHE_DIR=../.uv-cache \
uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Server runs at `http://127.0.0.1:8000`. Health check: `GET /health`.

Default credentials: `admin` / `admin`.

## Demo Data Behavior

- App startup runs `initialize_database()` from `app.db.bootstrap`.
- That bootstrap path seeds:
  - SQLite demo records via `app.db.seed_demo.seed_demo_data`
  - vector-store demo records only if the Chroma collections are empty
- The standalone script `scripts/seed_demo.py` currently seeds the vector store only. It is not a full SQLite + vector demo initializer.

## Path Resolution Warning

- `DECISIONOS_DB_PATH=./decisionos.db` and `DECISIONOS_CHROMA_PATH=./chroma_data` are resolved relative to the current working directory.
- If you start the API from a different directory, you may silently create a different SQLite or Chroma store.
- For remote or containerized deployments, prefer absolute paths such as `/data/decisionos.db` and `/data/chroma`.

## Run in Background

```bash
UV_CACHE_DIR=../.uv-cache \
nohup uv run --python .venv/bin/python uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &
```

Check logs: `tail -f /tmp/backend.log`
