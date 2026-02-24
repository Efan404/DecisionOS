# Agent Update Version-Conflict Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `apply_agent_update` 在乐观锁冲突时自动用最新 version 重试一次写库，消除正常并发操作下的 `IDEA_VERSION_CONFLICT` SSE 错误。

**Architecture:**
在 `IdeaRepository.apply_agent_update` 中，当 `_update_context_internal` 返回 `kind="conflict"` 时，立即重新读取数据库中的最新 idea 版本号，用该版本号再调用一次 `_update_context_internal`。此行为仅对 `apply_agent_update` 生效（即 LLM agent 写库场景），不影响普通的 `update_idea` 乐观锁语义。前提条件：调用方传入的 `mutate_context` 函数必须是幂等的（只写入新数据，不依赖旧 context 做 diff）——当前所有 `_apply_*` 函数均满足此条件。

**Tech Stack:** Python, SQLite, FastAPI, Pydantic

---

## 背景：问题根因

### 触发时序

```
用户在 DAG Canvas 点击 "Confirm Path"
  → POST /paths (idea.version: N → N+1)  ← 耗时约 6s（含 LLM summary）
  → router.push('/feasibility')           ← 立刻跳转

用户在 Feasibility 页面点击 "Generate Plans"
  → POST /feasibility/stream (payload.version = N)  ← 几乎同时发出
  → 入口版本检查：db.version 此时可能还是 N（/paths 未完成）→ 通过
  → 并行调用 3 个 LLM generate_single_plan（耗时 ~30s）
  → /paths 在 LLM 运行中途写库完成，version 变成 N+1
  → LLM 完成，apply_agent_update(version=N)
  → SQL: WHERE version=N → rowcount=0 → IDEA_VERSION_CONFLICT
```

### 为什么选择后端 retry 而不是前端串行化

| 方案                 | 问题                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------ |
| 前端串行化           | 只能防护"页面跳转触发"场景；用户在 LLM 运行中途切回 DAG 再改路径仍会触发；未来新的写操作都要单独加保护 |
| 前端静默忽略         | LLM 结果未落库，刷新后丢失，数据不一致                                                                 |
| 后端 retry（本方案） | 通用：覆盖所有 agent 写库场景；前提满足（`mutate_context` 幂等）；改动局限在一个函数                   |

### 为什么 mutate_context 是幂等的

当前所有 `_apply_*` 函数均只做"把新生成的 LLM output 写入 context 对应字段"，不读旧值做 diff，不累加，不依赖先前状态。因此用最新 version 的 context 重跑 mutate_context，结果完全等价。

---

## Task 1: 在 `apply_agent_update` 加 version-refresh retry

**Files:**

- Modify: `backend/app/db/repo_ideas.py:214-226`
- Test: `backend/tests/test_ideas_repo.py`

### Step 1: 阅读当前实现

```bash
sed -n '214,280p' backend/app/db/repo_ideas.py
```

确认 `apply_agent_update` 直接调用 `_update_context_internal`，后者在 `rowcount=0` 时返回 `UpdateIdeaResult(kind="conflict")`。

### Step 2: 写失败测试

在 `backend/tests/test_ideas_repo.py` 末尾追加以下测试类：

```python
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
        from app.schemas.context import DecisionContext
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
        from app.db.repo_ideas import IdeaRepository
        idea = self._make_idea()
        original_version = idea.version

        # 模拟"另一个并发操作"推进了 version（如 /paths 写库）
        bumped = self.repo.update_idea(
            idea.id,
            version=original_version,
            title="Bumped by concurrent op",
        )
        self.assertEqual(bumped.kind, "ok")
        assert bumped.idea is not None
        self.assertEqual(bumped.idea.version, original_version + 1)

        # apply_agent_update 仍用旧的 original_version，应自动 retry 并成功
        result = self.repo.apply_agent_update(
            idea.id,
            version=original_version,       # 过期版本
            mutate_context=self._noop_mutate(),
        )
        self.assertEqual(result.kind, "ok", f"Expected ok but got {result.kind}")
        assert result.idea is not None
        self.assertEqual(result.idea.version, original_version + 2)

    def test_apply_agent_update_returns_conflict_if_idea_deleted(self):
        """idea 不存在时，retry 后仍应返回 not_found，不崩溃。"""
        result = self.repo.apply_agent_update(
            "non-existent-id",
            version=1,
            mutate_context=self._noop_mutate(),
        )
        self.assertIn(result.kind, ("not_found", "conflict"))
```

### Step 3: 运行测试，确认失败

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py::ApplyAgentUpdateRetryTestCase -v 2>&1 | tail -20
```

Expected: `test_apply_agent_update_retries_on_version_conflict` **FAIL**（当前没有 retry 逻辑）。

### Step 4: 实现 retry 逻辑

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
    if result.kind == "conflict":
        # Version was advanced by a concurrent operation (e.g. /paths write)
        # while the LLM was running. Re-read the latest version and retry once.
        # Safe because all mutate_context functions are idempotent (they only
        # write new LLM output into context fields, never diff against old state).
        latest = self.get_idea(idea_id)
        if latest is not None:
            result = self._update_context_internal(
                idea_id,
                version=latest.version,
                mutate_context=mutate_context,
                require_not_archived=True,
            )
    return result
```

### Step 5: 运行测试，确认通过

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py::ApplyAgentUpdateRetryTestCase -v 2>&1 | tail -20
```

Expected: 3 个测试全部 **PASS**。

### Step 6: 运行完整 repo 测试套件，确认无回归

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  pytest tests/test_ideas_repo.py -v 2>&1 | tail -30
```

Expected: 所有已有测试仍然 **PASS**。

### Step 7: 验证模块可正常导入

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  python -c "from app.db.repo_ideas import IdeaRepository; print('OK')"
```

Expected: `OK`

### Step 8: Commit

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
git add backend/app/db/repo_ideas.py backend/tests/test_ideas_repo.py
git commit -m "fix: retry apply_agent_update on version conflict from concurrent writes

When an LLM agent finishes generation, a concurrent write (e.g. /paths)
may have already bumped the idea version. Re-read the latest version and
retry once. Safe because all mutate_context functions are idempotent."
```

---

## Task 2: 重启后端，手动验证

### Step 1: 重启后端

```bash
# Kill existing backend
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

# Start fresh
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin \
DECISIONOS_SEED_ADMIN_PASSWORD=admin \
UV_CACHE_DIR=../.uv-cache \
nohup uv run --python .venv/bin/python uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &

sleep 3
curl -s http://127.0.0.1:8000/health
```

Expected: `{"ok":true}`

### Step 2: 手动验证 feasibility 不再出现 VERSION_CONFLICT

1. 打开 `http://127.0.0.1:3001`
2. 进入一个 idea → Idea Canvas → 选择路径 → Confirm Path
3. 页面跳转到 Feasibility 后立刻点 Generate Plans
4. 观察后端日志：

```bash
strings /tmp/backend.log | grep -i "feasibility\|conflict" | tail -20
```

Expected: 看到 `agent.feasibility.stream.done`，**不再出现** `agent.feasibility.stream.failed ... IDEA_VERSION_CONFLICT`。

---

## 参考文件

| 文件                                | 用途                                                |
| ----------------------------------- | --------------------------------------------------- |
| `backend/app/db/repo_ideas.py`      | 核心修改：`apply_agent_update` retry 逻辑           |
| `backend/tests/test_ideas_repo.py`  | 新增 `ApplyAgentUpdateRetryTestCase`                |
| `backend/app/routes/idea_agents.py` | 所有调用 `apply_agent_update` 的 caller（不需改动） |
