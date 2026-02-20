from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

LLMMode = Literal["mock", "modelscope", "auto"]


@dataclass(frozen=True)
class Settings:
    app_name: str
    llm_mode: LLMMode
    cors_origins: tuple[str, ...]
    db_path: str
    secret_key: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_mode = os.getenv("LLM_MODE", "auto").strip().lower()
    if raw_mode == "modelscope":
        llm_mode: LLMMode = "modelscope"
    elif raw_mode == "mock":
        llm_mode = "mock"
    else:
        llm_mode = "auto"

    return Settings(
        app_name="DecisionOS API",
        llm_mode=llm_mode,
        cors_origins=("http://localhost:3000", "http://127.0.0.1:3000"),
        db_path=os.getenv("DECISIONOS_DB_PATH", "./decisionos.db").strip() or "./decisionos.db",
        secret_key=(
            os.getenv("DECISIONOS_SECRET_KEY", "").strip()
            or "decisionos-dev-secret-change-me"
        ),
    )
