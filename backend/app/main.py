from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import get_settings
from app.db.bootstrap import initialize_database
from app.routes.agents import router as agents_router
from app.routes.ai_settings import router as ai_settings_router
from app.routes.health import router as health_router
from app.routes.idea_agents import router as idea_agents_router
from app.routes.idea_dag import router as idea_dag_router
from app.routes.idea_scope import router as idea_scope_router
from app.routes.ideas import router as ideas_router
from app.routes.workspaces import router as workspaces_router


def create_app() -> FastAPI:
    settings = get_settings()
    initialize_database()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(workspaces_router)
    app.include_router(ai_settings_router)
    app.include_router(ideas_router)
    app.include_router(idea_agents_router)
    app.include_router(idea_dag_router)
    app.include_router(idea_scope_router)
    app.include_router(agents_router)
    return app


app = create_app()
