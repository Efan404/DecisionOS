from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_name: str
    cors_origins: tuple[str, ...]
    db_path: str
    chroma_path: str | None  # None = in-memory (tests); path = persistent (prod)
    secret_key: str
    auth_disabled: bool
    auth_session_ttl_seconds: int
    seed_admin_username: str
    seed_admin_password: str
    seed_test_username: str
    seed_test_password: str
    rate_limit_login_max_requests: int
    rate_limit_login_window_seconds: int
    rate_limit_idea_agents_max_requests: int
    rate_limit_idea_agents_window_seconds: int


def _parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    defaults = ("http://localhost:3000", "http://127.0.0.1:3000")
    if raw is None or not raw.strip():
        return defaults

    configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
    merged: list[str] = []
    for origin in [*configured, *defaults]:
        if origin not in merged:
            merged.append(origin)
    return tuple(merged) if merged else defaults


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(raw: str | None, *, default: int, minimum: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value >= minimum else default


class ConfigurationError(Exception):
    """Raised when a required configuration is missing or invalid."""

    pass


def _require_env(name: str) -> str:
    """Require an environment variable to be set."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"Required environment variable '{name}' is not set. "
            f"Please set it before starting the application."
        )
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Admin credentials are required - must be set via environment variables
    seed_admin_username = _require_env("DECISIONOS_SEED_ADMIN_USERNAME")
    seed_admin_password = _require_env("DECISIONOS_SEED_ADMIN_PASSWORD")

    return Settings(
        app_name="DecisionOS API",
        cors_origins=_parse_cors_origins(os.getenv("DECISIONOS_CORS_ORIGINS")),
        db_path=os.getenv("DECISIONOS_DB_PATH", "./decisionos.db").strip() or "./decisionos.db",
        chroma_path=os.getenv("DECISIONOS_CHROMA_PATH", "./chroma_data").strip() or "./chroma_data",
        secret_key=(
            os.getenv("DECISIONOS_SECRET_KEY", "").strip()
            or "decisionos-dev-secret-change-me"
        ),
        auth_disabled=_parse_bool(os.getenv("DECISIONOS_AUTH_DISABLED"), default=False),
        auth_session_ttl_seconds=_parse_int(
            os.getenv("DECISIONOS_AUTH_SESSION_TTL_SECONDS"),
            default=43200,
            minimum=300,
        ),
        seed_admin_username=seed_admin_username,
        seed_admin_password=seed_admin_password,
        seed_test_username=os.getenv("DECISIONOS_SEED_TEST_USERNAME", "test").strip() or "test",
        seed_test_password=os.getenv("DECISIONOS_SEED_TEST_PASSWORD", "test").strip() or "test",
        rate_limit_login_max_requests=_parse_int(
            os.getenv("DECISIONOS_RATE_LIMIT_LOGIN_MAX_REQUESTS"),
            default=5,
            minimum=1,
        ),
        rate_limit_login_window_seconds=_parse_int(
            os.getenv("DECISIONOS_RATE_LIMIT_LOGIN_WINDOW_SECONDS"),
            default=60,
            minimum=1,
        ),
        rate_limit_idea_agents_max_requests=_parse_int(
            os.getenv("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_MAX_REQUESTS"),
            default=30,
            minimum=1,
        ),
        rate_limit_idea_agents_window_seconds=_parse_int(
            os.getenv("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_WINDOW_SECONDS"),
            default=60,
            minimum=1,
        ),
    )
