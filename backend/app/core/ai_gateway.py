from __future__ import annotations

import json
import time
from typing import TypeVar, cast
from urllib import request

from pydantic import BaseModel

from app.core.prompts import SYSTEM_PROMPT
from app.db.repo_ai import AISettingsRepository
from app.schemas.ai_settings import AIProviderConfig, ProviderKind, TaskName

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_settings_repo = AISettingsRepository()


def generate_structured(
    *,
    task: TaskName,
    user_prompt: str,
    schema_model: type[SchemaT],
) -> SchemaT:
    settings = _settings_repo.get_settings().config
    enabled_providers = [provider for provider in settings.providers if provider.enabled]
    provider_map = {provider.id: provider for provider in enabled_providers}
    ordered_provider_ids = getattr(settings.routing, task)
    if ordered_provider_ids:
        providers = [
            provider_map[provider_id]
            for provider_id in ordered_provider_ids
            if provider_id in provider_map
        ]
    else:
        providers = enabled_providers

    if not providers:
        raise RuntimeError(f"No enabled providers configured for task: {task}")

    response_schema = schema_model.model_json_schema()
    errors: list[str] = []
    for provider in providers:
        try:
            raw = _invoke_provider(
                provider=provider,
                task=task,
                user_prompt=user_prompt,
                response_schema=response_schema,
            )
            return schema_model.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider.id}: {exc}")

    raise RuntimeError(f"All providers failed for task {task}: {' | '.join(errors)}")


def test_provider_connection(provider: AIProviderConfig) -> tuple[bool, int, str]:
    started = time.perf_counter()
    try:
        if provider.kind == "generic_json":
            _probe_generic_json(provider)
        elif provider.kind == "openai_compatible":
            _probe_openai_compatible(provider)
        else:
            raise RuntimeError(f"Unsupported provider kind: {provider.kind}")
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, elapsed_ms, str(exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return True, elapsed_ms, "Connection successful"


def _invoke_provider(
    *,
    provider: AIProviderConfig,
    task: TaskName,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    if provider.kind == "generic_json":
        return _call_generic_json_provider(
            provider=provider,
            task=task,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )

    if provider.kind == "openai_compatible":
        return _call_openai_compatible_provider(
            provider=provider,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )

    raise RuntimeError(f"Unsupported provider kind: {provider.kind}")


def _probe_generic_json(provider: AIProviderConfig) -> None:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": True,
    }
    _call_generic_json_provider(
        provider=provider,
        task="opportunity",
        user_prompt="Return JSON with {'ok': true}.",
        response_schema=schema,
    )


def _probe_openai_compatible(provider: AIProviderConfig) -> None:
    endpoint = provider.base_url.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    models_url = f"{endpoint}/models"

    headers: dict[str, str] = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    req = request.Request(models_url, headers=headers, method="GET")
    with request.urlopen(req, timeout=provider.timeout_seconds) as response:
        raw = response.read().decode("utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("Unexpected /models response shape")


def _call_generic_json_provider(
    *,
    provider: AIProviderConfig,
    task: TaskName,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    body: dict[str, object] = {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "response_schema": response_schema,
        "model": provider.model,
        "temperature": provider.temperature,
        "task": task,
    }
    decoded = _post_json(
        url=provider.base_url,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    if isinstance(decoded, dict) and "data" in decoded and isinstance(decoded["data"], dict):
        return cast(dict[str, object], decoded["data"])
    return cast(dict[str, object], decoded)


def _call_openai_compatible_provider(
    *,
    provider: AIProviderConfig,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    body: dict[str, object] = {
        "model": provider.model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": provider.temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "decisionos_response",
                "schema": response_schema,
            },
        },
    }
    decoded = _post_json(
        url=endpoint,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )

    if not isinstance(decoded, dict):
        raise RuntimeError("Provider response is not an object")

    choices = decoded.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Provider response missing choices")

    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("Provider response has invalid first choice")

    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Provider response missing message object")

    content = message.get("content")
    if isinstance(content, dict):
        return cast(dict[str, object], content)
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        content = "\n".join(text_parts)

    if not isinstance(content, str):
        raise RuntimeError("Provider response content is not JSON text")

    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("Provider response content is not a JSON object")
    return cast(dict[str, object], parsed)


def _post_json(
    *,
    url: str,
    body: dict[str, object],
    timeout_seconds: float,
    api_key: str | None,
) -> object:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)
