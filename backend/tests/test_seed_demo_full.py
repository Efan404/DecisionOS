from __future__ import annotations

import os

from tests._test_env import ensure_required_seed_env


def _reset_runtime(db_path: str, chroma_path: str) -> None:
    os.environ["DECISIONOS_DB_PATH"] = db_path
    os.environ["DECISIONOS_CHROMA_PATH"] = chroma_path

    from app.core.settings import get_settings

    get_settings.cache_clear()

    import app.agents.memory.vector_store as vector_store_module

    vector_store_module._singleton = None


def test_seed_demo_full_populates_sqlite_and_vector_store(tmp_path):
    ensure_required_seed_env()
    db_path = str(tmp_path / "seed-demo.db")
    chroma_path = str(tmp_path / "chroma")
    _reset_runtime(db_path=db_path, chroma_path=chroma_path)

    from scripts.seed_demo_full import seed_demo_full
    from app.db.engine import db_session
    from app.agents.memory.vector_store import get_vector_store

    seed_demo_full()

    with db_session() as conn:
        idea_count = conn.execute("SELECT COUNT(*) AS cnt FROM idea").fetchone()["cnt"]
        demo_idea_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM idea WHERE id LIKE 'demo-%'"
        ).fetchone()["cnt"]
        notification_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM notification"
        ).fetchone()["cnt"]

    assert idea_count >= 3
    assert demo_idea_count >= 3
    assert notification_count >= 1

    vs = get_vector_store()
    assert vs._ideas.count() >= 5
    assert vs._news.count() >= 5
    assert vs._patterns.count() >= 3


def test_seed_demo_full_is_idempotent_and_preserves_ai_settings(tmp_path):
    ensure_required_seed_env()
    db_path = str(tmp_path / "seed-demo.db")
    chroma_path = str(tmp_path / "chroma")
    _reset_runtime(db_path=db_path, chroma_path=chroma_path)

    from app.db.bootstrap import initialize_database
    from app.db.engine import db_session
    from app.db.repo_ai import AISettingsRepository
    from app.schemas.ai_settings import AIProviderConfig, AISettingsPayload
    from scripts.seed_demo_full import seed_demo_full

    initialize_database()

    repo = AISettingsRepository()
    repo.update_settings(
        AISettingsPayload(
            providers=[
                AIProviderConfig(
                    id="prov-1",
                    name="Demo Provider",
                    kind="openai_compatible",
                    base_url="https://example.com/v1",
                    api_key="secret-demo-key",
                    model="demo-model",
                    enabled=True,
                )
            ]
        )
    )

    before = repo.get_settings()

    seed_demo_full()
    seed_demo_full()

    after = repo.get_settings()

    with db_session() as conn:
        demo_idea_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM idea WHERE id LIKE 'demo-%'"
        ).fetchone()["cnt"]

    assert demo_idea_count == 3
    assert len(after.config.providers) == 1
    assert after.config.providers[0].id == before.config.providers[0].id
    assert after.config.providers[0].api_key == before.config.providers[0].api_key
