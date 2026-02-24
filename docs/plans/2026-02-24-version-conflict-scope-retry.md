# Scope Version-Conflict Retry & Apply_agent_update Double-Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除 scope 操作的 `IDEA_VERSION_CONFLICT` 硬失败（无 retry），并把 `apply_agent_update` 的单次 retry 升级为两次，覆盖 PRD 90s 窗口内的双重并发写场景。

**Architecture:**

- **T1**: `repo_scope.py` 中所有公开方法（bootstrap_draft / patch_draft / freeze_draft / new_version）在调用 `_update_idea_context()` 返回 `None`（conflict）时，重新读取最新 idea version 并重试一次。由于这四个方法在写库前已完成所有副作用（scope_baselines 表插入/更新），retry 仅需重跑 `_update_idea_context()`，不需要重跑业务逻辑，完全安全。
- **T2**: `repo_ideas.py` 的 `apply_agent_update` 把单次 retry 改为最多两次，覆盖 PRD 两阶段 ~90s 窗口内出现两次并发写的场景。

**Tech Stack:** Python, SQLite, FastAPI

---

## 背景：为什么这样设计

### Scope 操作的特殊性

```
bootstrap_draft / patch_draft / freeze_draft / new_version
  ├── _check_idea_guard()   ← 读 version，不匹配直接返回 conflict（无 retry）
  ├── <scope_baselines 表的写操作>   ← 已完成，不依赖 idea.version
  └── _update_idea_context()         ← 写 idea 表，WHERE version = expected_version
        如果 rowcount=0 → 返回 None → caller 返回 ScopeMutationResult(kind="conflict")
```

**两处失败点：**

1. `_check_idea_guard()`：在 `db_session()` 事务开头，读到 version 不对就直接退出，scope_baselines 什么都没写 → **safe to retry from scratch**
2. `_update_idea_context()`：scope_baselines 已写完，只剩 idea 上下文未更新 → **safe to retry only `_update_idea_context()`**

修复策略：

- 情况 1（`_check_idea_guard` 失败）：重新调用整个方法（因为 scope_baselines 尚未写入，幂等安全）。但实际上检查发生在事务内，scope_baselines 的写入在同一事务，一旦 guard 失败整个事务回滚，所以也是 safe to retry from scratch。
- 情况 2（`_update_idea_context` 失败）：直接在当前 connection 内重读 version 并重试，不需要重跑 scope_baselines 写入（同一事务内已完成）。

**最简实现**：在每个方法的 `_update_idea_context()` 返回 None 时，重读 idea 最新 version，用新 version 再调用一次 `_update_idea_context()`（connection 复用，同事务内）。

### apply_agent_update 双次 retry 必要性

PRD 两阶段生成约 90s。在此窗口内，正常用户操作可能触发两次 version bump：

1. Path summary background task 完成（T+15s）
2. 用户触发 scope 操作（T+50s）

单次 retry 只能覆盖一次冲突。把上限提升到 2 次可覆盖绝大多数实际场景，不存在无限循环风险（每次 retry 都读最新 version，只有第三方写再次抢先才会失败）。

---

## Task 1: repo_scope.py — 四个方法加 \_update_idea_context retry

**Files:**

- Modify: `backend/app/db/repo_scope.py`
- Test: `backend/tests/test_scope_repo.py`（新增测试类）

### Step 1: 查看现有 scope repo 测试

```bash
cat backend/tests/test_scope_repo.py | head -60
```

了解已有测试的 setUp 模式和 fixture 风格。

### Step 2: 写失败测试

在 `backend/tests/test_scope_repo.py` 末尾追加：

```python
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
        """bootstrap_draft succeeds even if version was bumped before its write."""
        idea = self.repo.create_idea(title="Scope Retry Test")
        v = idea.version

        # Simulate concurrent bump AFTER guard check but BEFORE _update_idea_context
        new_v = self._bump_version(idea.id, v)

        # bootstrap_draft is called with the original (stale) version
        result = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")
        self.assertIsNotNone(result.baseline)

    def test_freeze_draft_retries_on_conflict(self):
        """freeze_draft succeeds even if version was bumped before its write."""
        idea = self.repo.create_idea(title="Scope Retry Freeze")
        v = idea.version

        # Bootstrap a draft first (with correct version)
        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        v2 = r1.idea_version

        # Simulate concurrent bump
        new_v = self._bump_version(idea.id, v2)

        # freeze_draft called with stale v2
        result = self.scope.freeze_draft(idea.id, version=v2)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")

    def test_patch_draft_retries_on_conflict(self):
        """patch_draft succeeds even if version was bumped before its write."""
        from app.db.repo_scope import ScopeDraftItemInput
        idea = self.repo.create_idea(title="Scope Retry Patch")
        v = idea.version

        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        v2 = r1.idea_version

        new_v = self._bump_version(idea.id, v2)

        result = self.scope.patch_draft(
            idea.id,
            version=v2,
            items=[ScopeDraftItemInput(lane="in", content="Feature X")],
        )
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")

    def test_new_version_retries_on_conflict(self):
        """new_version succeeds even if version was bumped before its write."""
        idea = self.repo.create_idea(title="Scope Retry New Version")
        v = idea.version

        # Bootstrap + freeze to get a frozen baseline
        r1 = self.scope.bootstrap_draft(idea.id, version=v)
        self.assertEqual(r1.kind, "ok")
        assert r1.idea_version is not None
        r2 = self.scope.freeze_draft(idea.id, version=r1.idea_version)
        self.assertEqual(r2.kind, "ok")
        assert r2.idea_version is not None
        v3 = r2.idea_version

        new_v = self._bump_version(idea.id, v3)

        result = self.scope.new_version(idea.id, version=v3)
        self.assertEqual(result.kind, "ok", f"Expected ok, got {result.kind}")
```

### Step 3: 运行测试，确认失败

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_scope_repo.py::ScopeRepoVersionRetryTestCase -v 2>&1 | tail -20
```

Expected: 4 个测试均 **FAIL**（当前无 retry 逻辑）。

### Step 4: 实现 retry

在 `backend/app/db/repo_scope.py` 中修改 `_update_idea_context`，使其在 conflict 时重读最新 version 并重试一次：

```python
def _update_idea_context(
    connection: sqlite3.Connection,
    *,
    idea_id: str,
    expected_version: int,
    mutate_context: Callable[[DecisionContext], DecisionContext],
) -> int | None:
    row = _select_idea_row(connection, idea_id)
    if row is None:
        return None
    context = parse_context_strict(json.loads(str(row["context_json"])))
    next_context_model = mutate_context(context)
    next_context = next_context_model.model_dump(mode="python", exclude_none=True)
    next_stage = infer_stage_from_context(next_context_model)
    idea_seed_value = next_context.get("idea_seed")
    next_idea_seed = str(idea_seed_value) if isinstance(idea_seed_value, str) else None
    result = connection.execute(
        """
        UPDATE idea
        SET context_json = ?, stage = ?, idea_seed = ?, updated_at = ?, version = version + 1
        WHERE id = ? AND version = ?
        """,
        (
            json.dumps(next_context, ensure_ascii=False),
            next_stage,
            next_idea_seed,
            utc_now_iso(),
            idea_id,
            expected_version,
        ),
    )
    if result.rowcount == 0:
        # Version was bumped by a concurrent write. Re-read and retry once.
        # Safe: mutate_context is idempotent (only stamps new data into context fields).
        fresh_row = _select_idea_row(connection, idea_id)
        if fresh_row is None:
            return None
        fresh_version = int(fresh_row["version"])
        fresh_context = parse_context_strict(json.loads(str(fresh_row["context_json"])))
        fresh_next_model = mutate_context(fresh_context)
        fresh_next = fresh_next_model.model_dump(mode="python", exclude_none=True)
        fresh_stage = infer_stage_from_context(fresh_next_model)
        fresh_seed_val = fresh_next.get("idea_seed")
        fresh_seed = str(fresh_seed_val) if isinstance(fresh_seed_val, str) else None
        retry = connection.execute(
            """
            UPDATE idea
            SET context_json = ?, stage = ?, idea_seed = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND version = ?
            """,
            (
                json.dumps(fresh_next, ensure_ascii=False),
                fresh_stage,
                fresh_seed,
                utc_now_iso(),
                idea_id,
                fresh_version,
            ),
        )
        if retry.rowcount == 0:
            return None
        return fresh_version + 1
    return expected_version + 1
```

**Note:** The retry happens inside the same `db_session()` connection (SQLite single-writer, WAL mode). The scope_baselines writes already committed in prior statements within the same transaction — the context update is the last step.

### Step 5: 运行新测试，确认通过

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_scope_repo.py::ScopeRepoVersionRetryTestCase -v 2>&1 | tail -20
```

Expected: 4 个测试全部 **PASS**。

### Step 6: 运行完整 scope repo 测试，无回归

```bash
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_scope_repo.py -v 2>&1 | tail -20
```

Expected: 全部 **PASS**。

### Step 7: 验证导入

```bash
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  python -c "from app.db.repo_scope import ScopeRepository; print('OK')"
```

Expected: `OK`

### Step 8: Commit

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
git add backend/app/db/repo_scope.py backend/tests/test_scope_repo.py
git commit -m "fix: retry _update_idea_context in scope repo on version conflict

Scope operations (bootstrap/patch/freeze/new-version) now auto-retry
once when a concurrent write bumped idea.version between the guard
check and the final context write. Safe because mutate_context is
idempotent and scope_baselines writes are already complete."
```

---

## Task 2: repo_ideas.py — apply_agent_update 升级为最多两次 retry

**Files:**

- Modify: `backend/app/db/repo_ideas.py:214-240`
- Test: `backend/tests/test_ideas_repo.py`（扩展已有 ApplyAgentUpdateRetryTestCase）

### Step 1: 写失败测试

在 `backend/tests/test_ideas_repo.py` 的 `ApplyAgentUpdateRetryTestCase` 内追加：

```python
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
    )
    self.assertEqual(result.kind, "ok", f"Expected ok but got {result.kind}")
    assert result.idea is not None
    self.assertEqual(result.idea.version, v2 + 1)
```

### Step 2: 运行测试，确认失败

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py::ApplyAgentUpdateRetryTestCase::test_apply_agent_update_retries_twice_on_double_conflict -v 2>&1 | tail -15
```

Expected: **FAIL** — 目前只重试一次，双重冲突后返回 `conflict`。

### Step 3: 实现双次 retry

修改 `backend/app/db/repo_ideas.py` 的 `apply_agent_update`：

```python
def apply_agent_update(
    self,
    idea_id: str,
    *,
    version: int,
    mutate_context: Callable[[DecisionContext], DecisionContext],
) -> UpdateIdeaResult:
    result = self._update_context_internal(
        idea_id,
        version=version,
        mutate_context=mutate_context,
        require_not_archived=True,
    )
    # Retry up to 2 times when a concurrent write (e.g. /paths background task,
    # scope freeze) bumped the version while the LLM was running (~90s for PRD).
    # Safe because all mutate_context functions are idempotent.
    for _ in range(2):
        if result.kind != "conflict":
            break
        latest = self.get_idea(idea_id)
        if latest is None:
            break
        result = self._update_context_internal(
            idea_id,
            version=latest.version,
            mutate_context=mutate_context,
            require_not_archived=True,
        )
    return result
```

### Step 4: 运行所有 apply_agent_update 测试

```bash
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py::ApplyAgentUpdateRetryTestCase -v 2>&1 | tail -15
```

Expected: 4 个测试全部 **PASS**（含原有 3 个 + 新增 1 个）。

### Step 5: 运行完整 ideas repo 测试，无回归

```bash
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py -v 2>&1 | tail -20
```

Expected: 全部 **PASS**。

### Step 6: 验证导入

```bash
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  python -c "from app.db.repo_ideas import IdeaRepository; print('OK')"
```

Expected: `OK`

### Step 7: Commit

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
git add backend/app/db/repo_ideas.py backend/tests/test_ideas_repo.py
git commit -m "fix: increase apply_agent_update retry limit to 2 for long LLM windows

PRD generation takes ~90s. Two concurrent writes (e.g. path summary
background task + scope operation) can both land during that window.
Two retries covers the vast majority of real-world scenarios without
risk of infinite loops."
```

---

## Task 3: 重启后端，运行完整测试套件

### Step 1: 运行所有后端测试

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
PYTHONPATH=. UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/ -v --ignore=tests/test_api_ideas_and_agents.py 2>&1 | tail -30
```

Expected: 全部 **PASS**（忽略需要运行中服务器的集成测试）。

### Step 2: 重启后端

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 1
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin \
DECISIONOS_SEED_ADMIN_PASSWORD=admin \
UV_CACHE_DIR=../.uv-cache \
nohup uv run --python .venv/bin/python uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &
sleep 3 && curl -s http://127.0.0.1:8000/health
```

Expected: `{"ok":true}`

---

## 参考文件

| 文件                               | 改动                                         |
| ---------------------------------- | -------------------------------------------- |
| `backend/app/db/repo_scope.py`     | `_update_idea_context()` 加 retry（T1）      |
| `backend/app/db/repo_ideas.py`     | `apply_agent_update()` 单次→双次 retry（T2） |
| `backend/tests/test_scope_repo.py` | 新增 `ScopeRepoVersionRetryTestCase`（T1）   |
| `backend/tests/test_ideas_repo.py` | 新增双重冲突测试（T2）                       |
