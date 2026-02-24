from __future__ import annotations

import json
import logging
import time
from typing import TypeVar, cast
from urllib import request

from pydantic import BaseModel

from app.core.prompts import SYSTEM_PROMPT
from app.db.repo_ai import AISettingsRepository
from app.schemas.ai_settings import AIProviderConfig, TaskName

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_settings_repo = AISettingsRepository()
logger = logging.getLogger(__name__)

# Keep provider payloads bounded to avoid untrusted large responses consuming memory.
_POST_JSON_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_POST_JSON_READ_CHUNK_BYTES = 64 * 1024


def _get_active_provider() -> AIProviderConfig:
    """Return the single enabled provider, or raise if none configured."""
    settings = _settings_repo.get_settings().config
    enabled = [p for p in settings.providers if p.enabled]
    if not enabled:
        raise RuntimeError(
            "No AI provider configured. Please go to Settings → AI Provider to add and enable one."
        )
    return enabled[0]


def generate_structured(
    *,
    task: TaskName,
    user_prompt: str,
    schema_model: type[SchemaT],
) -> SchemaT:
    provider = _get_active_provider()
    logger.info(
        "generate_structured task=%s provider=%s model=%s prompt_chars=%d",
        task, provider.id, provider.model, len(user_prompt),
    )
    response_schema = schema_model.model_json_schema()
    try:
        raw = _invoke_provider(
            provider=provider,
            task=task,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )
        result = schema_model.model_validate(raw)
        logger.info("generate_structured task=%s provider=%s SUCCESS", task, provider.id)
        return result
    except Exception as exc:
        logger.error("generate_structured task=%s provider=%s FAILED: %s", task, provider.id, exc)
        raise


def generate_text(*, task: TaskName, user_prompt: str) -> str:
    """Call provider and return raw text content (no schema enforcement)."""
    provider = _get_active_provider()
    logger.info("generate_text task=%s provider=%s model=%s", task, provider.id, provider.model)
    try:
        result = _invoke_provider_text(provider=provider, user_prompt=user_prompt)
        logger.info("generate_text task=%s provider=%s SUCCESS len=%d", task, provider.id, len(result))
        return result
    except Exception as exc:
        logger.error("generate_text task=%s provider=%s FAILED: %s", task, provider.id, exc)
        raise


def _invoke_provider_text(*, provider: AIProviderConfig, user_prompt: str) -> str:
    """Invoke provider and return plain text response content."""
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
        "include_reasoning": False,
    }
    logger.debug("_invoke_provider_text url=%s model=%s", endpoint, body["model"])
    decoded = _post_json(
        url=endpoint,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    return _extract_content_from_choices(decoded)


def test_provider_connection(provider: AIProviderConfig) -> tuple[bool, int, str]:
    started = time.perf_counter()
    logger.info("test_provider_connection provider=%s kind=%s", provider.id, provider.kind)
    try:
        if provider.kind == "generic_json":
            _probe_generic_json(provider)
        elif provider.kind == "openai_compatible":
            _probe_openai_compatible(provider)
        else:
            raise RuntimeError(f"Unsupported provider kind: {provider.kind}")
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "test_provider_connection provider=%s FAILED %dms: %s", provider.id, elapsed_ms, exc
        )
        return False, elapsed_ms, str(exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("test_provider_connection provider=%s OK %dms", provider.id, elapsed_ms)
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

    logger.debug("_probe_openai_compatible url=%s", models_url)
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
    logger.debug(
        "_call_generic_json_provider url=%s task=%s model=%s", provider.base_url, task, provider.model
    )
    decoded = _post_json(
        url=provider.base_url,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    if isinstance(decoded, dict) and "data" in decoded and isinstance(decoded["data"], dict):
        return cast(dict[str, object], decoded["data"])
    return cast(dict[str, object], decoded)


def _extract_content_from_choices(decoded: object) -> str:
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
        return json.dumps(content)
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        content = "\n".join(text_parts)
    if not isinstance(content, str):
        raise RuntimeError("Provider response content is not JSON text")
    return content


def _parse_json_from_content(content: str) -> dict[str, object]:
    text = content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("Provider response content is not a JSON object")
    return cast(dict[str, object], parsed)


def _call_openai_compatible_provider(
    *,
    provider: AIProviderConfig,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    model = provider.model or "gpt-4o-mini"

    # First attempt: use json_schema structured output (supported by GPT-4o etc.)
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": provider.temperature,
        "include_reasoning": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "decisionos_response",
                "schema": response_schema,
            },
        },
    }
    logger.debug("_call_openai_compatible_provider url=%s model=%s (json_schema)", endpoint, model)
    try:
        decoded = _post_json(
            url=endpoint,
            body=body,
            timeout_seconds=provider.timeout_seconds,
            api_key=provider.api_key,
        )
        content = _extract_content_from_choices(decoded)
        return _parse_json_from_content(content)
    except Exception as exc:
        logger.warning(
            "_call_openai_compatible_provider json_schema failed (%s), retrying with plain prompt", exc
        )

    # Fallback: plain prompt asking for JSON (for models that don't support response_format)
    # Include schema to guide field names, but keep it compact
    schema_str = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
    fallback_prompt = (
        f"{user_prompt}\n\n"
        "IMPORTANT: Your response MUST be a single valid JSON object only — "
        "no markdown, no code fences, no explanations, no text before or after the JSON. "
        f"Use exactly these field names as defined in this JSON Schema: {schema_str}"
    )
    fallback_body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": fallback_prompt},
        ],
        "temperature": provider.temperature,
        "include_reasoning": False,
    }
    logger.debug("_call_openai_compatible_provider url=%s model=%s (plain prompt fallback)", endpoint, model)
    decoded = _post_json(
        url=endpoint,
        body=fallback_body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    content = _extract_content_from_choices(decoded)
    return _parse_json_from_content(content)


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
        content_length_header = response.headers.get("Content-Length")
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
            except ValueError:
                content_length = None
            if content_length is not None and content_length > _POST_JSON_MAX_RESPONSE_BYTES:
                raise RuntimeError(
                    "Provider response Content-Length "
                    f"{content_length} exceeds limit {_POST_JSON_MAX_RESPONSE_BYTES} bytes"
                )

        buffer = bytearray()
        while True:
            chunk = response.read(_POST_JSON_READ_CHUNK_BYTES)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > _POST_JSON_MAX_RESPONSE_BYTES:
                raise RuntimeError(
                    "Provider response body exceeds limit "
                    f"{_POST_JSON_MAX_RESPONSE_BYTES} bytes"
                )

        raw = buffer.decode("utf-8")
    return json.loads(raw)
