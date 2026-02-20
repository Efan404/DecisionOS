from __future__ import annotations

import os
import tempfile
import unittest


class DagRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database

        initialize_database()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _seed_idea(self) -> str:
        from app.db.repo_ideas import IdeaRepository

        repo = IdeaRepository()
        idea = repo.create_idea(title="Test", idea_seed="seed")
        return idea.id

    def test_create_root_node(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        node = repo_dag.create_node(idea_id=idea_id, content="root content", parent_id=None)
        self.assertIsNotNone(node.id)
        self.assertEqual(node.depth, 0)
        self.assertIsNone(node.parent_id)
        self.assertEqual(node.status, "active")
        self.assertEqual(node.content, "root content")

    def test_create_child_node(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        root = repo_dag.create_node(idea_id=idea_id, content="root", parent_id=None)
        child = repo_dag.create_node(
            idea_id=idea_id,
            content="child",
            parent_id=root.id,
            expansion_pattern="narrow_users",
            edge_label="缩小用户群体",
        )
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.parent_id, root.id)
        self.assertEqual(child.expansion_pattern, "narrow_users")
        self.assertEqual(child.edge_label, "缩小用户群体")

    def test_list_nodes(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        root = repo_dag.create_node(idea_id=idea_id, content="root", parent_id=None)
        repo_dag.create_node(idea_id=idea_id, content="child", parent_id=root.id)
        nodes = repo_dag.list_nodes(idea_id=idea_id)
        self.assertEqual(len(nodes), 2)

    def test_get_node(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        created = repo_dag.create_node(idea_id=idea_id, content="root", parent_id=None)
        fetched = repo_dag.get_node(created.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.content, "root")

    def test_get_node_returns_none_for_missing(self) -> None:
        from app.db import repo_dag

        result = repo_dag.get_node("nonexistent-id")
        self.assertIsNone(result)

    def test_create_and_get_path(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        root = repo_dag.create_node(idea_id=idea_id, content="root", parent_id=None)
        path = repo_dag.create_path(
            idea_id=idea_id,
            node_chain=[root.id],
            path_md="# Root\nroot content",
            path_json='{"node_chain": []}',
        )
        self.assertIsNotNone(path.id)
        self.assertEqual(path.node_chain, [root.id])

        latest = repo_dag.get_latest_path(idea_id=idea_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.id, path.id)

    def test_get_latest_path_returns_none_when_empty(self) -> None:
        from app.db import repo_dag

        idea_id = self._seed_idea()
        result = repo_dag.get_latest_path(idea_id=idea_id)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
