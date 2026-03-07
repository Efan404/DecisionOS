from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import cast

from app.core.secret_crypto import decrypt_text, encrypt_text, is_encrypted
from app.core.settings import get_settings
from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.schemas.search_settings import SearchSettingsDetail, SearchSettingsPayload

DEFAULT_SEARCH_SETTINGS_ID = "default"
_MASK_SENTINEL = "****"


@dataclass(frozen=True)
class SearchSettingsRecord:
    id: str
    config: SearchSettingsPayload
    created_at: str
    updated_at: str


def default_search_settings_payload() -> dict[str, object]:
    return {"providers": []}


class SearchSettingsRepository:
    def get_settings(self) -> SearchSettingsRecord:
        secret_key = get_settings().secret_key
        with db_session() as connection:
            row = _select_settings_row(connection)
            if row is None:
                _insert_default_settings(connection)
                row = _select_settings_row(connection)
                assert row is not None
            return _row_to_record(row, secret_key=secret_key)

    def update_settings(self, payload: SearchSettingsPayload) -> SearchSettingsRecord:
        now = utc_now_iso()
        secret_key = get_settings().secret_key
        encrypted_payload = _encrypt_payload(payload, secret_key=secret_key)
        config_json = json.dumps(encrypted_payload, ensure_ascii=False)
        with db_session() as connection:
            connection.execute(
                "UPDATE search_settings SET config_json = ?, updated_at = ? WHERE id = ?",
                (config_json, now, DEFAULT_SEARCH_SETTINGS_ID),
            )
            row = _select_settings_row(connection)
            assert row is not None
            return _row_to_record(row, secret_key=secret_key)


def ensure_default_search_settings(connection: sqlite3.Connection) -> None:
    now = utc_now_iso()
    connection.execute(
        "INSERT INTO search_settings (id, config_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
        (DEFAULT_SEARCH_SETTINGS_ID, json.dumps(default_search_settings_payload()), now, now),
    )


def _insert_default_settings(connection: sqlite3.Connection) -> None:
    ensure_default_search_settings(connection)


def _select_settings_row(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            "SELECT * FROM search_settings WHERE id = ?", (DEFAULT_SEARCH_SETTINGS_ID,)
        ).fetchone(),
    )


def _row_to_record(row: sqlite3.Row, *, secret_key: str) -> SearchSettingsRecord:
    raw_payload = SearchSettingsPayload.model_validate(json.loads(str(row["config_json"])))
    payload = _decrypt_payload(raw_payload, secret_key=secret_key)
    return SearchSettingsRecord(
        id=str(row["id"]),
        config=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _encrypt_payload(payload: SearchSettingsPayload, *, secret_key: str) -> dict[str, object]:
    raw = payload.model_dump(mode="python")
    for provider in raw.get("providers", []):
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key and not is_encrypted(api_key):
            provider["api_key"] = encrypt_text(plaintext=api_key, secret_key=secret_key)
    return raw


def _decrypt_payload(payload: SearchSettingsPayload, *, secret_key: str) -> SearchSettingsPayload:
    raw = payload.model_dump(mode="python")
    for provider in raw.get("providers", []):
        if not isinstance(provider, dict):
            continue
        api_key = provider.get("api_key")
        if isinstance(api_key, str) and api_key:
            provider["api_key"] = decrypt_text(payload=api_key, secret_key=secret_key)
    return SearchSettingsPayload.model_validate(raw)


def _mask_api_key(key: str | None) -> str | None:
    if not key:
        return key
    if len(key) <= 12:
        return _MASK_SENTINEL
    return f"{key[:4]}{_MASK_SENTINEL}{key[-4:]}"


def to_schema(record: SearchSettingsRecord) -> SearchSettingsDetail:
    masked_providers = [
        p.model_copy(update={"api_key": _mask_api_key(p.api_key)})
        for p in record.config.providers
    ]
    return SearchSettingsDetail(
        id=record.id,
        providers=masked_providers,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
