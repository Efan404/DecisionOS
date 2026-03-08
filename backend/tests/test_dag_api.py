from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from unittest.mock import patch
from urllib.parse import urlsplit

from tests._test_env import ensure_required_seed_env


_MOCK_EXPAND_NODES = [
    {"content": "Child node A", "edge_label": "方向A"},
    {"content": "Child node B", "edge_label": "方向B"},
]

_MOCK_PATH_SUMMARY = "Mock path summary for testing."


class DagApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        os.environ["DECISIONOS_AUTH_DISABLED"] = "1"

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

        # Patch LLM calls so tests don't require a real AI provider
        self._patch_expand_user = patch(
            "app.core.llm.generate_expand_node_user",
            return_value=_MOCK_EXPAND_NODES,
        )
        self._patch_expand_nodes = patch(
            "app.core.llm.generate_expand_nodes",
            return_value=_MOCK_EXPAND_NODES,
        )
        self._patch_path_summary = patch(
            "app.core.llm.generate_path_summary",
            return_value=_MOCK_PATH_SUMMARY,
        )
        self._patch_expand_user.start()
        self._patch_expand_nodes.start()
        self._patch_path_summary.start()

    def tearDown(self) -> None:
        self._patch_expand_user.stop()
        self._patch_expand_nodes.stop()
        self._patch_path_summary.stop()
        self._tmpdir.cleanup()

    def _create_idea(self) -> str:
        status, body = self.client.request_json(
            "POST", "/ideas", {"title": "Test", "idea_seed": "seed"}
        )
        self.assertEqual(status, 201)
        assert body is not None
        return body["id"]

    def test_create_root_node(self) -> None:
        idea_id = self._create_idea()
        status, body = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root idea"}
        )
        self.assertEqual(status, 201)
        assert body is not None
        self.assertEqual(body["depth"], 0)
        self.assertIsNone(body["parent_id"])
        self.assertEqual(body["content"], "root idea")

    def test_list_nodes_empty(self) -> None:
        idea_id = self._create_idea()
        status, body = self.client.request_json("GET", f"/ideas/{idea_id}/nodes")
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body, [])

    def test_list_nodes_after_create(self) -> None:
        idea_id = self._create_idea()
        self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        status, body = self.client.request_json("GET", f"/ideas/{idea_id}/nodes")
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(len(body), 1)

    def test_get_single_node(self) -> None:
        idea_id = self._create_idea()
        _, created = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert created is not None
        node_id = created["id"]

        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/nodes/{node_id}"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["id"], node_id)

    def test_user_expand(self) -> None:
        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        status, body = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/nodes/{root['id']}/expand/user",
            {"description": "make it for B2B"},
        )
        self.assertEqual(status, 201)
        assert body is not None
        self.assertIsInstance(body, list)
        self.assertGreaterEqual(len(body), 1)
        self.assertEqual(body[0]["depth"], 1)
        self.assertEqual(body[0]["parent_id"], root["id"])

    def test_confirm_path(self) -> None:
        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        status, body = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/paths",
            {"node_chain": [root["id"]]},
        )
        self.assertEqual(status, 201)
        assert body is not None
        self.assertIn("path_md", body)
        self.assertIn("path_json", body)

        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None
        context = detail["context"]
        self.assertEqual(context["confirmed_dag_path_id"], body["id"])
        self.assertEqual(context["confirmed_dag_node_id"], root["id"])
        self.assertEqual(context["confirmed_dag_node_content"], root["content"])
        self.assertIn("confirmed_dag_path_summary", context)

    def test_confirm_path_update_conflict_returns_409(self) -> None:
        from app.db.repo_ideas import UpdateIdeaResult
        from app.db import repo_dag

        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        with patch(
            "app.routes.idea_dag._repo.apply_agent_update",
            return_value=UpdateIdeaResult(kind="conflict"),
        ):
            status, body = self.client.request_json(
                "POST",
                f"/ideas/{idea_id}/paths",
                {"node_chain": [root["id"]]},
            )
        self.assertEqual(status, 409)
        assert body is not None
        self.assertEqual(body["detail"]["code"], "IDEA_VERSION_CONFLICT")
        self.assertIsNone(repo_dag.get_latest_path(idea_id))

    def test_confirm_path_update_archived_returns_409(self) -> None:
        from app.db.repo_ideas import UpdateIdeaResult
        from app.db import repo_dag

        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        with patch(
            "app.routes.idea_dag._repo.apply_agent_update",
            return_value=UpdateIdeaResult(kind="archived"),
        ):
            status, body = self.client.request_json(
                "POST",
                f"/ideas/{idea_id}/paths",
                {"node_chain": [root["id"]]},
            )
        self.assertEqual(status, 409)
        assert body is not None
        self.assertEqual(body["detail"]["code"], "IDEA_ARCHIVED")
        self.assertIsNone(repo_dag.get_latest_path(idea_id))

    def test_confirm_path_update_not_found_returns_404(self) -> None:
        from app.db.repo_ideas import UpdateIdeaResult

        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        with patch(
            "app.routes.idea_dag._repo.apply_agent_update",
            return_value=UpdateIdeaResult(kind="not_found"),
        ):
            status, body = self.client.request_json(
                "POST",
                f"/ideas/{idea_id}/paths",
                {"node_chain": [root["id"]]},
            )
        self.assertEqual(status, 404)
        assert body is not None
        self.assertEqual(body["detail"]["code"], "IDEA_NOT_FOUND")

    def test_get_latest_path_404_when_none(self) -> None:
        idea_id = self._create_idea()
        status, _ = self.client.request_json(
            "GET", f"/ideas/{idea_id}/paths/latest"
        )
        self.assertEqual(status, 404)

    def test_get_latest_path_after_confirm(self) -> None:
        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/paths",
            {"node_chain": [root["id"]]},
        )

        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/paths/latest"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertIn("path_md", body)

    def test_node_not_found(self) -> None:
        idea_id = self._create_idea()
        status, _ = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/nodes/nonexistent/expand/user",
            {"description": "test"},
        )
        self.assertEqual(status, 404)

    def test_idea_not_found_for_nodes(self) -> None:
        status, _ = self.client.request_json("GET", "/ideas/nonexistent/nodes")
        self.assertEqual(status, 404)

    def test_expand_stream_exception_is_sanitized_and_logged(self) -> None:
        idea_id = self._create_idea()
        _, root = self.client.request_json(
            "POST", f"/ideas/{idea_id}/nodes", {"content": "root"}
        )
        assert root is not None

        leaked_message = "provider secret leaked"
        with patch(
            "app.routes.idea_dag.llm.generate_expand_nodes",
            side_effect=RuntimeError(leaked_message),
        ), patch("app.routes.idea_dag.logger.exception") as mock_log_exception:
            response = self.client.request_raw(
                "POST",
                f"/ideas/{idea_id}/nodes/{root['id']}/expand/stream?pattern_id=narrow_users",
            )

        self.assertEqual(response.status_code, 200)
        raw = response.body.decode("utf-8")
        self.assertNotIn(leaked_message, raw)
        self.assertIn("event: error", raw)

        error_payload: dict[str, object] | None = None
        for chunk in raw.split("\n\n"):
            if "event: error" not in chunk:
                continue
            data_line = next(
                (line for line in chunk.splitlines() if line.startswith("data: ")),
                None,
            )
            if data_line is None:
                continue
            error_payload = json.loads(data_line[len("data: ") :])
            break

        self.assertIsNotNone(error_payload)
        assert error_payload is not None
        self.assertEqual(error_payload["code"], "EXPAND_FAILED")
        self.assertEqual(error_payload["message"], "Failed to expand node")
        mock_log_exception.assert_called_once()


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
    split = urlsplit(path)
    scope_path = split.path or path
    query_string = split.query.encode("utf-8")

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
        "path": scope_path,
        "raw_path": scope_path.encode("ascii"),
        "query_string": query_string,
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
