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
    CREATE TABLE IF NOT EXISTS notification (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        type TEXT NOT NULL CHECK (type IN ('news_match', 'cross_idea_insight', 'pattern_learned')),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        read_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_trace (
        id TEXT PRIMARY KEY,
        idea_id TEXT,
        graph_name TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        node_name TEXT NOT NULL,
        input_json TEXT,
        output_json TEXT,
        duration_ms INTEGER,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id                   TEXT PRIMARY KEY,
        email                     TEXT,
        notify_enabled            INTEGER NOT NULL DEFAULT 0,
        notify_types              TEXT NOT NULL DEFAULT '["news_match","cross_idea_insight","pattern_learned"]',
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
    """
    CREATE TABLE IF NOT EXISTS competitor (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspace(id),
        name TEXT NOT NULL,
        canonical_url TEXT,
        category TEXT,
        status TEXT NOT NULL CHECK (status IN ('candidate', 'tracked', 'archived')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_competitor_workspace_updated
    ON competitor(workspace_id, updated_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS competitor_snapshot (
        id TEXT PRIMARY KEY,
        competitor_id TEXT NOT NULL REFERENCES competitor(id) ON DELETE CASCADE,
        snapshot_version INTEGER NOT NULL CHECK (snapshot_version >= 1),
        summary_json TEXT NOT NULL DEFAULT '{}',
        quality_score REAL,
        traction_score REAL,
        relevance_score REAL,
        underrated_score REAL,
        confidence REAL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_competitor_snapshot_version
    ON competitor_snapshot(competitor_id, snapshot_version DESC);
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_snapshot_unique_version
    ON competitor_snapshot(competitor_id, snapshot_version);
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_source (
        id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL CHECK (source_type IN ('website', 'pricing', 'docs', 'news', 'community', 'review')),
        url TEXT NOT NULL,
        title TEXT,
        snippet TEXT,
        published_at TEXT,
        fetched_at TEXT NOT NULL,
        confidence REAL,
        payload_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS market_signal (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspace(id),
        signal_type TEXT NOT NULL CHECK (signal_type IN ('competitor_update', 'market_news', 'community_buzz', 'pricing_change')),
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
        detected_at TEXT NOT NULL,
        evidence_source_id TEXT REFERENCES evidence_source(id),
        payload_json TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_signal_workspace_detected
    ON market_signal(workspace_id, detected_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS idea_evidence_link (
        id TEXT PRIMARY KEY,
        idea_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
        entity_type TEXT NOT NULL CHECK (entity_type IN ('competitor', 'signal', 'insight')),
        entity_id TEXT NOT NULL,
        link_reason TEXT NOT NULL,
        relevance_score REAL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_idea_evidence_link_idea
    ON idea_evidence_link(idea_id, entity_type, entity_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS cross_idea_insight (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspace(id),
        idea_a_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
        idea_b_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
        insight_type TEXT NOT NULL CHECK (insight_type IN (
            'execution_reuse', 'merge_candidate', 'positioning_conflict',
            'shared_audience', 'shared_capability', 'evidence_overlap'
        )),
        summary TEXT NOT NULL,
        why_it_matters TEXT NOT NULL,
        recommended_action TEXT NOT NULL CHECK (recommended_action IN (
            'review', 'compare_feasibility', 'reuse_scope',
            'reuse_prd_requirements', 'merge_ideas', 'keep_separate'
        )),
        confidence REAL,
        similarity_score REAL,
        evidence_json TEXT,
        fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (idea_a_id < idea_b_id)
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cross_idea_insight_dedup
    ON cross_idea_insight(idea_a_id, idea_b_id, fingerprint);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cross_idea_insight_idea_a
    ON cross_idea_insight(idea_a_id, updated_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cross_idea_insight_idea_b
    ON cross_idea_insight(idea_b_id, updated_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS search_settings (
        id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS market_insight (
        id TEXT PRIMARY KEY,
        idea_id TEXT NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
        summary TEXT NOT NULL,
        decision_impact TEXT NOT NULL,
        recommended_actions TEXT NOT NULL DEFAULT '[]',
        signal_count INTEGER NOT NULL DEFAULT 0,
        generated_at TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_insight_idea
    ON market_insight(idea_id, generated_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_v2 (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        type TEXT NOT NULL CHECK (type IN (
            'news_match', 'cross_idea_insight', 'pattern_learned',
            'market_signal', 'market_insight'
        )),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        read_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
)
