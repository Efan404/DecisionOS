from __future__ import annotations

import logging
import re

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.auth import require_authenticated_user
from app.core.logging_config import setup_logging
from app.core.rate_limit import InMemoryRateLimiter, resolve_client_identifier
from app.core.request_logging import RequestLoggingMiddleware
from app.core.scheduler import create_scheduler
from app.core.settings import get_settings
from app.db.bootstrap import initialize_database
from app.routes.agents import router as agents_router
from app.routes.ai_settings import router as ai_settings_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.idea_agents import router as idea_agents_router
from app.routes.idea_dag import router as idea_dag_router
from app.routes.idea_prd_export import router as idea_prd_export_router
from app.routes.idea_prd_feedback import router as idea_prd_feedback_router
from app.routes.idea_scope import router as idea_scope_router
from app.routes.idea_market_evidence import router as idea_market_evidence_router
from app.routes.ideas import router as ideas_router
from app.routes.notifications import router as notifications_router
from app.routes.insights import router as insights_router
from app.routes.profile import router as profile_router
from app.routes.workspaces import router as workspaces_router

logger = logging.getLogger(__name__)

_IDEA_AGENTS_MUTATION_RE = re.compile(r"^/ideas/[^/]+/agents/[^/]+(?:/stream)?$")


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
    limiter = InMemoryRateLimiter()

    @app.middleware("http")
    async def enforce_rate_limits(request, call_next):  # type: ignore[no-untyped-def]
        method = request.method.upper()
        path = request.url.path
        client_id = resolve_client_identifier(request)

        if method == "POST" and path == "/auth/login":
            violation = limiter.consume(
                key=f"login:{client_id}",
                max_requests=settings.rate_limit_login_max_requests,
                window_seconds=settings.rate_limit_login_window_seconds,
                message="Too many login attempts. Please try again later.",
            )
            if violation is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": violation.detail},
                    headers={"Retry-After": str(violation.retry_after_seconds)},
                )

        if method == "POST" and _IDEA_AGENTS_MUTATION_RE.match(path):
            violation = limiter.consume(
                key=f"idea-agents:{client_id}",
                max_requests=settings.rate_limit_idea_agents_max_requests,
                window_seconds=settings.rate_limit_idea_agents_window_seconds,
                message="Too many agent requests. Please try again later.",
            )
            if violation is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": violation.detail},
                    headers={"Retry-After": str(violation.retry_after_seconds)},
                )

        return await call_next(request)

    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(auth_router)

    protected_dependencies = [] if settings.auth_disabled else [Depends(require_authenticated_user)]
    app.include_router(workspaces_router, dependencies=protected_dependencies)
    app.include_router(ai_settings_router, dependencies=protected_dependencies)
    app.include_router(ideas_router, dependencies=protected_dependencies)
    app.include_router(idea_agents_router, dependencies=protected_dependencies)
    app.include_router(idea_prd_export_router, dependencies=protected_dependencies)
    app.include_router(idea_prd_feedback_router, dependencies=protected_dependencies)
    app.include_router(idea_dag_router, dependencies=protected_dependencies)
    app.include_router(idea_scope_router, dependencies=protected_dependencies)
    app.include_router(idea_market_evidence_router, dependencies=protected_dependencies)
    app.include_router(agents_router, dependencies=protected_dependencies)
    app.include_router(notifications_router, dependencies=protected_dependencies)
    app.include_router(insights_router, dependencies=protected_dependencies)
    app.include_router(profile_router, dependencies=protected_dependencies)

    scheduler = create_scheduler()

    @app.on_event("startup")
    async def start_scheduler() -> None:
        scheduler.start()
        logger.info("scheduler.started")

    @app.on_event("shutdown")
    async def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")


    return app


app = create_app()
