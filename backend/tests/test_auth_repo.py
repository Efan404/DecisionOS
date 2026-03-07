from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from tests._test_env import ensure_required_seed_env

_UTC_ISO_MILLIS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _parse_utc_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AuthRepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DECISIONOS_DB_PATH"] = os.path.join(self._tmpdir.name, "auth-repo-test.db")
        os.environ["DECISIONOS_AUTH_DISABLED"] = "0"
        os.environ["DECISIONOS_AUTH_SESSION_TTL_SECONDS"] = "600"

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database
        from app.db.repo_auth import AuthRepository

        initialize_database()
        self.repo = AuthRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()


    def test_get_user_by_session_token_rejects_expired_session(self) -> None:
        from app.core.auth_crypto import hash_session_token
        from app.core.time import utc_from_datetime_iso
        from app.db.engine import db_session

        now = datetime.now(UTC)
        valid_token = "valid-session-token"
        expired_token = "expired-session-token"

        with db_session() as connection:
            user_row = connection.execute(
                "SELECT id FROM user_account WHERE username = ?",
                ("mock",),
            ).fetchone()
            assert user_row is not None
            user_id = str(user_row["id"])
            connection.execute(
                """
                INSERT INTO auth_session (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    hash_session_token(valid_token),
                    user_id,
                    utc_from_datetime_iso(now - timedelta(minutes=1)),
                    utc_from_datetime_iso(now + timedelta(minutes=5)),
                ),
            )
            connection.execute(
                """
                INSERT INTO auth_session (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    hash_session_token(expired_token),
                    user_id,
                    utc_from_datetime_iso(now - timedelta(minutes=10)),
                    utc_from_datetime_iso(now - timedelta(seconds=1)),
                ),
            )

        user = self.repo.get_user_by_session_token(valid_token)
        self.assertIsNotNone(user)
        assert user is not None
        self.assertEqual(user.username, "mock")

        expired_user = self.repo.get_user_by_session_token(expired_token)
        self.assertIsNone(expired_user)

        with db_session() as connection:
            expired_row = connection.execute(
                "SELECT token_hash FROM auth_session WHERE token_hash = ?",
                (hash_session_token(expired_token),),
            ).fetchone()
        self.assertIsNone(expired_row)


if __name__ == "__main__":
    unittest.main()
