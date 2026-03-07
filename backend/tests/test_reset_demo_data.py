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


def test_reset_demo_data_removes_demo_rows_and_preserves_ai_settings(tmp_path):
    ensure_required_seed_env()
    db_path = str(tmp_path / "reset-demo.db")
    chroma_path = str(tmp_path / "chroma")
    _reset_runtime(db_path=db_path, chroma_path=chroma_path)

    from app.db.bootstrap import initialize_database
    from app.db.repo_ai import AISettingsRepository
    from app.db.repo_ideas import IdeaRepository
    from app.db.engine import db_session
    from app.schemas.ai_settings import AIProviderConfig, AISettingsPayload
    from scripts.seed_demo_full import seed_demo_full
    from scripts.reset_demo_data import reset_demo_data
    from app.agents.memory.vector_store import get_vector_store

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

    user_idea = IdeaRepository().create_idea(title="User Idea", idea_seed="custom seed")
    seed_demo_full()

    vs = get_vector_store()
    assert vs._ideas.count() >= 5
    assert vs._news.count() >= 5
    assert vs._patterns.count() >= 3

    reset_demo_data()

    with db_session() as conn:
        demo_ideas = conn.execute(
            "SELECT COUNT(*) AS cnt FROM idea WHERE id LIKE 'demo-%'"
        ).fetchone()["cnt"]
        demo_paths = conn.execute(
            "SELECT COUNT(*) AS cnt FROM idea_paths WHERE idea_id LIKE 'demo-%'"
        ).fetchone()["cnt"]
        demo_baselines = conn.execute(
            "SELECT COUNT(*) AS cnt FROM scope_baselines WHERE idea_id LIKE 'demo-%'"
        ).fetchone()["cnt"]
        user_ideas = conn.execute(
            "SELECT COUNT(*) AS cnt FROM idea WHERE id = ?",
            (user_idea.id,),
        ).fetchone()["cnt"]
        demo_notifications = conn.execute(
            "SELECT COUNT(*) AS cnt FROM notification WHERE id LIKE 'demo-%'"
        ).fetchone()["cnt"]
        demo_events = conn.execute(
            "SELECT COUNT(*) AS cnt FROM decision_events WHERE id LIKE 'demo-%'"
        ).fetchone()["cnt"]

    settings = repo.get_settings()

    assert demo_ideas == 0
    assert demo_paths == 0
    assert demo_baselines == 0
    assert user_ideas == 1
    assert demo_notifications == 0
    assert demo_events == 0
    assert len(settings.config.providers) == 1
    assert settings.config.providers[0].api_key == "secret-demo-key"
    assert vs._ideas.count() == 0
    assert vs._news.count() == 0
    assert vs._patterns.count() == 0
