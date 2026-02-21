from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import require_authenticated_user
from app.core.logging_config import setup_logging
from app.core.request_logging import RequestLoggingMiddleware
from app.core.settings import get_settings
from app.db.bootstrap import initialize_database
from app.routes.agents import router as agents_router
from app.routes.ai_settings import router as ai_settings_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.idea_agents import router as idea_agents_router
from app.routes.idea_dag import router as idea_dag_router
from app.routes.idea_prd_feedback import router as idea_prd_feedback_router
from app.routes.idea_scope import router as idea_scope_router
from app.routes.ideas import router as ideas_router
from app.routes.workspaces import router as workspaces_router


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    initialize_database()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-Id"],
    )

    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(auth_router)

    protected_dependencies = [] if settings.auth_disabled else [Depends(require_authenticated_user)]
    app.include_router(workspaces_router, dependencies=protected_dependencies)
    app.include_router(ai_settings_router, dependencies=protected_dependencies)
    app.include_router(ideas_router, dependencies=protected_dependencies)
    app.include_router(idea_agents_router, dependencies=protected_dependencies)
    app.include_router(idea_prd_feedback_router, dependencies=protected_dependencies)
    app.include_router(idea_dag_router, dependencies=protected_dependencies)
    app.include_router(idea_scope_router, dependencies=protected_dependencies)
    app.include_router(agents_router, dependencies=protected_dependencies)
    return app


app = create_app()
