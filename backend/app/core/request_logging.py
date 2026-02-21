from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar, Token

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
_logger = logging.getLogger("app.request")


def get_request_id() -> str:
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> Token[str]:
    return _request_id_ctx.set(request_id)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        token = set_request_id(request_id)

        method = str(scope.get("method", "UNKNOWN"))
        path = str(scope.get("path", ""))
        started_at = time.perf_counter()
        status_code: int | None = None
        failed = False

        _logger.info("http.request.start method=%s path=%s", method, path)

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                raw_headers = list(message.get("headers", []))
                raw_headers.append((REQUEST_ID_HEADER.encode("ascii"), request_id.encode("ascii")))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        except Exception:
            failed = True
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            _logger.exception(
                "http.request.failed method=%s path=%s duration_ms=%s",
                method,
                path,
                duration_ms,
            )
            raise
        finally:
            if not failed:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                if status_code is None:
                    _logger.info(
                        "http.request.done method=%s path=%s duration_ms=%s",
                        method,
                        path,
                        duration_ms,
                    )
                else:
                    _logger.info(
                        "http.request.done method=%s path=%s status_code=%s duration_ms=%s",
                        method,
                        path,
                        status_code,
                        duration_ms,
                    )
            _request_id_ctx.reset(token)


def _resolve_request_id(scope: Scope) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != REQUEST_ID_HEADER.encode("ascii"):
            continue
        incoming = raw_value.decode("ascii", errors="ignore").strip()
        if incoming:
            return incoming
        break
    return uuid.uuid4().hex
