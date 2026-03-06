from __future__ import annotations

import os


def ensure_required_seed_env() -> None:
    os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
    os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")
    # Force in-memory ChromaDB in tests — prevents disk writes and singleton pollution
    os.environ.setdefault("DECISIONOS_CHROMA_PATH", "")
