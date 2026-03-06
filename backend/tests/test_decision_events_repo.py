from __future__ import annotations

import os
import tempfile
import unittest

from tests._test_env import ensure_required_seed_env


class DecisionEventRepoTestCase(unittest.TestCase):
    """Use a dedicated test user_id to avoid collisions with demo seed data."""

    _TEST_USER = "test-decision-events"

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
            user_id=self._TEST_USER,
        )
        self.repo.record(
            event_type="feasibility_plan_selected",
            idea_id="idea-1",
            payload={"plan_name": "Bootstrap"},
            user_id=self._TEST_USER,
        )

        events = self.repo.list_for_user(self._TEST_USER)
        self.assertEqual(len(events), 2)
        # Most recent first
        self.assertEqual(events[0].event_type, "feasibility_plan_selected")
        self.assertEqual(events[1].event_type, "dag_path_confirmed")

    def test_count(self) -> None:
        self.assertEqual(self.repo.count_for_user(self._TEST_USER), 0)
        self.repo.record(event_type="scope_frozen", idea_id="idea-2", user_id=self._TEST_USER)
        self.assertEqual(self.repo.count_for_user(self._TEST_USER), 1)

    def test_list_respects_limit(self) -> None:
        for i in range(10):
            self.repo.record(event_type="prd_generated", idea_id=f"idea-{i}", user_id=self._TEST_USER)
        events = self.repo.list_for_user(self._TEST_USER, limit=3)
        self.assertEqual(len(events), 3)

    def test_exists_for_idea_event_key(self) -> None:
        self.repo.record(
            event_type="prd_generated",
            idea_id="idea-42",
            payload={"baseline_id": "bl-1"},
            user_id=self._TEST_USER,
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
            user_id=self._TEST_USER,
        )
        events = self.repo.list_for_user(self._TEST_USER)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["path_id"], "p99")
        self.assertEqual(events[0].payload["node_count"], 3)
        self.assertEqual(events[0].payload["leaf_content"], "Deploy MVP")


if __name__ == "__main__":
    unittest.main()
