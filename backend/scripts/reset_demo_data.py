"""Remove demo SQLite rows and vector-store demo records while preserving user data.

Run: cd backend && python -m scripts.reset_demo_data
"""
from __future__ import annotations

import argparse

from app.agents.memory.seed_data import DEMO_IDEAS, DEMO_NEWS, DEMO_PATTERNS
from app.agents.memory.vector_store import get_vector_store
from app.db.engine import db_session


def reset_demo_data(*, reset_db: bool = True, reset_vector: bool = True) -> None:
    if reset_db:
        _reset_demo_sqlite()
    if reset_vector:
        _reset_demo_vector_store()


def _reset_demo_sqlite() -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM notification WHERE id LIKE 'demo-%'")
        conn.execute("DELETE FROM decision_events WHERE id LIKE 'demo-%'")
        conn.execute("DELETE FROM scope_baselines WHERE idea_id LIKE 'demo-%'")
        conn.execute("DELETE FROM idea_paths WHERE idea_id LIKE 'demo-%'")
        conn.execute("DELETE FROM idea_nodes WHERE id LIKE 'demo-%'")
        conn.execute("DELETE FROM idea WHERE id LIKE 'demo-%'")


def _reset_demo_vector_store() -> None:
    vs = get_vector_store()
    vs._ideas.delete(ids=[item["id"] for item in DEMO_IDEAS])
    vs._news.delete(ids=[item["id"] for item in DEMO_NEWS])
    vs._patterns.delete(ids=[item["id"] for item in DEMO_PATTERNS])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Reset SQLite demo data only.",
    )
    parser.add_argument(
        "--vector-only",
        action="store_true",
        help="Reset vector-store demo data only.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.db_only and args.vector_only:
        parser.error("--db-only and --vector-only cannot be used together")

    reset_demo_data(
        reset_db=not args.vector_only,
        reset_vector=not args.db_only,
    )


if __name__ == "__main__":
    main()
