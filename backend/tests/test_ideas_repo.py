from __future__ import annotations

import copy
import os
import tempfile
import unittest


class IdeasRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
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
        self.assertEqual(len(default_items), 1)

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
        self.assertEqual(active_items, [])

        archived_items, _ = self.repo.list_ideas(statuses=["archived"], limit=50)
        self.assertEqual(len(archived_items), 1)
        self.assertEqual(archived_items[0].id, created.id)

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
