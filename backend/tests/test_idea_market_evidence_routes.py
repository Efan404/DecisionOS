from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import dataclass

from tests._test_env import ensure_required_seed_env


class MarketEvidenceApiTestCase(unittest.TestCase):
    """Tests for /ideas/{idea_id}/evidence/* endpoints."""

    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "evidence-api-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        os.environ["DECISIONOS_AUTH_DISABLED"] = "1"

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_idea(self, title: str) -> str:
        status, body = self.client.request_json(
            "POST",
            "/ideas",
            {"title": title, "idea_seed": "seed"},
        )
        self.assertEqual(status, 201)
        assert body is not None
        return body["id"]

    # ---- Competitors ----

    def test_list_competitors_empty(self) -> None:
        idea_id = self._create_idea("Empty competitors")
        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/evidence/competitors"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(body["data"], [])

    def test_list_competitors_with_data(self) -> None:
        idea_id = self._create_idea("With competitors")

        # Create a competitor, a snapshot, and link it to the idea
        from app.db.repo_competitors import CompetitorRepository
        from app.db.repo_market_signals import MarketSignalRepository

        comp_repo = CompetitorRepository()
        sig_repo = MarketSignalRepository()

        comp = comp_repo.create_competitor(
            workspace_id="default",
            name="Acme Corp",
            canonical_url="https://acme.example.com",
            category="analytics",
        )
        snap = comp_repo.create_snapshot(
            competitor_id=comp.id,
            summary_json={"key": "value"},
            quality_score=0.8,
        )
        link = sig_repo.link_idea_entity(
            idea_id=idea_id,
            entity_type="competitor",
            entity_id=comp.id,
            link_reason="auto-discovered",
            relevance_score=0.9,
        )

        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/evidence/competitors"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(len(body["data"]), 1)

        item = body["data"][0]
        self.assertEqual(item["competitor"]["id"], comp.id)
        self.assertEqual(item["competitor"]["name"], "Acme Corp")
        self.assertIsNotNone(item["latest_snapshot"])
        self.assertEqual(item["latest_snapshot"]["id"], snap.id)
        self.assertEqual(item["latest_snapshot"]["quality_score"], 0.8)
        self.assertEqual(item["link"]["id"], link.id)
        self.assertEqual(item["link"]["link_reason"], "auto-discovered")

    # ---- Signals ----

    def test_list_signals_empty(self) -> None:
        idea_id = self._create_idea("Empty signals")
        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/evidence/signals"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(body["data"], [])

    def test_list_signals_with_data(self) -> None:
        idea_id = self._create_idea("With signals")

        from app.db.repo_market_signals import MarketSignalRepository

        sig_repo = MarketSignalRepository()

        signal = sig_repo.create_signal(
            workspace_id="default",
            signal_type="market_news",
            title="Big News",
            summary="Something important happened",
            severity="medium",
        )
        sig_repo.link_idea_entity(
            idea_id=idea_id,
            entity_type="signal",
            entity_id=signal.id,
            link_reason="relevant-news",
            relevance_score=0.7,
        )

        status, body = self.client.request_json(
            "GET", f"/ideas/{idea_id}/evidence/signals"
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["id"], signal.id)
        self.assertEqual(body["data"][0]["title"], "Big News")

    # ---- Discover (placeholder) ----

    def test_discover_competitors_returns_triggered(self) -> None:
        idea_id = self._create_idea("Discover competitors")
        status, body = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/evidence/competitors/discover",
            {"search_query": "analytics tools"},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(body["status"], "discovery_triggered")

    # ---- Sync Insights (placeholder) ----

    def test_sync_insights_returns_triggered(self) -> None:
        idea_id = self._create_idea("Sync insights")
        status, body = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/evidence/insights/sync",
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["idea_id"], idea_id)
        self.assertEqual(body["status"], "sync_triggered")


# ---------------------------------------------------------------------------
# Minimal ASGI test client (same pattern as test_scope_api.py)
# ---------------------------------------------------------------------------
import asyncio


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
