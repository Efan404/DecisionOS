from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import dataclass


class ScopeApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "scope-api-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_idea(self, title: str) -> tuple[str, int]:
        status, body = self.client.request_json(
            "POST",
            "/ideas",
            {"title": title, "idea_seed": "seed"},
        )
        self.assertEqual(status, 201)
        assert body is not None
        return body["id"], body["version"]

    def test_get_draft_404_when_absent(self) -> None:
        idea_id, _ = self._create_idea("Scope Draft Missing")
        status, body = self.client.request_json("GET", f"/ideas/{idea_id}/scope/draft")
        self.assertEqual(status, 404)
        assert body is not None
        self.assertEqual(body["detail"]["code"], "SCOPE_DRAFT_NOT_FOUND")

    def test_bootstrap_returns_draft(self) -> None:
        idea_id, version = self._create_idea("Scope Bootstrap")
        status, body = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {"version": version},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(body["idea_version"], version + 1)
        self.assertEqual(body["data"]["status"], "draft")
        self.assertEqual(body["data"]["version"], 1)

    def test_patch_draft_requires_version_and_returns_new_idea_version(self) -> None:
        idea_id, version = self._create_idea("Scope Patch")
        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {"version": version},
        )
        self.assertEqual(bootstrap_status, 200)
        assert bootstrap is not None

        missing_version_status, _ = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}/scope/draft",
            {"items": [{"lane": "in", "content": "Missing version"}]},
        )
        self.assertEqual(missing_version_status, 422)

        patch_status, patched = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}/scope/draft",
            {
                "version": bootstrap["idea_version"],
                "items": [
                    {"lane": "in", "content": "In Scope A"},
                    {"lane": "out", "content": "Out Scope A"},
                ],
            },
        )
        self.assertEqual(patch_status, 200)
        assert patched is not None
        self.assertEqual(patched["idea_version"], bootstrap["idea_version"] + 1)
        self.assertEqual(
            [(item["lane"], item["content"]) for item in patched["data"]["items"]],
            [("in", "In Scope A"), ("out", "Out Scope A")],
        )

    def test_freeze_returns_frozen_baseline_and_marks_context(self) -> None:
        idea_id, version = self._create_idea("Scope Freeze")
        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {"version": version},
        )
        self.assertEqual(bootstrap_status, 200)
        assert bootstrap is not None

        freeze_status, frozen = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/freeze",
            {"version": bootstrap["idea_version"]},
        )
        self.assertEqual(freeze_status, 200)
        assert frozen is not None
        self.assertEqual(frozen["data"]["status"], "frozen")
        self.assertEqual(frozen["data"]["version"], 1)
        self.assertIsNotNone(frozen["data"]["frozen_at"])

        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None
        self.assertEqual(detail["context"]["current_scope_baseline_id"], frozen["data"]["id"])
        self.assertEqual(detail["context"]["current_scope_baseline_version"], 1)

    def test_new_version_clones_latest_frozen(self) -> None:
        idea_id, version = self._create_idea("Scope New Version")
        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {"version": version},
        )
        self.assertEqual(bootstrap_status, 200)
        assert bootstrap is not None

        patch_status, patched = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}/scope/draft",
            {
                "version": bootstrap["idea_version"],
                "items": [{"lane": "in", "content": "Clone me"}],
            },
        )
        self.assertEqual(patch_status, 200)
        assert patched is not None

        freeze_status, frozen = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/freeze",
            {"version": patched["idea_version"]},
        )
        self.assertEqual(freeze_status, 200)
        assert frozen is not None

        new_status, new_version = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/new-version",
            {"version": frozen["idea_version"]},
        )
        self.assertEqual(new_status, 200)
        assert new_version is not None
        self.assertEqual(new_version["data"]["status"], "draft")
        self.assertEqual(new_version["data"]["version"], 2)
        self.assertEqual(new_version["data"]["source_baseline_id"], frozen["data"]["id"])
        self.assertEqual(
            [(item["lane"], item["content"]) for item in new_version["data"]["items"]],
            [("in", "Clone me")],
        )

    def test_get_baseline_validates_idea_ownership(self) -> None:
        owner_idea_id, version = self._create_idea("Scope Baseline Owner")
        other_idea_id, _ = self._create_idea("Scope Baseline Stranger")
        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{owner_idea_id}/scope/draft/bootstrap",
            {"version": version},
        )
        self.assertEqual(bootstrap_status, 200)
        assert bootstrap is not None

        freeze_status, frozen = self.client.request_json(
            "POST",
            f"/ideas/{owner_idea_id}/scope/freeze",
            {"version": bootstrap["idea_version"]},
        )
        self.assertEqual(freeze_status, 200)
        assert frozen is not None
        baseline_id = frozen["data"]["id"]

        ok_status, ok_body = self.client.request_json(
            "GET",
            f"/ideas/{owner_idea_id}/scope/baselines/{baseline_id}",
        )
        self.assertEqual(ok_status, 200)
        assert ok_body is not None
        self.assertEqual(ok_body["id"], baseline_id)

        bad_status, bad_body = self.client.request_json(
            "GET",
            f"/ideas/{other_idea_id}/scope/baselines/{baseline_id}",
        )
        self.assertEqual(bad_status, 404)
        assert bad_body is not None
        self.assertEqual(bad_body["detail"]["code"], "SCOPE_BASELINE_NOT_FOUND")


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
    ) -> tuple[int, dict[str, object] | list[object] | None]:
        response = self.request_raw(method, path, payload)
        if not response.body:
            return response.status_code, None
        return response.status_code, json.loads(response.body.decode("utf-8"))

    def request_raw(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> _RawResponse:
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        return asyncio.run(
            _run_asgi_request(app=self._app, method=method, path=path, body=body)
        )


async def _run_asgi_request(
    *,
    app: object,
    method: str,
    path: str,
    body: bytes,
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
        "headers": [(b"content-type", b"application/json")],
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
