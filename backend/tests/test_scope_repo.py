from __future__ import annotations

import os
import tempfile
import unittest

from tests._test_env import ensure_required_seed_env


class ScopeRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
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

    def test_bootstrap_returns_existing_draft_before_other_sources(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        assert bootstrapped.idea_version is not None
        assert bootstrapped.baseline is not None

        from app.db.repo_scope import ScopeDraftItemInput

        patched = self.scope_repo.patch_draft(
            self.idea.id,
            version=bootstrapped.idea_version,
            items=[ScopeDraftItemInput(lane="in", content="Existing Draft Item")],
        )
        self.assertEqual(patched.kind, "ok")
        assert patched.idea_version is not None
        assert patched.baseline is not None

        existing = self.scope_repo.bootstrap_draft(
            self.idea.id,
            version=patched.idea_version,
            items=[],
        )
        self.assertEqual(existing.kind, "ok")
        assert existing.idea_version is not None
        assert existing.baseline is not None
        self.assertEqual(existing.idea_version, patched.idea_version)
        self.assertEqual(existing.baseline.id, patched.baseline.id)
        self.assertEqual(
            [(item.lane, item.content) for item in existing.baseline.items],
            [("in", "Existing Draft Item")],
        )

    def test_bootstrap_without_items_clones_latest_frozen(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        assert bootstrapped.idea_version is not None

        from app.db.repo_scope import ScopeDraftItemInput

        patched = self.scope_repo.patch_draft(
            self.idea.id,
            version=bootstrapped.idea_version,
            items=[
                ScopeDraftItemInput(lane="in", content="Clone in"),
                ScopeDraftItemInput(lane="out", content="Clone out"),
            ],
        )
        assert patched.idea_version is not None

        frozen = self.scope_repo.freeze_draft(self.idea.id, version=patched.idea_version)
        self.assertEqual(frozen.kind, "ok")
        assert frozen.idea_version is not None
        assert frozen.baseline is not None

        cloned = self.scope_repo.bootstrap_draft(self.idea.id, version=frozen.idea_version)
        self.assertEqual(cloned.kind, "ok")
        assert cloned.idea_version is not None
        assert cloned.baseline is not None
        self.assertEqual(cloned.idea_version, frozen.idea_version + 1)
        self.assertEqual(cloned.baseline.status, "draft")
        self.assertEqual(cloned.baseline.version, frozen.baseline.version + 1)
        self.assertEqual(cloned.baseline.source_baseline_id, frozen.baseline.id)
        self.assertEqual(
            [(item.lane, item.content) for item in cloned.baseline.items],
            [("in", "Clone in"), ("out", "Clone out")],
        )

    def test_bootstrap_without_items_ignores_existing_context_scope(self) -> None:
        idea = self.idea_repo.get_idea(self.idea.id)
        assert idea is not None
        next_context = dict(idea.context)
        next_context["scope"] = {
            "in_scope": [
                {"id": "legacy-in-1", "title": "Legacy In", "desc": "keep", "priority": "P0"}
            ],
            "out_scope": [
                {
                    "id": "legacy-out-1",
                    "title": "Legacy Out",
                    "desc": "drop",
                    "reason": "not now",
                }
            ],
        }
        updated = self.idea_repo.update_context(
            self.idea.id,
            version=idea.version,
            context=next_context,
        )
        self.assertEqual(updated.kind, "ok")
        assert updated.idea is not None

        migrated = self.scope_repo.bootstrap_draft(self.idea.id, version=updated.idea.version)
        self.assertEqual(migrated.kind, "ok")
        assert migrated.baseline is not None
        self.assertEqual(
            [(item.lane, item.content) for item in migrated.baseline.items],
            [],
        )

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

    def test_freeze_rebuilds_scope_metadata_from_baseline(self) -> None:
        idea = self.idea_repo.get_idea(self.idea.id)
        assert idea is not None
        next_context = dict(idea.context)
        next_context["scope"] = {
            "in_scope": [
                {
                    "id": "legacy-in-keep",
                    "title": "Keep In Metadata",
                    "desc": "in-desc",
                    "priority": "P2",
                }
            ],
            "out_scope": [
                {
                    "id": "legacy-out-keep",
                    "title": "Keep Out Metadata",
                    "desc": "out-desc",
                    "reason": "out-reason",
                }
            ],
        }
        updated = self.idea_repo.update_context(
            self.idea.id,
            version=idea.version,
            context=next_context,
        )
        self.assertEqual(updated.kind, "ok")
        assert updated.idea is not None

        from app.db.repo_scope import ScopeDraftItemInput

        bootstrapped = self.scope_repo.bootstrap_draft(
            self.idea.id,
            version=updated.idea.version,
            items=[
                ScopeDraftItemInput(lane="in", content="Keep In Metadata"),
                ScopeDraftItemInput(lane="out", content="Keep Out Metadata"),
            ],
        )
        assert bootstrapped.idea_version is not None
        frozen = self.scope_repo.freeze_draft(self.idea.id, version=bootstrapped.idea_version)
        self.assertEqual(frozen.kind, "ok")

        latest = self.idea_repo.get_idea(self.idea.id)
        assert latest is not None
        scope = latest.context.get("scope")
        assert isinstance(scope, dict)
        in_scope = scope.get("in_scope")
        out_scope = scope.get("out_scope")
        assert isinstance(in_scope, list)
        assert isinstance(out_scope, list)
        self.assertEqual(in_scope[0]["title"], "Keep In Metadata")
        self.assertEqual(in_scope[0]["desc"], "")
        self.assertEqual(in_scope[0]["priority"], "P1")
        self.assertEqual(out_scope[0]["title"], "Keep Out Metadata")
        self.assertEqual(out_scope[0]["desc"], "")
        self.assertEqual(out_scope[0]["reason"], "")

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

    def test_patch_draft_with_stale_version_retries_once(self) -> None:
        bootstrapped = self.scope_repo.bootstrap_draft(self.idea.id, version=self.idea.version)
        self.assertEqual(bootstrapped.kind, "ok")

        from app.db.repo_scope import ScopeDraftItemInput

        # Version is 1 behind — the retry in _update_idea_context handles it.
        result = self.scope_repo.patch_draft(
            self.idea.id,
            version=self.idea.version,
            items=[ScopeDraftItemInput(lane="in", content="stale")],
        )
        self.assertEqual(result.kind, "ok")


class ScopeRepoVersionRetryTestCase(unittest.TestCase):
    """Verify that scope operations auto-retry once when idea.version was
    bumped by a concurrent operation between the guard check and the
    _update_idea_context() write."""

    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "decisionos-test.db")
        os.environ["DECISIONOS_DB_PATH"] = db_path
        from app.core.settings import get_settings

        get_settings.cache_clear()

        from app.db.bootstrap import initialize_database
        from app.db.repo_ideas import IdeaRepository
        from app.db.repo_scope import ScopeRepository

        initialize_database()
        self.repo = IdeaRepository()
        self.scope = ScopeRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _bump_version(self, idea_id: str, current_version: int) -> int:
        """Simulate a concurrent operation bumping idea.version."""
        result = self.repo.update_idea(
            idea_id, version=current_version, title="bumped", status=None
        )
        assert result.kind == "ok" and result.idea is not None
        return result.idea.version

    def test_bootstrap_draft_retries_on_conflict(self):
        idea = self.repo.create_idea(title="Scope Retry Test")
        v = idea.version
        self._bump_version(idea.id, v)
        result = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")
        self.assertIsNotNone(result.baseline)

    def test_freeze_draft_retries_on_conflict(self):
        idea = self.repo.create_idea(title="Scope Retry Freeze")
        v = idea.version
        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        v2 = r1.idea_version
        self._bump_version(idea.id, v2)
        result = self.scope.freeze_draft(idea.id, version=v2)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")

    def test_patch_draft_retries_on_conflict(self):
        from app.db.repo_scope import ScopeDraftItemInput

        idea = self.repo.create_idea(title="Scope Retry Patch")
        v = idea.version
        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        v2 = r1.idea_version
        self._bump_version(idea.id, v2)
        result = self.scope.patch_draft(
            idea.id,
            version=v2,
            items=[ScopeDraftItemInput(lane="in", content="Feature X")],
        )
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")

    def test_new_version_retries_on_conflict(self):
        idea = self.repo.create_idea(title="Scope Retry New Version")
        v = idea.version
        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        r2 = self.scope.freeze_draft(idea.id, version=r1.idea_version)
        self.assertEqual(r2.kind, "ok")
        assert r2.idea_version is not None
        v3 = r2.idea_version
        self._bump_version(idea.id, v3)
        result = self.scope.new_version(idea.id, version=v3)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")


if __name__ == "__main__":
    unittest.main()
