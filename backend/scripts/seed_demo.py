"""Standalone script to seed demo data for hackathon presentation.

Run: cd backend && python -m scripts.seed_demo
"""
from __future__ import annotations

import os

os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.agents.memory.seed_data import seed_vector_store

if __name__ == "__main__":
    vs = seed_vector_store()
    print(
        f"Demo data seeded: {vs._ideas.count()} ideas, "
        f"{vs._news.count()} news, {vs._patterns.count()} patterns"
    )
