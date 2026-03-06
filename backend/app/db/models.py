from __future__ import annotations

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS workspace (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS idea (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        title TEXT NOT NULL,
        idea_seed TEXT,
        stage TEXT NOT NULL CHECK (stage IN ('idea_canvas', 'feasibility', 'scope_freeze', 'prd')),
        status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'frozen', 'archived')),
        context_json TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT,
        FOREIGN KEY (workspace_id) REFERENCES workspace(id),
        CHECK (
            (status = 'archived' AND archived_at IS NOT NULL)
            OR
            (status != 'archived' AND archived_at IS NULL)
        )
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_idea_updated
    ON idea(updated_at DESC, id DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_idea_status_updated
    ON idea(status, updated_at DESC, id DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_settings (
        id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_account (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_session (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_session_user_id
    ON auth_session(user_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_session_expires_at
    ON auth_session(expires_at);
    """,
    """
    CREATE TABLE IF NOT EXISTS idea_nodes (
        id                TEXT PRIMARY KEY,
        idea_id           TEXT NOT NULL REFERENCES idea(id),
        parent_id         TEXT REFERENCES idea_nodes(id),
        content           TEXT NOT NULL,
        expansion_pattern TEXT,
        edge_label        TEXT,
        depth             INTEGER NOT NULL DEFAULT 0,
        status            TEXT NOT NULL DEFAULT 'active',
        created_at        TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS idea_paths (
        id          TEXT PRIMARY KEY,
        idea_id     TEXT NOT NULL REFERENCES idea(id),
        node_chain  TEXT NOT NULL,
        path_md     TEXT NOT NULL,
        path_json   TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scope_baselines (
        id TEXT PRIMARY KEY,
        idea_id TEXT NOT NULL REFERENCES idea(id),
        version INTEGER NOT NULL CHECK (version >= 1),
        status TEXT NOT NULL CHECK (status IN ('draft', 'frozen', 'superseded')),
        source_baseline_id TEXT,
        created_at TEXT NOT NULL,
        frozen_at TEXT
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_scope_baselines_idea_version_unique
    ON scope_baselines(idea_id, version);
    """,
    """
    CREATE TABLE IF NOT EXISTS scope_baseline_items (
        id TEXT PRIMARY KEY,
        baseline_id TEXT NOT NULL REFERENCES scope_baselines(id) ON DELETE CASCADE,
        lane TEXT NOT NULL CHECK (lane IN ('in', 'out')),
        content TEXT NOT NULL,
        display_order INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scope_baseline_items_order
    ON scope_baseline_items(baseline_id, lane, display_order);
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id                   TEXT PRIMARY KEY,
        email                     TEXT,
        notify_enabled            INTEGER NOT NULL DEFAULT 0,
        learned_patterns_json     TEXT NOT NULL DEFAULT '{}',
        last_learned_event_count  INTEGER NOT NULL DEFAULT 0,
        updated_at                TEXT NOT NULL DEFAULT ''
    );
    """,
    # NOTE: The following ALTER TABLE statements are the migration path for existing databases.
    # Fresh databases already have these columns from the CREATE TABLE above.
    # bootstrap.py's _column_exists() guard makes both paths safe.
    """
    ALTER TABLE user_preferences
    ADD COLUMN learned_patterns_json TEXT NOT NULL DEFAULT '{}';
    """,
    """
    ALTER TABLE user_preferences
    ADD COLUMN last_learned_event_count INTEGER NOT NULL DEFAULT 0;
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_events (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL DEFAULT 'default',
        idea_id     TEXT,
        event_type  TEXT NOT NULL CHECK (event_type IN (
                        'dag_path_confirmed',
                        'feasibility_plan_selected',
                        'scope_frozen',
                        'prd_generated'
                    )),
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_decision_events_user_created
    ON decision_events(user_id, created_at DESC);
    """,
)
