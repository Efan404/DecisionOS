"""Explicitly seed both SQLite demo data and vector-store demo data.

Run: cd backend && python -m scripts.seed_demo_full
"""
from __future__ import annotations

import argparse

from app.db.bootstrap import seed_demo_sqlite, seed_demo_vector_store


def seed_demo_full(*, seed_db: bool = True, seed_vector: bool = True) -> None:
    if seed_db:
        seed_demo_sqlite()
    if seed_vector:
        seed_demo_vector_store()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Seed SQLite demo data only.",
    )
    parser.add_argument(
        "--vector-only",
        action="store_true",
        help="Seed vector-store demo data only.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.db_only and args.vector_only:
        parser.error("--db-only and --vector-only cannot be used together")

    seed_demo_full(
        seed_db=not args.vector_only,
        seed_vector=not args.db_only,
    )


if __name__ == "__main__":
    main()
