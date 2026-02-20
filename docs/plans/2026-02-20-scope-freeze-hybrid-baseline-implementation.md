# Scope Freeze Hybrid Baseline (Step 4) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Step4 重构为 Hybrid Baseline：Scope 可编辑草稿 + 冻结快照（baseline_id/version）+ PRD 只引用冻结基线，且修复当前 `Missing context for Scope Freeze` 阻塞问题。

**Architecture:** 采用后端持久化真源。`idea.context_json` 只保存当前 scope 指针与兼容字段，真正的冻结版本写入独立 `scope_baselines`/`scope_baseline_items`。前端 Scope 页面仅负责最小交互（删/增/拖拽排序/冻结/新版本），PRD 页通过 `baseline_id` 读取只读快照，保证生成稳定可追溯。

**Tech Stack:** FastAPI + Pydantic + SQLite + Next.js App Router + Zustand + dnd-kit + Zod + unittest/pytest + Vitest

---

## 0. 约束与执行编排

### 0.1 Non-Negotiables

- 所有 mutating API 必须携带 `version` 并做 CAS（optimistic locking）。
- `idea_id` 仅走 route，不放 request body 重复。
- 后端是持久化真源，前端 Zustand 只做 UI cache。
- 归档仍由 `idea.status` 管控，不新增并行归档语义。

### 0.2 协作方式（Collab + Subagents）

- Controller（当前会话）只做任务编排与验收，不直接“跨任务大改”。
- Implementer 子代理按任务执行，默认一次只拿一个任务。
- Reviewer 子代理独立存在，至少在两个检查点执行：
  - Backend phase 完成后
  - Frontend + E2E 回归后
- 若任务互不改同一文件，可并行：
  - 并行组 A：后端数据层（schema/repo）
  - 并行组 B：前端测试基建（Vitest）
  - Reviewer 不并行修改代码，只做审查。

### 0.3 外部 worktree 即将合并的低冲突策略

- 每个任务单独 commit，且 `git add` 只加任务内文件。
- 禁止全仓格式化、禁止无关 import 排序重写。
- 高冲突文件单独一提交：
  - `backend/app/db/models.py`
  - `frontend/components/scope/ScopeFreezePage.tsx`
  - `frontend/lib/idea-routes.ts`
- 本计划不处理冲突，只保证提交可 cherry-pick 与可回滚。

---

## 1. 目标 API/数据契约（先定 spec）

### 1.1 数据表（新增）

- `scope_baselines`
  - `id TEXT PK`
  - `idea_id TEXT NOT NULL FK idea(id)`
  - `version INTEGER NOT NULL`（同一 idea 内从 1 递增）
  - `status TEXT NOT NULL CHECK(status IN ('draft','frozen','superseded'))`
  - `source_baseline_id TEXT NULL`（由哪个 frozen 克隆）
  - `created_at TEXT NOT NULL`
  - `frozen_at TEXT NULL`
  - 唯一约束：`UNIQUE(idea_id, version)`
- `scope_baseline_items`
  - `id TEXT PK`
  - `baseline_id TEXT NOT NULL FK scope_baselines(id)`
  - `lane TEXT NOT NULL CHECK(lane IN ('in','out'))`
  - `content TEXT NOT NULL`
  - `display_order INTEGER NOT NULL`
  - `created_at TEXT NOT NULL`
  - 索引：`(baseline_id, lane, display_order)`

### 1.2 context_json（兼容）

在 `DecisionContext` 增加可选字段：

- `current_scope_baseline_id?: string`
- `current_scope_baseline_version?: number`

兼容期仍保留：

- `scope`
- `scope_frozen`

### 1.3 新增路由（idea-scoped）

- `GET /ideas/{idea_id}/scope/draft`
- `POST /ideas/{idea_id}/scope/draft/bootstrap`
- `PATCH /ideas/{idea_id}/scope/draft`
- `POST /ideas/{idea_id}/scope/freeze`
- `POST /ideas/{idea_id}/scope/new-version`
- `GET /ideas/{idea_id}/scope/baselines/{baseline_id}`

关键返回码：

- `404`：idea/baseline 不存在
- `409`：`IDEA_VERSION_CONFLICT`（CAS 失败）或 `IDEA_ARCHIVED`
- `422`：payload schema 不合法

### 1.4 PRD 入口约定

- 跳转时追加 `baseline_id` query：`/ideas/{ideaId}/prd?baseline_id=...`
- PRD 页面：
  - 有 `baseline_id` -> 只读加载该 baseline（推荐路径）
  - 无 `baseline_id` -> 允许用 draft，但显示警告条

---

## 2. 任务拆解（Spec -> TDD -> Implementation）

### Task 1: 修复当前 blocker（计划确认必须持久化）

**Files:**

- Modify: `frontend/components/feasibility/FeasibilityDetailClient.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/ideas-store.ts`
- Test: `backend/tests/test_api_ideas_and_agents.py`

**Step 1: 写失败测试（后端视角验证上下文可持久化 selected_plan_id）**

```python
# backend/tests/test_api_ideas_and_agents.py
# 新增: test_patch_context_persists_selected_plan_id
# 流程: create idea -> generate feasibility -> PATCH /ideas/{id}/context 写 selected_plan_id -> GET /ideas/{id}
# 断言: context.selected_plan_id 存在且 stage 进入 scope_freeze
```

**Step 2: 跑测试确认先失败**

- Run: `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_api_ideas_and_agents.py -k selected_plan_id -v`
- Expected: FAIL（当前前端未写入后端，测试需先暴露缺口）

**Step 3: 最小实现**

- Feasibility detail confirm 按钮改为：
  1. 先本地 `setPlan(plan.id)`
  2. 调 `patchIdeaContext(ideaId, { version, context: { ...context, selected_plan_id: plan.id } })`
  3. 用返回 detail 覆盖 `replaceContext` + `setIdeaVersion`
  4. 再跳转 scope-freeze
- 处理 `409 IDEA_VERSION_CONFLICT`：提示并 reload idea detail 重试。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_api_ideas_and_agents.py frontend/components/feasibility/FeasibilityDetailClient.tsx frontend/lib/api.ts frontend/lib/ideas-store.ts
git commit -m "fix(scope-entry): persist selected_plan_id before navigating to scope-freeze"
```

---

### Task 2: 后端 baseline schema（数据库层）

**Files:**

- Modify: `backend/app/db/models.py`
- Test: `backend/tests/test_dag_db.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_dag_db.py
# 新增断言:
# - scope_baselines 表存在
# - scope_baseline_items 表存在
# - constraints/index 存在（至少校验列和基本约束）
```

**Step 2: 跑测试确认失败**

- Run: `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_dag_db.py -k scope_baseline -v`
- Expected: FAIL

**Step 3: 最小实现**

- 在 `SCHEMA_STATEMENTS` 追加两张表与索引 SQL。
- 不改已有表字段，避免迁移风险。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/test_dag_db.py
git commit -m "feat(scope-baseline): add scope_baselines and scope_baseline_items tables"
```

---

### Task 3: Repo 层（baseline CRUD + CAS 协作）

**Files:**

- Create: `backend/app/db/repo_scope.py`
- Modify: `backend/app/db/repo_ideas.py`
- Test: `backend/tests/test_scope_repo.py` (new)

**Step 1: 写失败测试**

```python
# backend/tests/test_scope_repo.py
# 覆盖:
# 1) bootstrap_draft 创建 v1 draft
# 2) patch_draft 替换 items 并保持 display_order
# 3) freeze_draft -> frozen baseline + context pointer + version bump
# 4) new_version_from_frozen -> v2 draft
# 5) stale version -> conflict
```

**Step 2: 跑测试确认失败**

- Run: `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_scope_repo.py -v`
- Expected: FAIL

**Step 3: 最小实现**

- `repo_scope.py` 提供：
  - `get_draft(idea_id)`
  - `bootstrap_draft(idea_id, idea_version)`
  - `patch_draft(idea_id, idea_version, items)`
  - `freeze_draft(idea_id, idea_version)`
  - `new_version(idea_id, idea_version)`
  - `get_baseline(idea_id, baseline_id)`
- 所有 mutating 操作通过 `IdeaRepository.apply_agent_update` 或等价 CAS 更新 context/version。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/db/repo_scope.py backend/app/db/repo_ideas.py backend/tests/test_scope_repo.py
git commit -m "feat(scope-baseline): add repository layer with CAS-safe draft/freeze/version ops"
```

---

### Task 4: API 层（scope baseline endpoints）

**Files:**

- Create: `backend/app/routes/idea_scope.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/scope.py`
- Modify: `backend/app/schemas/ideas.py`
- Test: `backend/tests/test_scope_api.py` (new)

**Step 1: 写失败测试**

```python
# backend/tests/test_scope_api.py
# 覆盖:
# - GET draft 404 when absent
# - POST bootstrap returns draft
# - PATCH draft requires version and returns new idea_version
# - POST freeze returns baseline_id/version and sets readonly state
# - POST new-version clones latest frozen
# - GET baseline validates idea ownership
```

**Step 2: 跑测试确认失败**

- Run: `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_scope_api.py -v`
- Expected: FAIL

**Step 3: 最小实现**

- 新路由 `APIRouter(prefix="/ideas/{idea_id}/scope")`。
- response envelope 与现有 agent 风格对齐：`{ idea_id, idea_version, data }`（mutating routes）。
- 在 `backend/app/schemas/ideas.py` 的 `DecisionContext` 明确新增：
  - `current_scope_baseline_id: str | None = None`
  - `current_scope_baseline_version: int | None = None`
- 在 `frontend/lib/schemas.ts` 的 `decisionContextSchema` 同步新增：
  - `current_scope_baseline_id: z.string().optional()`
  - `current_scope_baseline_version: z.number().int().positive().optional()`
- `bootstrap` 来源优先级：
  1. 已有 draft -> 直接返回
  2. 最新 frozen -> clone
  3. context.scope -> 迁移成 draft
  4. 调 `llm.generate_scope`（需具备 confirmed path + feasibility + selected_plan）

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routes/idea_scope.py backend/app/main.py backend/app/schemas/scope.py backend/app/schemas/ideas.py backend/tests/test_scope_api.py
git commit -m "feat(scope-api): add draft/bootstrap/freeze/new-version/baseline endpoints"
```

---

### Task 5: Backend Phase Review（专用 reviewer 子代理）

**Files:**

- No code changes required by default

**Step 1: 收集差异范围**

- Run:

```bash
BASE_SHA=$(git rev-parse HEAD~4)
HEAD_SHA=$(git rev-parse HEAD)
echo "$BASE_SHA $HEAD_SHA"
```

**Step 2: 派发 reviewer 子代理（spec compliance）**

- 检查点：
  - 是否严格满足新增 API 与 CAS 约束
  - 是否存在 over-build（未在方案 B 要求内）

**Step 3: 派发 reviewer 子代理（code quality）**

- 检查点：
  - 事务边界、索引、异常码
  - 向后兼容（context.scope/scope_frozen）

**Step 4: 修复发现问题并复测**

- Run: `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_scope_repo.py tests/test_scope_api.py -v`

**Step 5: Commit（如有修复）**

```bash
git add <fixed-files>
git commit -m "chore(scope-api): address backend review findings"
```

---

### Task 6: 前端测试基建（Vitest + RTL）

**Files:**

- Modify: `package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/test/setup.ts`
- Dev dependency updates via `pnpm add -D`

**Step 1: 写失败测试（最小 smoke）**

```tsx
// frontend/components/scope/__tests__/scope-smoke.test.tsx
// render <ScopeFreezePage /> and assert guard placeholder text
```

**Step 2: 跑测试确认失败**

- Run: `pnpm test:web -- frontend/components/scope/__tests__/scope-smoke.test.tsx`
- Expected: FAIL（脚本/环境未配置）

**Step 3: 最小实现**

- 新增脚本：`"test:web": "vitest run --config frontend/vitest.config.ts"`
- 配置 jsdom + setup。
- 在 `frontend/test/setup.ts` 增加 `next/navigation` mocks（`useRouter/usePathname/useSearchParams`），避免组件渲染直接崩溃。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add package.json pnpm-lock.yaml frontend/vitest.config.ts frontend/test/setup.ts frontend/components/scope/__tests__/scope-smoke.test.tsx
git commit -m "test(frontend): setup vitest and RTL harness"
```

---

### Task 7: 前端 API/Schema 适配 baseline contract

**Files:**

- Modify: `frontend/lib/schemas.ts`
- Modify: `frontend/lib/api.ts`
- Test: `frontend/lib/__tests__/scope-api-contract.test.ts` (new)

**Step 1: 写失败测试**

```ts
// scope-api-contract.test.ts
// parse sample payload for draft/frozen baseline and ensure zod schemas accept
```

**Step 2: 跑测试确认失败**

- Run: `pnpm test:web -- frontend/lib/__tests__/scope-api-contract.test.ts`
- Expected: FAIL

**Step 3: 最小实现**

- 新增 schema：`ScopeBaseline`, `ScopeBaselineItem`, `ScopeDraftResponse`。
- 新增 API：
  - `getScopeDraft`
  - `bootstrapScopeDraft`
  - `patchScopeDraft`
  - `freezeScope`
  - `createScopeNewVersion`
  - `getScopeBaseline`

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/schemas.ts frontend/lib/api.ts frontend/lib/__tests__/scope-api-contract.test.ts
git commit -m "feat(frontend): add scope baseline schemas and API client"
```

---

### Task 8: Scope 页面重构（最简交互 + 持久化）

**Files:**

- Modify: `frontend/components/scope/ScopeFreezePage.tsx`
- Modify: `frontend/components/scope/ScopeBoard.tsx`
- Modify: `frontend/components/scope/ScopeColumn.tsx`
- Modify: `frontend/components/scope/ScopeItem.tsx`
- Test: `frontend/components/scope/__tests__/ScopeFreezePage.test.tsx` (new)

**Step 1: 写失败测试**

```tsx
// 覆盖:
// - 两栏渲染 in/out item
// - 新增一条、删除一条
// - 拖拽排序触发 onScopeChange
// - Freeze 后禁用编辑
// - Frozen 下点击编辑会提示 Create new version
```

**Step 2: 跑测试确认失败**

- Run: `pnpm test:web -- frontend/components/scope/__tests__/ScopeFreezePage.test.tsx`
- Expected: FAIL

**Step 3: 最小实现**

- 页面加载策略：
  - `GET draft`，若 404 则 `POST bootstrap`。
- 编辑策略：
  - 只允许三操作：新增/删除/拖拽排序。
  - 每次编辑 `PATCH draft`（可做 debounce）。
- 冻结策略：
  - `POST freeze` 后页面切只读，显示 `Baseline vN / frozen_at`。
  - 将 `baseline_id/version` 明确写回后端 context（`patchIdeaContext`）和本地 `replaceContext`，保证 hydration 后仍可读。
- 新版本策略：
  - `POST new-version`，返回 draft vN+1 并解锁编辑。
  - 同步更新 context 指针到新 draft baseline，避免 PRD 路由仍持有旧 baseline_id。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add frontend/components/scope/ScopeFreezePage.tsx frontend/components/scope/ScopeBoard.tsx frontend/components/scope/ScopeColumn.tsx frontend/components/scope/ScopeItem.tsx frontend/components/scope/__tests__/ScopeFreezePage.test.tsx
git commit -m "feat(scope-ui): rebuild scope freeze with hybrid baseline draft/freeze/new-version flow"
```

---

### Task 9: PRD 衔接 baseline_id（稳定引用）

**Files:**

- Modify: `frontend/lib/idea-routes.ts`
- Modify: `frontend/components/scope/ScopeFreezePage.tsx`
- Modify: `frontend/components/prd/PrdPage.tsx`
- Test: `frontend/components/prd/__tests__/PrdPageBaseline.test.tsx` (new)

**Step 1: 写失败测试**

```tsx
// 覆盖:
// - Scope页面 Continue 按钮带 baseline_id
// - PrdPage 读取 baseline_id 并调用 getScopeBaseline
// - 无 baseline_id 时显示 Draft warning
```

**Step 2: 跑测试确认失败**

- Run: `pnpm test:web -- frontend/components/prd/__tests__/PrdPageBaseline.test.tsx`
- Expected: FAIL

**Step 3: 最小实现**

- `buildIdeaStepHref` 增加可选 query 参数。
- Scope -> PRD 跳转带 `baseline_id`。
- PRD 页面优先使用 frozen baseline 数据生成；若无则 fallback draft + warning。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/idea-routes.ts frontend/components/scope/ScopeFreezePage.tsx frontend/components/prd/PrdPage.tsx frontend/components/prd/__tests__/PrdPageBaseline.test.tsx
git commit -m "feat(prd): consume baseline_id and prefer frozen baseline for generation"
```

---

### Task 10: 前端导航与 guard 回归

**Files:**

- Modify: `frontend/lib/guards.ts`
- Modify: `frontend/components/layout/AppShell.tsx`
- Test: `frontend/lib/__tests__/guards.scope-baseline.test.ts` (new)

**Step 1: 写失败测试**

```ts
// 覆盖:
// - canOpenScope 不依赖本地瞬态，基于后端已持久化字段
// - canOpenPrd 在 baseline 或 draft fallback 下行为正确
```

**Step 2: 跑测试确认失败**

- Run: `pnpm test:web -- frontend/lib/__tests__/guards.scope-baseline.test.ts`
- Expected: FAIL

**Step 3: 最小实现**

- Guard 逻辑与新 baseline 字段对齐。
- AppShell “done/open/locked” 状态改为基于 baseline + 冻结状态。

**Step 4: 跑测试确认通过**

- Run: 同 Step 2
- Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/guards.ts frontend/components/layout/AppShell.tsx frontend/lib/__tests__/guards.scope-baseline.test.ts
git commit -m "refactor(guards): align scope/prd guards with baseline-driven flow"
```

---

### Task 11: E2E 回归与文档同步

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`（仅必要更新）
- Create: `docs/plans/2026-02-20-scope-freeze-hybrid-baseline-runbook.md`

**Step 1: 写失败验收清单（手工或自动）**

- 场景：Idea Canvas -> Feasibility -> Confirm Plan -> Scope Freeze -> Freeze -> PRD
- 断言：
  - 不再出现 `Missing context for Scope Freeze`
  - 生成页读取冻结 baseline
  - `Create new version` 产生 v2，不影响 v1

**Step 2: 执行回归**

- Run (backend): `cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_scope_api.py tests/test_api_ideas_and_agents.py -v`
- Run (frontend): `pnpm lint:web && pnpm test:web`

**Step 3: 最小修复（如失败）**

- 只修复阻断项，不做额外重构。

**Step 4: 回归通过后更新文档**

- README 增加 Scope baseline 流程和 API 一览。
- AGENTS.md 同步 Step4 契约与 guard 条件。

**Step 5: Commit**

```bash
git add README.md AGENTS.md docs/plans/2026-02-20-scope-freeze-hybrid-baseline-runbook.md
git commit -m "docs(scope-baseline): add runbook and update architecture guardrails"
```

---

### Task 12: Final Review 子代理（必须）

**Files:**

- No default file edits

**Step 1: 获取审查范围**

```bash
BASE_SHA=$(git rev-parse HEAD~8)
HEAD_SHA=$(git rev-parse HEAD)
```

**Step 2: 派发 reviewer 子代理（spec）**

- 必查：
  - 是否完整实现方案 B（baseline_id/version + frozen readonly + new-version）
  - 是否保持 CAS 和 idea-scoped 约束

**Step 3: 派发 reviewer 子代理（quality）**

- 必查：
  - 回归风险（hydration、route query、version conflict）
  - 测试覆盖缺口

**Step 4: 修复审查问题并重跑关键验证**

- Run:

```bash
cd backend && UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python -m pytest tests/test_scope_api.py tests/test_scope_repo.py tests/test_api_ideas_and_agents.py -v
pnpm lint:web
pnpm test:web
```

**Step 5: Commit（如有修复）**

```bash
git add <fixed-files>
git commit -m "chore(scope-baseline): address final review findings"
```

---

## 3. 验收标准（Done Definition）

- 用户能完成：删除/新增/拖拽排序 -> Freeze -> PRD 引用 baseline。
- Freeze 后范围只读且可追溯；`Create new version` 产出 v2。
- PRD 默认引用 frozen baseline（若无 baseline，明确 warning）。
- 所有 mutating API 均有 version CAS；冲突返回 409。
- 修复当前 blocker：不再出现 `Missing context for Scope Freeze`（在已 confirm plan 场景）。

---

## 4. 实施顺序建议

1. 先做 Task 1（修 blocker，恢复主流程）。
2. 再做 Task 2-5（backend baseline contract 完整落地并 review）。
3. 然后 Task 6-10（frontend TDD + 页面重构 + PRD 接线）。
4. 最后 Task 11-12（回归与 final review）。
