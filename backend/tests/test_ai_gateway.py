from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.ai_gateway import _post_json


class _FakeResponse:
    def __init__(self, *, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self._chunks = list(chunks)
        self.headers = headers or {}
        self.read_calls = 0

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self, _size: int = -1) -> bytes:
        self.read_calls += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class PostJsonLimitTestCase(unittest.TestCase):
    def test_post_json_parses_small_response(self) -> None:
        response = _FakeResponse(
            chunks=[b'{"ok":true}'],
            headers={"Content-Length": "11"},
        )
        with patch("app.core.ai_gateway.request.urlopen", return_value=response):
            result = _post_json(
                url="http://localhost/test",
                body={"ping": "pong"},
                timeout_seconds=1,
                api_key=None,
            )

        self.assertEqual(result, {"ok": True})

    def test_post_json_fails_fast_when_content_length_exceeds_limit(self) -> None:
        response = _FakeResponse(
            chunks=[b'{"ok":true}'],
            headers={"Content-Length": "12"},
        )
        with patch("app.core.ai_gateway._POST_JSON_MAX_RESPONSE_BYTES", 11):
            with patch("app.core.ai_gateway.request.urlopen", return_value=response):
                with self.assertRaises(RuntimeError) as context:
                    _post_json(
                        url="http://localhost/test",
                        body={"ping": "pong"},
                        timeout_seconds=1,
                        api_key=None,
                    )

        self.assertIn("Content-Length", str(context.exception))
        self.assertEqual(response.read_calls, 0)

    def test_post_json_fails_when_chunked_body_exceeds_limit(self) -> None:
        response = _FakeResponse(
            chunks=[b"12345", b"67890", b"x"],
            headers={},
        )
        with patch("app.core.ai_gateway._POST_JSON_MAX_RESPONSE_BYTES", 10):
            with patch("app.core.ai_gateway.request.urlopen", return_value=response):
                with self.assertRaises(RuntimeError) as context:
                    _post_json(
                        url="http://localhost/test",
                        body={"ping": "pong"},
                        timeout_seconds=1,
                        api_key=None,
                    )

        self.assertIn("exceeds", str(context.exception))


if __name__ == "__main__":
    unittest.main()
