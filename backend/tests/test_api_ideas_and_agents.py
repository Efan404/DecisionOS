from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from tests._test_env import ensure_required_seed_env

_DIR_IDS = ["A", "B", "C", "D", "E", "F"]


def _mock_opportunity(payload: object) -> object:
    """Return an OpportunityOutput with exactly payload.count directions."""
    from app.schemas.common import Direction
    from app.schemas.idea import OpportunityOutput

    count = getattr(payload, "count", 3)
    return OpportunityOutput(
        directions=[
            Direction(
                id=_DIR_IDS[i],
                title=f"Direction {_DIR_IDS[i]}",
                one_liner=f"One-liner for direction {_DIR_IDS[i]}",
                pain_tags=["tag1"],
            )
            for i in range(count)
        ]
    )


def _mock_single_plan(payload: object, plan_index: int) -> object:
    """Return a single Plan for stream_feasibility (generate_single_plan mock)."""
    from app.schemas.common import ReasoningBreakdown, ScoreBreakdown
    from app.schemas.feasibility import Plan

    pid = f"plan{plan_index}"
    return Plan(
        id=pid,
        name=f"Plan {plan_index}",
        summary=f"Summary for plan {plan_index}",
        score_overall=8.0 - plan_index * 0.5,
        scores=ScoreBreakdown(
            technical_feasibility=8.0,
            market_viability=8.0,
            execution_risk=7.5,
        ),
        reasoning=ReasoningBreakdown(
            technical_feasibility="tech",
            market_viability="market",
            execution_risk="risk",
        ),
        recommended_positioning=f"Position {plan_index}",
    )


def _mock_feasibility(payload: object) -> object:
    from app.schemas.common import ReasoningBreakdown, ScoreBreakdown
    from app.schemas.feasibility import FeasibilityOutput, Plan

    def _plan(idx: int) -> Plan:
        pid = f"plan{idx}"
        return Plan(
            id=pid,
            name=f"Plan {idx}",
            summary=f"Summary for plan {idx}",
            score_overall=8.0 - idx * 0.5,
            scores=ScoreBreakdown(
                technical_feasibility=8.0,
                market_viability=8.0,
                execution_risk=7.5,
            ),
            reasoning=ReasoningBreakdown(
                technical_feasibility="tech",
                market_viability="market",
                execution_risk="risk",
            ),
            recommended_positioning=f"Position {idx}",
        )

    return FeasibilityOutput(plans=[_plan(1), _plan(2), _plan(3)])


def _mock_scope(payload: object) -> object:
    from app.schemas.scope import InScopeItem, OutScopeItem, ScopeOutput

    return ScopeOutput(
        in_scope=[
            InScopeItem(id="in-1", title="Feature A", desc="Core feature", priority="P0"),
            InScopeItem(id="in-2", title="Feature B", desc="Secondary feature", priority="P1"),
        ],
        out_scope=[
            OutScopeItem(id="out-1", title="Feature X", desc="Nice to have", reason="deferred"),
        ],
    )


def _mock_prd(context_pack: object) -> object:
    from app.schemas.prd import (
        PRDBacklog,
        PRDBacklogItem,
        PRDGenerationMeta,
        PRDOutput,
        PRDRequirement,
        PRDSection,
    )

    req_ids = [f"REQ-{i}" for i in range(1, 7)]
    requirements = [
        PRDRequirement(
            id=req_id,
            title=f"Requirement {req_id}",
            description=f"Description for {req_id}",
            rationale=f"Rationale for {req_id}",
            acceptance_criteria=["AC1", "AC2"],
            source_refs=["step2"],
        )
        for req_id in req_ids
    ]
    backlog_items = [
        PRDBacklogItem(
            id=f"BL-{i}",
            title=f"Backlog Item {i}",
            requirement_id=req_ids[(i - 1) % len(req_ids)],
            priority="P1",
            type="story",
            summary=f"Summary for item {i}",
            acceptance_criteria=["AC1", "AC2"],
            source_refs=["step3"],
        )
        for i in range(1, 9)
    ]
    from app.schemas.prd import PrdContextPack

    pack: PrdContextPack = context_pack  # type: ignore[assignment]
    meta = PRDGenerationMeta(
        provider_id="mock",
        model="mock-model",
        confirmed_path_id=pack.step2_path.path_id,
        selected_plan_id=pack.step3_feasibility.selected_plan.id,
        baseline_id=pack.step4_scope.baseline_meta.baseline_id,
    )
    return PRDOutput(
        markdown="# PRD\n\nMock PRD content.",
        sections=[
            PRDSection(id=f"sec-{i}", title=f"Section {i}", content=f"Content {i}")
            for i in range(1, 7)
        ],
        requirements=requirements,
        backlog=PRDBacklog(items=backlog_items),
        generation_meta=meta,
    )


class IdeasAndAgentsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decisionos-api-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        os.environ["DECISIONOS_AUTH_DISABLED"] = "1"

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

        # Patch all LLM calls so tests don't require a real AI provider
        self._patch_opportunity = patch(
            "app.core.llm.generate_opportunity", side_effect=_mock_opportunity
        )
        self._patch_feasibility = patch(
            "app.core.llm.generate_feasibility", side_effect=_mock_feasibility
        )
        self._patch_single_plan = patch(
            "app.core.llm.generate_single_plan", side_effect=_mock_single_plan
        )
        self._patch_scope = patch(
            "app.core.llm.generate_scope", side_effect=_mock_scope
        )
        self._patch_prd = patch(
            "app.core.llm.generate_prd_strict", side_effect=_mock_prd
        )
        self._patch_path_summary = patch(
            "app.core.llm.generate_path_summary", return_value="Mock path summary."
        )
        self._patch_opportunity.start()
        self._patch_feasibility.start()
        self._patch_single_plan.start()
        self._patch_scope.start()
        self._patch_prd.start()
        self._patch_path_summary.start()

        self.idea_id, _ = self._create_idea("Delete Test Idea")

    def tearDown(self) -> None:
        self._patch_opportunity.stop()
        self._patch_feasibility.stop()
        self._patch_single_plan.stop()
        self._patch_scope.stop()
        self._patch_prd.stop()
        self._patch_path_summary.stop()
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
        confirmed_path_id: str = "dag-path-1",
        confirmed_node_id: str = "dag-node-1",
        confirmed_node_content: str = "Validated DAG node content",
        confirmed_path_summary: str | None = "DAG path summary",
    ) -> dict[str, object]:
        status, payload = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/feasibility",
            {
                "idea_seed": "seed",
                "confirmed_path_id": confirmed_path_id,
                "confirmed_node_id": confirmed_node_id,
                "confirmed_node_content": confirmed_node_content,
                "confirmed_path_summary": confirmed_path_summary,
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
        confirmed_path_id: str,
        confirmed_node_id: str,
        confirmed_node_content: str,
        confirmed_path_summary: str | None,
        selected_plan_id: str,
        feasibility: dict[str, object],
    ) -> tuple[int, dict[str, object] | None]:
        return self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/scope",
            {
                "idea_seed": "seed",
                "confirmed_path_id": confirmed_path_id,
                "confirmed_node_id": confirmed_node_id,
                "confirmed_node_content": confirmed_node_content,
                "confirmed_path_summary": confirmed_path_summary,
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
        baseline_id: str,
    ) -> tuple[int, dict[str, object] | None]:
        return self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/agents/prd",
            {
                "version": version,
                "baseline_id": baseline_id,
            },
        )

    def _post_prd_feedback(
        self,
        idea_id: str,
        *,
        version: int,
        baseline_id: str,
        rating_overall: int = 4,
        comment: str | None = None,
    ) -> tuple[int, dict[str, object] | None]:
        return self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/prd/feedback",
            {
                "version": version,
                "baseline_id": baseline_id,
                "rating_overall": rating_overall,
                "rating_dimensions": {
                    "clarity": 4,
                    "completeness": 4,
                    "actionability": 4,
                    "scope_fit": 4,
                },
                "comment": comment,
            },
        )

    def _create_root_and_confirm_path(self, idea_id: str, *, version: int) -> tuple[str, int]:
        root_status, root = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/nodes",
            {"content": "Root node"},
        )
        self.assertEqual(root_status, 201)
        assert root is not None

        confirm_status, confirmed = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/paths",
            {"node_chain": [root["id"]]},
        )
        self.assertEqual(confirm_status, 201)
        assert confirmed is not None

        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None
        return confirmed["id"], detail["version"]

    def _prepare_prd_baseline(self, idea_id: str, *, version: int) -> tuple[str, int, str]:
        _, version_after_path = self._create_root_and_confirm_path(idea_id, version=version)
        feasibility = self._generate_feasibility(
            idea_id,
            version=version_after_path,
            confirmed_path_id="dag-path-v2",
            confirmed_node_id="dag-node-v2",
            confirmed_node_content="Validated DAG node content",
            confirmed_path_summary="DAG path summary",
        )
        selected_plan_id = feasibility["data"]["plans"][0]["id"]

        scope_status, scope = self._generate_scope(
            idea_id,
            version=feasibility["idea_version"],
            confirmed_path_id="dag-path-v2",
            confirmed_node_id="dag-node-v2",
            confirmed_node_content="Validated DAG node content",
            confirmed_path_summary="DAG path summary",
            selected_plan_id=selected_plan_id,
            feasibility=feasibility["data"],
        )
        self.assertEqual(scope_status, 200)
        assert scope is not None

        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {"version": scope["idea_version"]},
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
        return frozen["data"]["id"], frozen["idea_version"], selected_plan_id

    def test_legacy_agents_route_reports_gone(self) -> None:
        status_code, payload = self.client.request_json(
            "POST",
            "/agents/opportunity",
            {"idea_seed": "seed"},
        )

        self.assertEqual(status_code, 410)
        assert payload is not None
        self.assertEqual(payload["detail"]["code"], "LEGACY_AGENTS_ROUTE_GONE")

    def test_request_id_header_echoes_when_provided(self) -> None:
        response = self.client.request_raw(
            "GET",
            "/ideas",
            headers={"x-request-id": "req-test-echo-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-request-id"), "req-test-echo-1")

    def test_request_id_header_generated_when_missing(self) -> None:
        response = self.client.request_raw("GET", "/ideas")
        self.assertEqual(response.status_code, 200)
        generated = response.headers.get("x-request-id")
        self.assertIsNotNone(generated)
        assert generated is not None
        self.assertNotEqual(generated.strip(), "")

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

    def test_idea_agents_routes_are_rate_limited(self) -> None:
        from app.core.settings import get_settings
        from app.main import create_app

        old_limit = os.environ.get("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_MAX_REQUESTS")
        old_window = os.environ.get("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_WINDOW_SECONDS")
        os.environ["DECISIONOS_RATE_LIMIT_IDEA_AGENTS_MAX_REQUESTS"] = "2"
        os.environ["DECISIONOS_RATE_LIMIT_IDEA_AGENTS_WINDOW_SECONDS"] = "60"
        get_settings.cache_clear()
        rate_limited_client = _AsgiTestClient(create_app())
        try:
            created_status, created = rate_limited_client.request_json(
                "POST",
                "/ideas",
                {"title": "Rate Limited Agents Idea", "idea_seed": "seed"},
            )
            self.assertEqual(created_status, 201)
            assert created is not None
            idea_id = created["id"]

            first_status, first_payload = rate_limited_client.request_json(
                "POST",
                f"/ideas/{idea_id}/agents/opportunity",
                {"idea_seed": "seed", "version": created["version"]},
            )
            self.assertEqual(first_status, 200)
            assert first_payload is not None

            second_response = rate_limited_client.request_raw(
                "POST",
                f"/ideas/{idea_id}/agents/opportunity/stream",
                {"idea_seed": "seed", "version": first_payload["idea_version"]},
            )
            self.assertEqual(second_response.status_code, 200)

            third_status, third_payload = rate_limited_client.request_json(
                "POST",
                f"/ideas/{idea_id}/agents/feasibility",
                {
                    "idea_seed": "seed",
                    "confirmed_path_id": "dag-path-1",
                    "confirmed_node_id": "dag-node-1",
                    "confirmed_node_content": "Validated DAG node content",
                    "confirmed_path_summary": "DAG path summary",
                    "version": first_payload["idea_version"] + 1,
                },
            )
            self.assertEqual(third_status, 429)
            assert third_payload is not None
            self.assertEqual(third_payload["detail"]["code"], "RATE_LIMITED")
        finally:
            if old_limit is None:
                os.environ.pop("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_MAX_REQUESTS", None)
            else:
                os.environ["DECISIONOS_RATE_LIMIT_IDEA_AGENTS_MAX_REQUESTS"] = old_limit

            if old_window is None:
                os.environ.pop("DECISIONOS_RATE_LIMIT_IDEA_AGENTS_WINDOW_SECONDS", None)
            else:
                os.environ["DECISIONOS_RATE_LIMIT_IDEA_AGENTS_WINDOW_SECONDS"] = old_window
            get_settings.cache_clear()

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
        current_version = opportunity["idea_version"]

        stale_stream = self.client.request_raw(
            "POST",
            f"/ideas/{idea_id}/agents/feasibility/stream",
            {
                "idea_seed": "seed",
                "confirmed_path_id": "dag-path-1",
                "confirmed_node_id": "dag-node-1",
                "confirmed_node_content": "Validated DAG node content",
                "confirmed_path_summary": "DAG path summary",
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
                "confirmed_path_id": "dag-path-1",
                "confirmed_node_id": "dag-node-1",
                "confirmed_node_content": "Validated DAG node content",
                "confirmed_path_summary": "DAG path summary",
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
        baseline_id, ready_version, selected_plan_id = self._prepare_prd_baseline(
            idea_id,
            version=initial_version,
        )

        stale_prd_status, stale_prd = self._generate_prd(
            idea_id,
            version=ready_version - 1,
            baseline_id=baseline_id,
        )
        self.assertEqual(stale_prd_status, 409)
        assert stale_prd is not None
        self.assertEqual(stale_prd["detail"]["code"], "IDEA_VERSION_CONFLICT")

        prd_status, prd = self._generate_prd(
            idea_id,
            version=ready_version,
            baseline_id=baseline_id,
        )
        self.assertEqual(prd_status, 200)
        assert prd is not None
        self.assertEqual(prd["idea_version"], ready_version + 1)
        requirements = prd["data"]["requirements"]
        backlog_items = prd["data"]["backlog"]["items"]
        requirement_ids = {item["id"] for item in requirements}
        self.assertGreaterEqual(len(requirements), 6)
        self.assertGreaterEqual(len(backlog_items), 8)
        self.assertTrue(requirement_ids)
        self.assertTrue(all(item["requirement_id"] in requirement_ids for item in backlog_items))

        final_status, final_detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(final_status, 200)
        assert final_detail is not None
        self.assertEqual(final_detail["version"], prd["idea_version"])
        self.assertIsNotNone(final_detail["context"]["scope"])
        self.assertIsNotNone(final_detail["context"]["prd"])
        self.assertEqual(final_detail["context"]["selected_plan_id"], selected_plan_id)
        self.assertEqual(final_detail["context"]["prd_bundle"]["baseline_id"], baseline_id)
        self.assertEqual(final_detail["context"]["prd_bundle"]["output"]["backlog"]["items"][0]["id"], "BL-1")
        self.assertNotIn("selected_direction_id", final_detail["context"])
        self.assertNotIn("path_id", final_detail["context"])

    def test_prd_context_pack_requires_selected_plan(self) -> None:
        idea_id, version = self._create_idea("PRD Selected Plan Required")
        _, version_after_path = self._create_root_and_confirm_path(idea_id, version=version)

        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {
                "version": version_after_path,
                "items": [{"lane": "in", "content": "MVP lane"}],
            },
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

        prd_status, prd = self._generate_prd(
            idea_id,
            version=frozen["idea_version"],
            baseline_id=frozen["data"]["id"],
        )
        self.assertEqual(prd_status, 409)
        assert prd is not None
        self.assertEqual(prd["detail"]["code"], "PRD_SELECTED_PLAN_REQUIRED")

    def test_prd_context_pack_requires_confirmed_path(self) -> None:
        idea_id, version = self._create_idea("PRD Confirmed Path Required")
        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None
        context_payload = dict(detail["context"])
        context_payload["selected_plan_id"] = "plan1"
        context_payload["feasibility"] = {
            "plans": [
                {
                    "id": "plan1",
                    "name": "Plan 1",
                    "summary": "summary",
                    "score_overall": 8.1,
                    "scores": {
                        "technical_feasibility": 8.0,
                        "market_viability": 8.0,
                        "execution_risk": 8.0,
                    },
                    "reasoning": {
                        "technical_feasibility": "tech",
                        "market_viability": "market",
                        "execution_risk": "risk",
                    },
                    "recommended_positioning": "position",
                },
                {
                    "id": "plan2",
                    "name": "Plan 2",
                    "summary": "summary 2",
                    "score_overall": 7.5,
                    "scores": {
                        "technical_feasibility": 7.0,
                        "market_viability": 8.0,
                        "execution_risk": 7.5,
                    },
                    "reasoning": {
                        "technical_feasibility": "tech",
                        "market_viability": "market",
                        "execution_risk": "risk",
                    },
                    "recommended_positioning": "position",
                },
                {
                    "id": "plan3",
                    "name": "Plan 3",
                    "summary": "summary 3",
                    "score_overall": 7.2,
                    "scores": {
                        "technical_feasibility": 7.0,
                        "market_viability": 7.2,
                        "execution_risk": 7.4,
                    },
                    "reasoning": {
                        "technical_feasibility": "tech",
                        "market_viability": "market",
                        "execution_risk": "risk",
                    },
                    "recommended_positioning": "position",
                },
            ]
        }
        patch_status, patched = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}/context",
            {"version": detail["version"], "context": context_payload},
        )
        self.assertEqual(patch_status, 200)
        assert patched is not None

        bootstrap_status, bootstrap = self.client.request_json(
            "POST",
            f"/ideas/{idea_id}/scope/draft/bootstrap",
            {
                "version": patched["version"],
                "items": [{"lane": "in", "content": "MVP lane"}],
            },
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

        prd_status, prd = self._generate_prd(
            idea_id,
            version=frozen["idea_version"],
            baseline_id=frozen["data"]["id"],
        )
        self.assertEqual(prd_status, 409)
        assert prd is not None
        self.assertEqual(prd["detail"]["code"], "PRD_CONFIRMED_PATH_REQUIRED")

    def test_prd_generation_failed_in_non_mock_returns_502(self) -> None:
        from app.core.llm import PRDGenerationError

        idea_id, version = self._create_idea("PRD Strict Failure")
        baseline_id, ready_version, _ = self._prepare_prd_baseline(idea_id, version=version)
        with patch(
            "app.core.llm.generate_prd_strict",
            side_effect=PRDGenerationError("provider down"),
        ):
            prd_status, prd = self._generate_prd(
                idea_id,
                version=ready_version,
                baseline_id=baseline_id,
            )
        self.assertEqual(prd_status, 502)
        assert prd is not None
        self.assertEqual(prd["detail"]["code"], "PRD_GENERATION_FAILED")

    def test_prd_feedback_latest_only_and_version_guard(self) -> None:
        idea_id, version = self._create_idea("PRD Feedback Latest")
        baseline_id, ready_version, _ = self._prepare_prd_baseline(idea_id, version=version)
        prd_status, prd = self._generate_prd(idea_id, version=ready_version, baseline_id=baseline_id)
        self.assertEqual(prd_status, 200)
        assert prd is not None

        feedback_status, feedback = self._post_prd_feedback(
            idea_id,
            version=prd["idea_version"],
            baseline_id=baseline_id,
            rating_overall=4,
            comment="first",
        )
        self.assertEqual(feedback_status, 200)
        assert feedback is not None

        stale_status, stale = self._post_prd_feedback(
            idea_id,
            version=prd["idea_version"],
            baseline_id=baseline_id,
            rating_overall=2,
            comment="stale",
        )
        self.assertEqual(stale_status, 409)
        assert stale is not None
        self.assertEqual(stale["detail"]["code"], "IDEA_VERSION_CONFLICT")

        overwrite_status, overwrite = self._post_prd_feedback(
            idea_id,
            version=feedback["idea_version"],
            baseline_id=baseline_id,
            rating_overall=5,
            comment="latest",
        )
        self.assertEqual(overwrite_status, 200)
        assert overwrite is not None

        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None
        feedback_latest = detail["context"]["prd_feedback_latest"]
        self.assertEqual(feedback_latest["rating_overall"], 5)
        self.assertEqual(feedback_latest["comment"], "latest")
        self.assertEqual(feedback_latest["baseline_id"], baseline_id)

    def test_patch_context_persists_selected_plan_id(self) -> None:
        idea_id, initial_version = self._create_idea("Persist Selected Plan")
        opportunity = self._generate_opportunity(idea_id, initial_version)
        feasibility = self._generate_feasibility(
            idea_id,
            version=opportunity["idea_version"],
            confirmed_path_id="dag-path-selected-plan",
            confirmed_node_id="dag-node-selected-plan",
            confirmed_node_content="Selected plan node content",
            confirmed_path_summary="Selected plan path summary",
        )
        selected_plan_id = feasibility["data"]["plans"][0]["id"]

        detail_status, detail = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(detail_status, 200)
        assert detail is not None

        context_payload = dict(detail["context"])
        context_payload["selected_plan_id"] = selected_plan_id

        patch_status, patched = self.client.request_json(
            "PATCH",
            f"/ideas/{idea_id}/context",
            {"version": detail["version"], "context": context_payload},
        )
        self.assertEqual(patch_status, 200)
        assert patched is not None
        self.assertEqual(patched["context"]["selected_plan_id"], selected_plan_id)
        self.assertEqual(patched["stage"], "scope_freeze")
        self.assertEqual(patched["version"], detail["version"] + 1)

        persisted_status, persisted = self.client.request_json("GET", f"/ideas/{idea_id}")
        self.assertEqual(persisted_status, 200)
        assert persisted is not None
        self.assertEqual(persisted["context"]["selected_plan_id"], selected_plan_id)
        self.assertEqual(persisted["stage"], "scope_freeze")

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
        assert r_body is not None
        detail = r_body["detail"]
        self.assertEqual(detail["code"], "IDEA_NOT_FOUND")

    def test_delete_idea_second_delete_returns_404(self) -> None:
        r_first = self.client.request_raw("DELETE", f"/ideas/{self.idea_id}")
        self.assertEqual(r_first.status_code, 204)
        r_status, r_body = self.client.request_json("DELETE", f"/ideas/{self.idea_id}")
        self.assertEqual(r_status, 404)
        assert r_body is not None
        detail = r_body["detail"]
        self.assertEqual(detail["code"], "IDEA_NOT_FOUND")

    def test_delete_idea_get_returns_404_after_delete(self) -> None:
        self.client.request_raw("DELETE", f"/ideas/{self.idea_id}")
        r_status, r_body = self.client.request_json("GET", f"/ideas/{self.idea_id}")
        self.assertEqual(r_status, 404)


@dataclass(frozen=True)
class _RawResponse:
    status_code: int
    body: bytes
    headers: dict[str, str]


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
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object] | None]:
        response = self.request_raw(
            method,
            path,
            payload,
            disconnect_after_body_chunks=disconnect_after_body_chunks,
            headers=headers,
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
                disconnect_after_body_chunks=disconnect_after_body_chunks,
                headers=headers,
            )
        )


async def _run_asgi_request(
    *,
    app: object,
    method: str,
    path: str,
    body: bytes,
    disconnect_after_body_chunks: int | None,
    headers: dict[str, str] | None,
) -> _RawResponse:
    request_sent = False
    body_chunk_count = 0
    response_started = False
    response_status = 500
    body_parts: list[bytes] = []
    response_headers: dict[str, str] = {}
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
            raw_headers = message.get("headers", [])
            if isinstance(raw_headers, list):
                for item in raw_headers:
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    raw_name, raw_value = item
                    if isinstance(raw_name, bytes) and isinstance(raw_value, bytes):
                        response_headers[raw_name.decode("latin-1").lower()] = raw_value.decode("latin-1")
            return

        if message_type == "http.response.body":
            body_chunk_count += 1
            raw = message.get("body", b"")
            if isinstance(raw, bytes):
                body_parts.append(raw)
            elif isinstance(raw, str):
                body_parts.append(raw.encode("utf-8"))

    incoming_headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    if headers is not None:
        for name, value in headers.items():
            incoming_headers.append(
                (name.encode("latin-1").lower(), value.encode("latin-1"))
            )

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
        "headers": incoming_headers,
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "state": {},
    }

    await app(scope, receive, send)

    if not response_started:
        raise RuntimeError("ASGI response did not start")

    return _RawResponse(status_code=response_status, body=b"".join(body_parts), headers=response_headers)


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
