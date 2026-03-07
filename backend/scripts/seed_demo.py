"""Standalone compatibility wrapper for vector-only demo seeding.

Run: cd backend && python -m scripts.seed_demo
"""
from __future__ import annotations

from scripts.seed_demo_full import seed_demo_full

if __name__ == "__main__":
    seed_demo_full(seed_db=False, seed_vector=True)
    print("Vector-store demo data seeded. For full SQLite + vector seeding, run: python -m scripts.seed_demo_full")
