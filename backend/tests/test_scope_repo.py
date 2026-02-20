from __future__ import annotations

import os
import tempfile
import unittest


class ScopeRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "scope-repo-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path

        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database
        from app.db.repo_ideas import IdeaRepository
        from app.db.repo_scope import ScopeRepository

        initialize_database()
        self.idea_repo = IdeaRepository()
        self.scope_repo = ScopeRepository()
        self.idea = self.idea_repo.create_idea(title="Scope Repo Idea", idea_seed="seed")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_bootstrap_draft_creates_v1(self) -> None:
        result = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        self.assertEqual(result.kind, "ok")
        assert result.baseline is not None
        assert result.idea_version is not None
        self.assertEqual(result.idea_version, self.idea.version + 1)
        self.assertEqual(result.baseline.version, 1)
        self.assertEqual(result.baseline.status, "draft")
        self.assertEqual(result.baseline.items, [])

    def test_patch_draft_replaces_items_and_order(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        assert bootstrapped.idea_version is not None

        from app.db.repo_scope import ScopeDraftItemInput

        patch = self.scope_repo.patch_draft(
            self.idea.id,
            version=bootstrapped.idea_version,
            items=[
                ScopeDraftItemInput(lane="in", content="In Item 1"),
                ScopeDraftItemInput(lane="out", content="Out Item 1"),
                ScopeDraftItemInput(lane="in", content="In Item 2"),
            ],
        )
        self.assertEqual(patch.kind, "ok")
        assert patch.baseline is not None
        contents = [(item.lane, item.content, item.display_order) for item in patch.baseline.items]
        self.assertEqual(
            contents,
            [("in", "In Item 1", 0), ("out", "Out Item 1", 0), ("in", "In Item 2", 1)],
        )

    def test_freeze_draft_updates_context_pointer_and_bumps_version(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        assert bootstrapped.idea_version is not None

        frozen = self.scope_repo.freeze_draft(self.idea.id, version=bootstrapped.idea_version)
        self.assertEqual(frozen.kind, "ok")
        assert frozen.baseline is not None
        assert frozen.idea_version is not None
        self.assertEqual(frozen.baseline.status, "frozen")
        self.assertEqual(frozen.idea_version, bootstrapped.idea_version + 1)

        idea = self.idea_repo.get_idea(self.idea.id)
        assert idea is not None
        self.assertEqual(idea.context["current_scope_baseline_id"], frozen.baseline.id)
        self.assertEqual(idea.context["current_scope_baseline_version"], frozen.baseline.version)

    def test_new_version_creates_next_draft_from_latest_frozen(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        assert bootstrapped.idea_version is not None

        from app.db.repo_scope import ScopeDraftItemInput

        patched = self.scope_repo.patch_draft(
            self.idea.id,
            version=bootstrapped.idea_version,
            items=[
                ScopeDraftItemInput(lane="in", content="Keep this"),
                ScopeDraftItemInput(lane="out", content="Skip this"),
            ],
        )
        assert patched.idea_version is not None

        frozen = self.scope_repo.freeze_draft(self.idea.id, version=patched.idea_version)
        assert frozen.idea_version is not None
        assert frozen.baseline is not None

        new_version = self.scope_repo.new_version(self.idea.id, version=frozen.idea_version)
        self.assertEqual(new_version.kind, "ok")
        assert new_version.baseline is not None
        self.assertEqual(new_version.baseline.version, frozen.baseline.version + 1)
        self.assertEqual(new_version.baseline.status, "draft")
        self.assertEqual(new_version.baseline.source_baseline_id, frozen.baseline.id)
        self.assertEqual(
            [(item.lane, item.content) for item in new_version.baseline.items],
            [("in", "Keep this"), ("out", "Skip this")],
        )

    def test_patch_draft_with_stale_version_returns_conflict(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        self.assertEqual(bootstrapped.kind, "ok")

        from app.db.repo_scope import ScopeDraftItemInput

        stale = self.scope_repo.patch_draft(
            self.idea.id,
            version=self.idea.version,
            items=[ScopeDraftItemInput(lane="in", content="stale")],
        )
        self.assertEqual(stale.kind, "conflict")


if __name__ == "__main__":
    unittest.main()
