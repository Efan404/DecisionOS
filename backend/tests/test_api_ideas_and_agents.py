from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import dataclass


class IdeasAndAgentsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decisionos-api-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())
        self.idea_id, _ = self._create_idea("Delete Test Idea")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_idea(self, title: str) -> tuple[str, int]:
        created_status, created = self.client.request_json(
            "POST",
            "/ideas",
            {"title": title, "idea_seed": "seed"},
        )
        self.assertEqual(created_status, 201)
        assert created is not None
        return created["id"], created["version"]

    def _generate_opportunity(self, idea_id: str, version: int) -> dict[str, object]:
        status, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "version": version},
        )
        self.assertEqual(status, 200)
        assert payload is not None
        return payload

    def _generate_feasibility(
        self,
        idea_id: str,
        *,
        version: int,
        direction_id: str,
        direction_text: str,
        path_id: str = "pathA",
    ) -> dict[str, object]:
        status, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/feasibility",
            {
                "idea_seed": "seed",
                "direction_id": direction_id,
                "direction_text": direction_text,
                "path_id": path_id,
                "version": version,
            },
        )
        self.assertEqual(status, 200)
        assert payload is not None
        return payload

    def _generate_scope(
        self,
        idea_id: str,
        *,
        version: int,
        direction_id: str,
        direction_text: str,
        selected_plan_id: str,
        feasibility: dict[str, object],
        path_id: str = "pathA",
    ) -> tuple[int, dict[str, object] | None]:
        return self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/scope",
            {
                "idea_seed": "seed",
                "direction_id": direction_id,
                "direction_text": direction_text,
                "path_id": path_id,
                "selected_plan_id": selected_plan_id,
                "feasibility": feasibility,
                "version": version,
            },
        )

    def _generate_prd(
        self,
        idea_id: str,
        *,
        version: int,
        direction_text: str,
        selected_plan_id: str,
        scope: dict[str, object],
    ) -> tuple[int, dict[str, object] | None]:
        return self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/prd",
            {
                "idea_seed": "seed",
                "direction_text": direction_text,
                "selected_plan_id": selected_plan_id,
                "scope": scope,
                "version": version,
            },
        )

    def test_legacy_agents_route_reports_gone(self) -> None:
        status_code, payload = self.client.request_json(
            "POST",
            "/agents/opportunity",
            {"idea_seed": "seed"},
        )

        self.assertEqual(status_code, 410)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "LEGACY_AGENTS_ROUTE_GONE")

    def test_opportunity_count_defaults_to_three(self) -> None:
        idea_id, version = self._create_idea("Default Count Idea")
        status_code, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "version": version},
        )

        self.assertEqual(status_code, 200)
        assert payload is not None
        directions = payload["data"]["directions"]
        self.assertEqual(len(directions), 3)
        self.assertEqual([item["id"] for item in directions], ["A", "B", "C"])

    def test_opportunity_count_respects_requested_range(self) -> None:
        idea_id, version = self._create_idea("Custom Count Idea")
        status_code, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "count": 6, "version": version},
        )

        self.assertEqual(status_code, 200)
        assert payload is not None
        directions = payload["data"]["directions"]
        self.assertEqual(len(directions), 6)
        self.assertEqual([item["id"] for item in directions], ["A", "B", "C", "D", "E", "F"])

        invalid_status, invalid_payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "count": 7, "version": payload["idea_version"]},
        )
        self.assertEqual(invalid_status, 422)
        assert invalid_payload is not None

    def test_patch_idea_returns_version_conflict(self) -> None:
        created_status, created = self.client.request_json(
            "POST",
            "/ideas",
            {"title": "Versioned Idea", "idea_seed": "seed"},
        )
        self.assertEqual(created_status, 201)
        assert created is not None
        idea_id = created["id"]

        first_patch_status, _ = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}",
            {"version": created["version"], "title": "Updated Title"},
        )
        self.assertEqual(first_patch_status, 200)

        stale_patch_status, stale_patch = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}",
            {"version": created["version"], "title": "Stale Title"},
        )
        self.assertEqual(stale_patch_status, 409)
        assert stale_patch is not None
        self.assertEqual(stale_patch["detail"]["code"], "IDEA_VERSION_CONFLICT")

    def test_idea_agent_not_found(self) -> None:
        status_code, payload = self.client.request_json(
            "POST",
            "/ideas/non-existent-id/agents/opportunity",
            {"idea_seed": "seed", "version": 1},
        )

        self.assertEqual(status_code, 404)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "IDEA_NOT_FOUND")

    def test_idea_agent_archived_conflict(self) -> None:
        created_status, created = self.client.request_json(
            "POST",
            "/ideas",
            {"title": "Archived Idea", "idea_seed": "seed"},
        )
        self.assertEqual(created_status, 201)
        assert created is not None
        idea_id = created["id"]
        archived_status, archived = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}",
            {"version": created["version"], "status": "archived"},
        )
        self.assertEqual(archived_status, 200)
        assert archived is not None

        status_code, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "version": archived["version"]},
        )
        self.assertEqual(status_code, 409)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "IDEA_ARCHIVED")

    def test_idea_agent_version_conflict(self) -> None:
        created_status, created = self.client.request_json(
            "POST",
            "/ideas",
            {"title": "Conflict Idea", "idea_seed": "seed"},
        )
        self.assertEqual(created_status, 201)
        assert created is not None
        idea_id = created["id"]
        initial_version = created["version"]

        ok_status, ok_payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "version": initial_version},
        )
        self.assertEqual(ok_status, 200)
        assert ok_payload is not None
        self.assertEqual(ok_payload["idea_version"], initial_version + 1)

        stale_status, stale_payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity",
            {"idea_seed": "seed", "version": initial_version},
        )
        self.assertEqual(stale_status, 409)
        assert stale_payload is not None
        self.assertEqual(stale_payload["detail"]["code"], "IDEA_VERSION_CONFLICT")

    def test_stream_persists_only_on_done_and_bumps_version(self) -> None:
        created_status, created = self.client.request_json(
            "POST",
            "/ideas",
            {"title": "Stream Idea", "idea_seed": "seed"},
        )
        self.assertEqual(created_status, 201)
        assert created is not None
        idea_id = created["id"]
        initial_version = created["version"]

        cancelled_stream = self.client.request_raw(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity/stream",
            {"idea_seed": "seed", "version": initial_version},
            disconnect_after_body_chunks=1,
        )
        self.assertEqual(cancelled_stream.status_code, 200)
        cancelled_events = _read_sse_events(cancelled_stream.body)
        self.assertTrue(cancelled_events)
        self.assertNotIn("done", [name for name, _ in cancelled_events])

        after_cancel_status, after_cancel = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(after_cancel_status, 200)
        assert after_cancel is not None
        self.assertEqual(after_cancel["version"], initial_version)
        self.assertIsNone(after_cancel["context"]["opportunity"])

        done_stream = self.client.request_raw(
            "POST",
            f"/ideas/{idea_id}/agents/opportunity/stream",
            {"idea_seed": "seed", "version": initial_version},
        )
        self.assertEqual(done_stream.status_code, 200)
        done_events = _read_sse_events(done_stream.body)

        event_names = [name for name, _ in done_events]
        self.assertIn("partial", event_names)
        self.assertEqual(event_names[-1], "done")

        done_payload = done_events[-1][1]
        assert done_payload is not None
        self.assertEqual(done_payload["idea_id"], idea_id)
        self.assertEqual(done_payload["idea_version"], initial_version + 1)

        after_done_status, after_done = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(after_done_status, 200)
        assert after_done is not None
        self.assertEqual(after_done["version"], initial_version + 1)
        self.assertIsNotNone(after_done["context"]["opportunity"])

    def test_feasibility_stream_emits_error_for_stale_version(self) -> None:
        idea_id, initial_version = self._create_idea("Feasibility Stream Idea")
        opportunity = self._generate_opportunity(idea_id, initial_version)
        direction = opportunity["data"]["directions"][0]
        current_version = opportunity["idea_version"]

        stale_stream = self.client.request_raw(
            "POST",
            f"/ideas/{idea_id}/agents/feasibility/stream",
            {
                "idea_seed": "seed",
                "direction_id": direction["id"],
                "direction_text": f"{direction['title']} - {direction['one_liner']}",
                "path_id": "pathA",
                "version": initial_version,
            },
        )
        self.assertEqual(stale_stream.status_code, 200)
        stale_events = _read_sse_events(stale_stream.body)
        self.assertTrue(stale_events)
        self.assertEqual(stale_events[-1][0], "error")
        assert stale_events[-1][1] is not None
        self.assertEqual(stale_events[-1][1]["code"], "IDEA_VERSION_CONFLICT")

        status_after_stale, detail_after_stale = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(status_after_stale, 200)
        assert detail_after_stale is not None
        self.assertEqual(detail_after_stale["version"], current_version)

        ok_stream = self.client.request_raw(
            "POST",
            f"/ideas/{idea_id}/agents/feasibility/stream",
            {
                "idea_seed": "seed",
                "direction_id": direction["id"],
                "direction_text": f"{direction['title']} - {direction['one_liner']}",
                "path_id": "pathA",
                "version": current_version,
            },
        )
        self.assertEqual(ok_stream.status_code, 200)
        ok_events = _read_sse_events(ok_stream.body)
        self.assertTrue(ok_events)
        self.assertEqual(ok_events[-1][0], "done")

        status_after_done, detail_after_done = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(status_after_done, 200)
        assert detail_after_done is not None
        self.assertEqual(detail_after_done["version"], current_version + 1)
        self.assertIsNotNone(detail_after_done["context"]["feasibility"])

    def test_scope_and_prd_version_guards(self) -> None:
        idea_id, initial_version = self._create_idea("Scope PRD Guard Idea")
        opportunity = self._generate_opportunity(idea_id, initial_version)
        direction = opportunity["data"]["directions"][0]
        direction_text = f"{direction['title']} - {direction['one_liner']}"
        feasibility = self._generate_feasibility(
            idea_id,
            version=opportunity["idea_version"],
            direction_id=direction["id"],
            direction_text=direction_text,
        )
        selected_plan_id = feasibility["data"]["plans"][0]["id"]

        stale_scope_status, stale_scope = self._generate_scope(
            idea_id,
            version=opportunity["idea_version"],
            direction_id=direction["id"],
            direction_text=direction_text,
            selected_plan_id=selected_plan_id,
            feasibility=feasibility["data"],
        )
        self.assertEqual(stale_scope_status, 409)
        assert stale_scope is not None
        self.assertEqual(stale_scope["detail"]["code"], "IDEA_VERSION_CONFLICT")

        scope_status, scope = self._generate_scope(
            idea_id,
            version=feasibility["idea_version"],
            direction_id=direction["id"],
            direction_text=direction_text,
            selected_plan_id=selected_plan_id,
            feasibility=feasibility["data"],
        )
        self.assertEqual(scope_status, 200)
        assert scope is not None

        stale_prd_status, stale_prd = self._generate_prd(
            idea_id,
            version=feasibility["idea_version"],
            direction_text=direction_text,
            selected_plan_id=selected_plan_id,
            scope=scope["data"],
        )
        self.assertEqual(stale_prd_status, 409)
        assert stale_prd is not None
        self.assertEqual(stale_prd["detail"]["code"], "IDEA_VERSION_CONFLICT")

        prd_status, prd = self._generate_prd(
            idea_id,
            version=scope["idea_version"],
            direction_text=direction_text,
            selected_plan_id=selected_plan_id,
            scope=scope["data"],
        )
        self.assertEqual(prd_status, 200)
        assert prd is not None
        self.assertEqual(prd["idea_version"], scope["idea_version"] + 1)

        final_status, final_detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(final_status, 200)
        assert final_detail is not None
        self.assertEqual(final_detail["version"], prd["idea_version"])
        self.assertIsNotNone(final_detail["context"]["scope"])
        self.assertIsNotNone(final_detail["context"]["prd"])


    def test_delete_idea_returns_204(self) -> None:
        r = self.client.request_raw("DELETE", f"/ideas/{self.idea_id}")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.body, b"")

    def test_delete_idea_removes_from_list(self) -> None:
        self.client.request_raw("DELETE", f"/ideas/{self.idea_id}")
        r_status, r_body = self.client.request_json("GET", "/ideas")
        assert r_body is not None
        ids = [i["id"] for i in r_body["items"]]
        self.assertNotIn(self.idea_id, ids)

    def test_delete_idea_not_found_returns_404(self) -> None:
        r_status, r_body = self.client.request_json("DELETE", "/ideas/nonexistent-id")
        self.assertEqual(r_status, 404)

    def test_delete_idea_get_returns_404_after_delete(self) -> None:
        self.client.request_raw("DELETE", f"/ideas/{self.idea_id}")
        r_status, r_body = self.client.request_json("GET", f"/ideas/{self.idea_id}")
        self.assertEqual(r_status, 404)


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
        *,
        disconnect_after_body_chunks: int | None = None,
    ) -> tuple[int, dict[str, object] | None]:
        response = self.request_raw(
            method,
            path,
            payload,
            disconnect_after_body_chunks=disconnect_after_body_chunks,
        )
        if not response.body:
            return response.status_code, None
        return response.status_code, json.loads(response.body.decode("utf-8"))

    def request_raw(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        disconnect_after_body_chunks: int | None = None,
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
                disconnect_after_body_chunks=disconnect_after_body_chunks,
            )
        )


async def _run_asgi_request(
    *,
    app: object,
    method: str,
    path: str,
    body: bytes,
    disconnect_after_body_chunks: int | None,
) -> _RawResponse:
    request_sent = False
    body_chunk_count = 0
    response_started = False
    response_status = 500
    body_parts: list[bytes] = []
    hold_receive = asyncio.Event()

    async def receive() -> dict[str, object]:
        nonlocal request_sent

        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        if disconnect_after_body_chunks is not None:
            while body_chunk_count < disconnect_after_body_chunks:
                await asyncio.sleep(0.001)
            return {"type": "http.disconnect"}

        await hold_receive.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        nonlocal body_chunk_count, response_started, response_status

        message_type = str(message.get("type"))
        if message_type == "http.response.start":
            response_started = True
            response_status = int(message.get("status", 500))
            return

        if message_type == "http.response.body":
            body_chunk_count += 1
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


def _read_sse_events(body: bytes) -> list[tuple[str, dict[str, object] | None]]:
    events: list[tuple[str, dict[str, object] | None]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    for line in body.decode("utf-8").splitlines():
        if line == "":
            if event_name is not None:
                payload = None
                if data_lines:
                    payload = json.loads("\n".join(data_lines))
                events.append((event_name, payload))
            event_name = None
            data_lines = []
            continue

        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())

    if event_name is not None:
        payload = None
        if data_lines:
            payload = json.loads("\n".join(data_lines))
        events.append((event_name, payload))

    return events


if __name__ == "__main__":
    unittest.main()
