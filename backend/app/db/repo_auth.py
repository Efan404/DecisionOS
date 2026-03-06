from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.auth_crypto import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.core.settings import get_settings
from app.core.time import utc_from_datetime_iso, utc_now_iso
from app.db.engine import db_session


@dataclass(frozen=True)
class UserRecord:
    id: str
    username: str
    password_hash: str
    role: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LoginResult:
    user: UserRecord
    access_token: str
    expires_in: int


class AuthRepository:
    def authenticate(self, *, username: str, password: str) -> LoginResult | None:
        with db_session() as connection:
            user = _select_user_by_username(connection, username)
            if user is None or not verify_password(password, user.password_hash):
                return None

            settings = get_settings()
            expires_in = settings.auth_session_ttl_seconds
            token = generate_session_token()
            token_hash = hash_session_token(token)
            now = datetime.now(UTC)
            expires_at = now + timedelta(seconds=expires_in)
            connection.execute(
                """
                INSERT INTO auth_session (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    token_hash,
                    user.id,
                    utc_from_datetime_iso(now),
                    utc_from_datetime_iso(expires_at),
                ),
            )
            return LoginResult(user=user, access_token=token, expires_in=expires_in)

    def get_user_by_session_token(self, token: str) -> UserRecord | None:
        token_hash = hash_session_token(token)
        now_iso = utc_now_iso()
        with db_session() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.role, u.created_at, u.updated_at
                FROM auth_session s
                JOIN user_account u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hash, now_iso),
            ).fetchone()
            if row is None:
                connection.execute("DELETE FROM auth_session WHERE token_hash = ?", (token_hash,))
                return None
            return _row_to_user(row)

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with db_session() as connection:
            return _select_user_by_username(connection, username)

    def revoke_session(self, token: str) -> None:
        token_hash = hash_session_token(token)
        with db_session() as connection:
            connection.execute("DELETE FROM auth_session WHERE token_hash = ?", (token_hash,))

    def ensure_seed_users(self, connection: sqlite3.Connection) -> None:
        settings = get_settings()
        # Admin user is always created (required by settings)
        _upsert_seed_user(
            connection,
            username=settings.seed_admin_username,
            password=settings.seed_admin_password,
            role="admin",
        )
        # Test user is optional (has default values)
        _upsert_seed_user(
            connection,
            username=settings.seed_test_username,
            password=settings.seed_test_password,
            role="user",
        )
        # Demo/mock user for video recordings and demos
        _upsert_seed_user(
            connection,
            username="mock",
            password="mock",
            role="user",
        )


def _upsert_seed_user(
    connection: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str,
) -> None:
    existing = _select_user_by_username(connection, username)
    now = utc_now_iso()
    if existing is None:
        connection.execute(
            """
            INSERT INTO user_account (id, username, password_hash, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), username, hash_password(password), role, now, now),
        )
        return

    # Keep seed accounts deterministic for hackathon environments.
    connection.execute(
        """
        UPDATE user_account
        SET password_hash = ?, role = ?, updated_at = ?
        WHERE id = ?
        """,
        (hash_password(password), role, now, existing.id),
    )


def _select_user_by_username(
    connection: sqlite3.Connection,
    username: str,
) -> UserRecord | None:
    row = connection.execute(
        """
        SELECT id, username, password_hash, role, created_at, updated_at
        FROM user_account
        WHERE username = ?
        """,
        (username,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def _row_to_user(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=str(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
