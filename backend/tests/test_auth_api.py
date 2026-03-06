from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import dataclass

from tests._test_env import ensure_required_seed_env


class AuthApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "auth-api-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        os.environ["DECISIONOS_AUTH_DISABLED"] = "0"

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

    def tearDown(self) -> None:
        self._tmpdir.cleanup()


    def test_login_invalid_password_returns_401(self) -> None:
        status, payload = self.client.request_json(
            "POST",
            "/auth/login",
            {"username": "admin", "password": "wrong-password"},
        )
        self.assertEqual(status, 401)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "AUTH_INVALID_CREDENTIALS")

    def test_login_rate_limited_returns_429(self) -> None:
        from app.core.settings import get_settings
        from app.main import create_app

        old_limit = os.environ.get("DECISIONOS_RATE_LIMIT_LOGIN_MAX_REQUESTS")
        old_window = os.environ.get("DECISIONOS_RATE_LIMIT_LOGIN_WINDOW_SECONDS")
        os.environ["DECISIONOS_RATE_LIMIT_LOGIN_MAX_REQUESTS"] = "2"
        os.environ["DECISIONOS_RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = "60"
        get_settings.cache_clear()
        rate_limited_client = _AsgiTestClient(create_app())
        try:
            for _ in range(2):
                status, payload = rate_limited_client.request_json(
                    "POST",
                    "/auth/login",
                    {"username": "admin", "password": "wrong-password"},
                )
                self.assertEqual(status, 401)
                assert payload is not None
                self.assertEqual(payload["detail"]["code"], "AUTH_INVALID_CREDENTIALS")

            status, payload = rate_limited_client.request_json(
                "POST",
                "/auth/login",
                {"username": "admin", "password": "wrong-password"},
            )
            self.assertEqual(status, 429)
            assert payload is not None
            self.assertEqual(payload["detail"]["code"], "RATE_LIMITED")
        finally:
            if old_limit is None:
                os.environ.pop("DECISIONOS_RATE_LIMIT_LOGIN_MAX_REQUESTS", None)
            else:
                os.environ["DECISIONOS_RATE_LIMIT_LOGIN_MAX_REQUESTS"] = old_limit

            if old_window is None:
                os.environ.pop("DECISIONOS_RATE_LIMIT_LOGIN_WINDOW_SECONDS", None)
            else:
                os.environ["DECISIONOS_RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = old_window
            get_settings.cache_clear()

    def test_protected_route_requires_auth(self) -> None:
        status, payload = self.client.request_json("GET", "/ideas")
        self.assertEqual(status, 401)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "AUTH_UNAUTHORIZED")

    def test_protected_route_allows_bearer_token(self) -> None:
        login_status, login_payload = self.client.request_json(
            "POST",
            "/auth/login",
            {"username": "test", "password": "test"},
        )
        self.assertEqual(login_status, 200)
        assert login_payload is not None
        token = login_payload["access_token"]

        status, payload = self.client.request_json(
            "GET",
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(status, 200)
        assert payload is not None
        self.assertIn("items", payload)


@dataclass(frozen=True)
class _RawResponse:
    status_code: int
    body: bytes


class _AsgiTestClient:
    def __init__(self, app: object) -> None:
        self._app = app

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object] | list[object] | None]:
        response = self.request_raw(method, path, payload, headers=headers)
        if not response.body:
            return response.status_code, None
        return response.status_code, json.loads(response.body.decode("utf-8"))

    def request_raw(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _RawResponse:
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        return asyncio.run(
            _run_asgi_request(
                app=self._app,
                method=method,
                path=path,
                body=body,
                headers=headers or {},
            )
        )


async def _run_asgi_request(
    *,
    app: object,
    method: str,
    path: str,
    body: bytes,
    headers: dict[str, str],
) -> _RawResponse:
    request_sent = False
    response_started = False
    response_status = 500
    body_parts: list[bytes] = []
    hold_receive = asyncio.Event()

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await hold_receive.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        nonlocal response_started, response_status
        message_type = str(message.get("type"))
        if message_type == "http.response.start":
            response_started = True
            response_status = int(message.get("status", 500))
            return
        if message_type == "http.response.body":
            raw = message.get("body", b"")
            if isinstance(raw, bytes):
                body_parts.append(raw)
            elif isinstance(raw, str):
                body_parts.append(raw.encode("utf-8"))

    encoded_headers = [(b"content-type", b"application/json")]
    for key, value in headers.items():
        encoded_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": encoded_headers,
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "state": {},
    }

    await app(scope, receive, send)

    if not response_started:
        raise RuntimeError("ASGI response did not start")

    return _RawResponse(status_code=response_status, body=b"".join(body_parts))


if __name__ == "__main__":
    unittest.main()
