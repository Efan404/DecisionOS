from __future__ import annotations

import os
import tempfile
import unittest

from tests._test_env import ensure_required_seed_env


class DecisionEventRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decision-events-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database

        initialize_database()

        from app.db.repo_decision_events import DecisionEventRepository

        self.repo = DecisionEventRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_record_and_list(self) -> None:
        self.repo.record(
            event_type="dag_path_confirmed",
            idea_id="idea-1",
            payload={"path_id": "p1"},
        )
        self.repo.record(
            event_type="feasibility_plan_selected",
            idea_id="idea-1",
            payload={"plan_name": "Bootstrap"},
        )

        events = self.repo.list_for_user()
        self.assertEqual(len(events), 2)
        # Most recent first
        self.assertEqual(events[0].event_type, "feasibility_plan_selected")
        self.assertEqual(events[1].event_type, "dag_path_confirmed")

    def test_count(self) -> None:
        self.assertEqual(self.repo.count_for_user(), 0)
        self.repo.record(event_type="scope_frozen", idea_id="idea-2")
        self.assertEqual(self.repo.count_for_user(), 1)

    def test_list_respects_limit(self) -> None:
        for i in range(10):
            self.repo.record(event_type="prd_generated", idea_id=f"idea-{i}")
        events = self.repo.list_for_user(limit=3)
        self.assertEqual(len(events), 3)

    def test_exists_for_idea_event_key(self) -> None:
        self.repo.record(
            event_type="prd_generated",
            idea_id="idea-42",
            payload={"baseline_id": "bl-1"},
        )
        self.assertTrue(
            self.repo.exists_for_idea_event_key(
                "idea-42", "prd_generated", "baseline_id", "bl-1"
            )
        )
        self.assertFalse(
            self.repo.exists_for_idea_event_key(
                "idea-42", "prd_generated", "baseline_id", "bl-999"
            )
        )

    def test_payload_stored_and_retrieved(self) -> None:
        self.repo.record(
            event_type="dag_path_confirmed",
            idea_id="idea-xyz",
            payload={"path_id": "p99", "node_count": 3, "leaf_content": "Deploy MVP"},
        )
        events = self.repo.list_for_user()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["path_id"], "p99")
        self.assertEqual(events[0].payload["node_count"], 3)
        self.assertEqual(events[0].payload["leaf_content"], "Deploy MVP")


if __name__ == "__main__":
    unittest.main()
