from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest


class DagDbTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        self._db_path = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database

        initialize_database()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_idea_nodes_table_exists(self) -> None:
        conn = sqlite3.connect(self._db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertIn("idea_nodes", tables)

    def test_idea_paths_table_exists(self) -> None:
        conn = sqlite3.connect(self._db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertIn("idea_paths", tables)

    def test_idea_nodes_columns(self) -> None:
        conn = sqlite3.connect(self._db_path)
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(idea_nodes)").fetchall()
        }
        conn.close()
        expected = {
            "id", "idea_id", "parent_id", "content",
            "expansion_pattern", "edge_label", "depth",
            "status", "created_at",
        }
        self.assertTrue(expected.issubset(cols), f"Missing columns: {expected - cols}")

    def test_scope_baselines_table_exists_with_expected_columns(self) -> None:
        conn = sqlite3.connect(self._db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("scope_baselines", tables)

        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(scope_baselines)").fetchall()
        }
        expected = {
            "id",
            "idea_id",
            "version",
            "status",
            "source_baseline_id",
            "created_at",
            "frozen_at",
        }
        self.assertTrue(expected.issubset(cols), f"Missing columns: {expected - cols}")

        index_names = {
            r[1]
            for r in conn.execute("PRAGMA index_list(scope_baselines)").fetchall()
        }
        conn.close()
        self.assertIn("idx_scope_baselines_idea_version_unique", index_names)

    def test_scope_baseline_items_table_exists_with_expected_columns_and_index(self) -> None:
        conn = sqlite3.connect(self._db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("scope_baseline_items", tables)

        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(scope_baseline_items)").fetchall()
        }
        expected = {
            "id",
            "baseline_id",
            "lane",
            "content",
            "display_order",
            "created_at",
        }
        self.assertTrue(expected.issubset(cols), f"Missing columns: {expected - cols}")

        index_names = {
            r[1]
            for r in conn.execute("PRAGMA index_list(scope_baseline_items)").fetchall()
        }
        conn.close()
        self.assertIn("idx_scope_baseline_items_order", index_names)


if __name__ == "__main__":
    unittest.main()
