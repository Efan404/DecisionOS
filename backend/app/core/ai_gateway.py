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
# Tracks (provider_id, model) pairs that don't support json_schema response_format.
# Populated at runtime on first 400 failure; reset on process restart.
_json_schema_unsupported: set[tuple[str, str]] = set()

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
    max_retries: int = 2,
) -> SchemaT:
    provider = _get_active_provider()
    logger.info(
        "generate_structured task=%s provider=%s model=%s prompt_chars=%d",
        task, provider.id, provider.model, len(user_prompt),
    )
    response_schema = schema_model.model_json_schema()
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
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
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "generate_structured task=%s provider=%s attempt=%d/%d FAILED (retrying): %s",
                    task, provider.id, attempt, max_retries, exc,
                )
                time.sleep(1)
            else:
                logger.error(
                    "generate_structured task=%s provider=%s attempt=%d/%d FAILED: %s",
                    task, provider.id, attempt, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


def generate_text(*, task: TaskName, user_prompt: str, max_retries: int = 2) -> str:
    """Call provider and return raw text content (no schema enforcement)."""
    provider = _get_active_provider()
    logger.info("generate_text task=%s provider=%s model=%s", task, provider.id, provider.model)
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            result = _invoke_provider_text(provider=provider, user_prompt=user_prompt)
            logger.info("generate_text task=%s provider=%s SUCCESS len=%d", task, provider.id, len(result))
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "generate_text task=%s provider=%s attempt=%d/%d FAILED (retrying): %s",
                    task, provider.id, attempt, max_retries, exc,
                )
                time.sleep(1)
            else:
                logger.error(
                    "generate_text task=%s provider=%s attempt=%d/%d FAILED: %s",
                    task, provider.id, attempt, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


def _invoke_provider_text(*, provider: AIProviderConfig, user_prompt: str) -> str:
    """Invoke provider and return plain text response content."""
    if provider.kind == "anthropic":
        endpoint = provider.base_url.rstrip("/")
        if not endpoint.endswith("/v1/messages"):
            endpoint = f"{endpoint}/v1/messages"
        body: dict[str, object] = {
            "model": provider.model or "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": provider.temperature,
        }
        logger.debug("_invoke_provider_text url=%s model=%s (anthropic)", endpoint, body["model"])
        decoded = _post_json(
            url=endpoint, body=body, timeout_seconds=provider.timeout_seconds,
            api_key=provider.api_key, auth_header="x-api-key",
        )
        return _extract_content_from_anthropic(decoded)

    # openai_compatible (default)
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    body = {
        "model": provider.model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": provider.temperature,
        "enable_thinking": False,
    }
    logger.debug("_invoke_provider_text url=%s model=%s", endpoint, body["model"])
    decoded = _post_json(
        url=endpoint, body=body, timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    return _extract_content_from_choices(decoded)


def test_provider_connection(provider: AIProviderConfig) -> tuple[bool, int, str]:
    started = time.perf_counter()
    logger.info("test_provider_connection provider=%s kind=%s", provider.id, provider.kind)
    try:
        if provider.kind == "openai_compatible":
            _probe_openai_compatible(provider)
        elif provider.kind == "anthropic":
            _probe_anthropic(provider)
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
    if provider.kind == "openai_compatible":
        return _call_openai_compatible_provider(
            provider=provider,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )

    if provider.kind == "anthropic":
        return _call_anthropic_provider(
            provider=provider,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )

    raise RuntimeError(f"Unsupported provider kind: {provider.kind}")


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
        text = "\n".join(inner).strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first JSON object from the text (handles LLMs
    # that emit prose before/after the JSON block).
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return cast(dict[str, object], parsed)
                    except json.JSONDecodeError:
                        pass
                    break

    raise RuntimeError(f"Provider response content is not valid JSON: {text[:300]}")


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

    # Use json_object mode with structured prompt - more reliable for ModelScope
    schema_str = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
    structured_prompt = (
        f"{user_prompt}\n\n"
        "IMPORTANT: Your response MUST be a valid JSON object only — "
        "no markdown, no code fences, no explanations, no text before or after the JSON.\n\n"
        f"JSON Schema (follow this exact structure): {schema_str}\n\n"
        "For array fields (like 'in_scope', 'out_scope'), each item MUST be an object with the exact fields "
        "defined in the schema. "
        "For 'in_scope' items: id (string/UUID), title (string), desc (string), priority (MUST be exactly 'P0', 'P1', or 'P2' - NOT 'high'/'medium'/'low'). "
        "For 'out_scope' items: id (string/UUID), title (string), desc (string), reason (string). "
        "Example: {\"in_scope\": [{\"id\": \"1\", \"title\": \"feature\", \"desc\": \"description\", \"priority\": \"P0\"}], \"out_scope\": []}"
    )
    body: dict[str, object] = {
        "model": model,
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\nIMPORTANT: Always respond with valid JSON matching the requested schema."},
            {"role": "user", "content": structured_prompt},
        ],
        "temperature": provider.temperature,
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
    }
    logger.debug("_call_openai_compatible_provider url=%s model=%s (json_object)", endpoint, model)
    decoded = _post_json(
        url=endpoint,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    content = _extract_content_from_choices(decoded)
    return _parse_json_from_content(content)


def _probe_anthropic(provider: AIProviderConfig) -> None:
    """Probe Anthropic Messages API by sending a trivial request."""
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/v1/messages"):
        endpoint = f"{endpoint}/v1/messages"
    body: dict[str, object] = {
        "model": provider.model or "claude-sonnet-4-20250514",
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "Say ok."}],
    }
    _post_json(
        url=endpoint,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
        auth_header="x-api-key",
    )


def _call_anthropic_provider(
    *,
    provider: AIProviderConfig,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    """Call Anthropic Messages API and return parsed JSON."""
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/v1/messages"):
        endpoint = f"{endpoint}/v1/messages"

    model = provider.model or "claude-sonnet-4-20250514"
    schema_str = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
    structured_prompt = (
        f"{user_prompt}\n\n"
        "IMPORTANT: Your response MUST be a valid JSON object only — "
        "no markdown, no code fences, no explanations, no text before or after the JSON.\n\n"
        f"JSON Schema (follow this exact structure): {schema_str}"
    )
    body: dict[str, object] = {
        "model": model,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT + "\n\nIMPORTANT: Always respond with valid JSON matching the requested schema.",
        "messages": [{"role": "user", "content": structured_prompt}],
        "temperature": provider.temperature,
    }
    logger.debug("_call_anthropic_provider url=%s model=%s", endpoint, model)
    decoded = _post_json(
        url=endpoint,
        body=body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
        auth_header="x-api-key",
    )
    content = _extract_content_from_anthropic(decoded)
    return _parse_json_from_content(content)


def _extract_content_from_anthropic(decoded: object) -> str:
    """Extract text content from Anthropic Messages API response."""
    if not isinstance(decoded, dict):
        raise RuntimeError("Anthropic response is not an object")
    content_blocks = decoded.get("content")
    if not isinstance(content_blocks, list) or not content_blocks:
        raise RuntimeError("Anthropic response missing content blocks")
    text_parts: list[str] = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
    if not text_parts:
        raise RuntimeError("Anthropic response has no text content")
    return "\n".join(text_parts)


def _post_json(
    *,
    url: str,
    body: dict[str, object],
    timeout_seconds: float,
    api_key: str | None,
    auth_header: str = "Authorization",
) -> object:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        if auth_header == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
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
