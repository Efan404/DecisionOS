from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest

from pydantic import ValidationError
from tests._test_env import ensure_required_seed_env


class IdeasRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decisionos-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database
        from app.db.repo_ideas import IdeaRepository

        initialize_database()
        self.repo = IdeaRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_default_workspace_bootstrap(self) -> None:
        workspace = self.repo.get_default_workspace()
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace.id, "default")
        self.assertEqual(workspace.name, "Default Workspace")

    def test_create_get_list_and_archive_filter(self) -> None:
        created = self.repo.create_idea(title="Idea One", idea_seed="alpha")

        self.assertEqual(created.version, 1)
        self.assertEqual(created.stage, "idea_canvas")
        self.assertEqual(created.status, "draft")
        self.assertEqual(created.context["context_schema_version"], 1)
        self.assertFalse(created.context["scope_frozen"])

        fetched = self.repo.get_idea(created.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.id, created.id)

        default_items, _ = self.repo.list_ideas(statuses=["draft", "active", "frozen"], limit=50)
        self.assertIn(created.id, [item.id for item in default_items])

        archived = self.repo.update_idea(
            created.id,
            version=1,
            title="Idea One Archived",
            status="archived",
        )
        self.assertEqual(archived.kind, "ok")
        assert archived.idea is not None
        self.assertEqual(archived.idea.version, 2)
        self.assertEqual(archived.idea.status, "archived")
        self.assertIsNotNone(archived.idea.archived_at)

        active_items, _ = self.repo.list_ideas(statuses=["draft", "active", "frozen"], limit=50)
        self.assertNotIn(created.id, [item.id for item in active_items])

        archived_items, _ = self.repo.list_ideas(statuses=["archived"], limit=50)
        self.assertIn(created.id, [item.id for item in archived_items])

    def test_update_idea_optimistic_locking(self) -> None:
        created = self.repo.create_idea(title="Versioned")

        ok_result = self.repo.update_idea(
            created.id,
            version=1,
            title="Versioned Updated",
            status=None,
        )
        self.assertEqual(ok_result.kind, "ok")
        assert ok_result.idea is not None
        self.assertEqual(ok_result.idea.version, 2)

        stale_result = self.repo.update_idea(
            created.id,
            version=1,
            title="Stale",
            status=None,
        )
        self.assertEqual(stale_result.kind, "conflict")

    def test_update_context_optimistic_locking(self) -> None:
        created = self.repo.create_idea(title="Context Idea", idea_seed="seed")
        next_context = copy.deepcopy(created.context)
        next_context["idea_seed"] = "seed-updated"

        ok_result = self.repo.update_context(
            created.id,
            version=1,
            context=next_context,
        )
        self.assertEqual(ok_result.kind, "ok")
        assert ok_result.idea is not None
        self.assertEqual(ok_result.idea.version, 2)
        self.assertEqual(ok_result.idea.context["idea_seed"], "seed-updated")

        stale_result = self.repo.update_context(
            created.id,
            version=1,
            context=next_context,
        )
        self.assertEqual(stale_result.kind, "conflict")

    def test_list_ideas_raises_for_invalid_context_payload(self) -> None:
        created = self.repo.create_idea(title="Legacy PRD", idea_seed="seed")

        from app.db.engine import db_session

        with db_session() as connection:
            row = connection.execute(
                "SELECT context_json FROM idea WHERE id = ?",
                (created.id,),
            ).fetchone()
            assert row is not None
            context_payload = json.loads(str(row["context_json"]))
            context_payload["prd"] = {
                "markdown": "# Legacy PRD",
                "sections": {"problem_statement": "old schema"},
            }
            connection.execute(
                "UPDATE idea SET context_json = ? WHERE id = ?",
                (json.dumps(context_payload, ensure_ascii=False), created.id),
            )

        with self.assertRaises(ValidationError):
            self.repo.list_ideas(statuses=["draft", "active", "frozen"], limit=50)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# pytest-style delete_idea tests
# ---------------------------------------------------------------------------
import os
import pytest
from app.db.bootstrap import initialize_database
from app.db.repo_ideas import IdeaRepository
from app.db import repo_dag as _repo_dag


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    initialize_database()


def _make_idea():
    repo = IdeaRepository()
    return repo.create_idea(title="Test Idea", idea_seed="seed")


# --- delete_idea tests ---

def test_delete_idea_removes_row():
    repo = IdeaRepository()
    idea = _make_idea()
    repo.delete_idea(idea.id)
    assert repo.get_idea(idea.id) is None


def test_delete_idea_cascades_nodes_and_paths():
    repo = IdeaRepository()
    idea = _make_idea()
    root = _repo_dag.create_node(idea_id=idea.id, content="root")
    child = _repo_dag.create_node(idea_id=idea.id, content="child", parent_id=root.id)
    _repo_dag.create_path(
        idea_id=idea.id,
        node_chain=[root.id, child.id],
        path_md="# Path",
        path_json='{"node_chain":[]}',
    )
    assert len(_repo_dag.list_nodes(idea.id)) == 2
    assert _repo_dag.get_latest_path(idea.id) is not None
    repo.delete_idea(idea.id)
    assert repo.get_idea(idea.id) is None
    assert _repo_dag.list_nodes(idea.id) == []
    assert _repo_dag.get_latest_path(idea.id) is None


def test_delete_idea_not_found_raises():
    repo = IdeaRepository()
    with pytest.raises(KeyError):
        repo.delete_idea("nonexistent-id")


class ApplyAgentUpdateRetryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decisionos-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings
        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database
        from app.db.repo_ideas import IdeaRepository
        initialize_database()
        self.repo = IdeaRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_idea(self):
        return self.repo.create_idea(title="Retry Test Idea")

    def _noop_mutate(self):
        """返回一个把 idea_seed 设为固定值的 mutate_context，幂等。"""
        from app.schemas.ideas import DecisionContext
        def mutate(ctx: DecisionContext) -> DecisionContext:
            ctx.idea_seed = "retry-seed"
            return ctx
        return mutate

    def test_apply_agent_update_succeeds_on_first_try(self):
        """正常情况：version 匹配，直接写库成功。"""
        idea = self._make_idea()
        result = self.repo.apply_agent_update(
            idea.id,
            version=idea.version,
            mutate_context=self._noop_mutate(),
        )
        self.assertEqual(result.kind, "ok")
        assert result.idea is not None
        self.assertEqual(result.idea.version, idea.version + 1)

    def test_apply_agent_update_retries_on_version_conflict(self):
        """关键测试：version 已被外部操作推进，apply_agent_update 应自动重试并成功。"""
        idea = self._make_idea()
        original_version = idea.version

        # 模拟"另一个并发操作"推进了 version（如 /paths 写库）
        bumped = self.repo.update_idea(
            idea.id,
            version=original_version,
            title="Bumped by concurrent op",
            status=None,
        )
        self.assertEqual(bumped.kind, "ok")
        assert bumped.idea is not None
        self.assertEqual(bumped.idea.version, original_version + 1)

        # apply_agent_update 仍用旧的 original_version，应自动 retry 并成功
        result = self.repo.apply_agent_update(
            idea.id,
            version=original_version,       # 过期版本
            mutate_context=self._noop_mutate(),
            allow_conflict_retry=True,
        )
        self.assertEqual(result.kind, "ok", f"Expected ok but got {result.kind}")
        assert result.idea is not None
        self.assertEqual(result.idea.version, original_version + 2)

    def test_apply_agent_update_retries_twice_on_double_conflict(self):
        """apply_agent_update succeeds even with two consecutive concurrent bumps."""
        idea = self._make_idea()
        original_version = idea.version

        # First concurrent bump (simulates background task)
        bump1 = self.repo.update_idea(
            idea.id, version=original_version, title="Bump 1", status=None
        )
        self.assertEqual(bump1.kind, "ok")
        assert bump1.idea is not None
        v1 = bump1.idea.version

        # Second concurrent bump (simulates scope operation)
        bump2 = self.repo.update_idea(
            idea.id, version=v1, title="Bump 2", status=None
        )
        self.assertEqual(bump2.kind, "ok")
        assert bump2.idea is not None
        v2 = bump2.idea.version

        # apply_agent_update with original stale version — needs 2 retries to succeed
        result = self.repo.apply_agent_update(
            idea.id,
            version=original_version,
            mutate_context=self._noop_mutate(),
            allow_conflict_retry=True,
        )
        self.assertEqual(result.kind, "ok", f"Expected ok but got {result.kind}")
        assert result.idea is not None
        self.assertEqual(result.idea.version, v2 + 1)

    def test_apply_agent_update_returns_not_found_for_missing_idea(self):
        """idea 不存在时，retry 后仍应返回 not_found，不崩溃。"""
        result = self.repo.apply_agent_update(
            "non-existent-id",
            version=1,
            mutate_context=self._noop_mutate(),
        )
        self.assertIn(result.kind, ("not_found", "conflict"))
