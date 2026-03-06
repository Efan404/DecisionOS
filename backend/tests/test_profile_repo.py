from __future__ import annotations

import os
import tempfile
import unittest

from tests._test_env import ensure_required_seed_env


class ProfileRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "profile-repo-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database

        initialize_database()

        from app.db.repo_profile import ProfileRepository

        self.repo = ProfileRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_get_learned_patterns_empty(self) -> None:
        patterns, count = self.repo.get_learned_patterns()
        self.assertEqual(patterns, {})
        self.assertEqual(count, 0)

    def test_save_and_get_learned_patterns(self) -> None:
        patterns = {
            "business_model_preference": "Bootstrapped",
            "risk_tolerance": "Low",
        }
        self.repo.save_learned_patterns(patterns=patterns, event_count=5)
        retrieved, count = self.repo.get_learned_patterns()
        self.assertEqual(retrieved["business_model_preference"], "Bootstrapped")
        self.assertEqual(retrieved["risk_tolerance"], "Low")
        self.assertEqual(count, 5)

    def test_save_does_not_overwrite_email(self) -> None:
        """Pattern saves must not touch email/notify_enabled/updated_at."""
        from app.db.engine import get_connection

        # Manually set email in user_preferences
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, email, notify_enabled, updated_at)
                VALUES ('default', 'test@example.com', 1, '2024-01-01')
                ON CONFLICT(user_id) DO UPDATE SET
                    email = excluded.email,
                    notify_enabled = excluded.notify_enabled
                """
            )
            conn.commit()

        # Save patterns — should not touch email
        self.repo.save_learned_patterns(
            patterns={"focus_area": "AI tools"}, event_count=3
        )

        with get_connection() as conn:
            row = conn.execute(
                "SELECT email, notify_enabled, learned_patterns_json, last_learned_event_count FROM user_preferences WHERE user_id = 'default'"
            ).fetchone()

        self.assertEqual(row["email"], "test@example.com")
        self.assertEqual(row["notify_enabled"], 1)
        self.assertIn("AI tools", row["learned_patterns_json"])
        self.assertEqual(row["last_learned_event_count"], 3)

    def test_save_overwrites_previous_patterns(self) -> None:
        self.repo.save_learned_patterns(
            patterns={"focus_area": "old"}, event_count=2
        )
        self.repo.save_learned_patterns(
            patterns={"focus_area": "new"}, event_count=7
        )
        patterns, count = self.repo.get_learned_patterns()
        self.assertEqual(patterns["focus_area"], "new")
        self.assertEqual(count, 7)


if __name__ == "__main__":
    unittest.main()
