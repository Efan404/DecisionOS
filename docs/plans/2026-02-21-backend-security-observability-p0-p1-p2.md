# Backend Security & Observability (P0/P1/P2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有多 idea 架构契约的前提下，完成后端 P0 限流、P1 异常脱敏、P2 日志基线建设，并补齐对应测试。

**Architecture:** 采用 FastAPI 中间件 + 路由级保护的增量改造方式：P0 使用应用内轻量级限流器（按路由类别和客户端 key），P1 在 DAG SSE 路由中返回固定错误语义并仅服务端记录细节，P2 引入统一 request/response 访问日志与关键异常日志，不改动业务 schema 与数据模型。

**Tech Stack:** FastAPI, Starlette middleware, Python logging, unittest/pytest (existing test harness)

---

## 修改边界（必须遵守）

- 仅修改 `backend/` 与 `docs/plans/`。
- 不改动前端、SQLite schema、idea/context 业务字段结构。
- 不引入外部基础设施（Redis / API Gateway）。限流先做单进程内实现，保留后续可替换点。
- 不改变已有 agent envelope 契约：普通 agent SSE 仍 `{ idea_id, idea_version, data }` done 语义，DAG SSE 仍 named events 且不 bump 版本。
- 所有新增错误码必须保持结构化 `detail.code/detail.message`（HTTP 路由）或 SSE `event:error` payload（DAG stream）。

## Sub-agent Ownership（并行执行）

- Agent A (P0 限流)
  - Owned files:
    - `backend/app/core/rate_limit.py` (new)
    - `backend/app/main.py`
    - `backend/app/core/settings.py`
    - `backend/tests/test_auth_api.py`
    - `backend/tests/test_api_ideas_and_agents.py`
  - 禁止修改 P1/P2 目标文件。

- Agent B (P1 异常信息脱敏)
  - Owned files:
    - `backend/app/routes/idea_dag.py`
    - `backend/tests/test_dag_api.py`
  - 禁止修改其他文件。

- Agent C (P2 日志基线)
  - Owned files:
    - `backend/app/core/logging_config.py` (new)
    - `backend/app/core/request_logging.py` (new)
    - `backend/app/main.py`
    - `backend/app/routes/idea_agents.py`
    - `backend/app/routes/ideas.py` (only if needed for key write-path logs)
    - `backend/tests/test_api_ideas_and_agents.py` (only新增日志相关测试)
  - 不得改动 P0 限流逻辑。

- Agent D (Review)
  - 只读 review：覆盖变更后的 `backend/app/**` 与 `backend/tests/**`。

## Task 1: P0 Rate Limiting（Agent A）

**Files:**

- Create: `backend/app/core/rate_limit.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/settings.py`
- Test: `backend/tests/test_auth_api.py`
- Test: `backend/tests/test_api_ideas_and_agents.py`

**Step 1: Write failing tests (auth login + AI endpoints rate limited)**

- `test_auth_api.py`: 连续多次 `/auth/login`（错误密码即可）应在阈值后返回 `429`，并带 `detail.code == "RATE_LIMITED"`。
- `test_api_ideas_and_agents.py`: 连续调用 `POST /ideas/{idea_id}/agents/opportunity` 在阈值后返回 `429`。

**Step 2: Run tests to verify RED**

Run:

```bash
cd backend && uv run -m pytest tests/test_auth_api.py tests/test_api_ideas_and_agents.py -k "rate_limit" -q
```

Expected: FAIL（当前没有限流）。

**Step 3: Implement minimal limiter**

- 在 `rate_limit.py` 实现内存窗口限流器：
  - key: `client_ip + route_group`。
  - route_group 最少覆盖：`auth_login`、`idea_agents_mutating`。
  - 默认阈值来自 settings（例如 login 更严格，agent 更宽松）。
- 在 `main.py` 注册中间件或依赖，命中时返回 429 + structured detail。
- `settings.py` 增加可选 env：
  - `DECISIONOS_RATE_LIMIT_LOGIN_PER_MINUTE`
  - `DECISIONOS_RATE_LIMIT_AGENT_PER_MINUTE`

**Step 4: Run targeted tests to verify GREEN**

Run:

```bash
cd backend && uv run -m pytest tests/test_auth_api.py tests/test_api_ideas_and_agents.py -k "rate_limit" -q
```

Expected: PASS。

**Step 5: Commit**

```bash
git add backend/app/core/rate_limit.py backend/app/main.py backend/app/core/settings.py backend/tests/test_auth_api.py backend/tests/test_api_ideas_and_agents.py
git commit -m "feat(backend): add in-app rate limiting for auth and agent endpoints"
```

## Task 2: P1 Exception Leakage Hardening（Agent B）

**Files:**

- Modify: `backend/app/routes/idea_dag.py`
- Test: `backend/tests/test_dag_api.py`

**Step 1: Write failing test (SSE error is sanitized)**

- patch `llm.generate_expand_nodes` 抛出包含敏感字样的异常（如 `"secret=abc123"`）。
- 调用 `/ideas/{idea_id}/nodes/{node_id}/expand/stream?pattern_id=...`。
- 断言 `event:error` 的 `message` 不包含内部异常文本，且 `code == "EXPAND_FAILED"`。

**Step 2: Run test to verify RED**

Run:

```bash
cd backend && uv run -m pytest tests/test_dag_api.py -k "expand_stream" -q
```

Expected: FAIL（当前返回 `str(exc)`）。

**Step 3: Minimal implementation**

- `idea_dag.py`：
  - 增加 `logger = logging.getLogger(__name__)`。
  - `except` 分支中 `logger.exception(...)` 记录异常。
  - SSE `error` payload 改为固定 message（例如 `"Expansion failed. Please retry."`）。

**Step 4: Run targeted tests to verify GREEN**

Run:

```bash
cd backend && uv run -m pytest tests/test_dag_api.py -k "expand_stream" -q
```

Expected: PASS。

**Step 5: Commit**

```bash
git add backend/app/routes/idea_dag.py backend/tests/test_dag_api.py
git commit -m "fix(backend): sanitize DAG stream errors and log internal exceptions"
```

## Task 3: P2 Logging Baseline（Agent C）

**Files:**

- Create: `backend/app/core/logging_config.py`
- Create: `backend/app/core/request_logging.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routes/idea_agents.py`
- Optional Modify: `backend/app/routes/ideas.py`
- Test: `backend/tests/test_api_ideas_and_agents.py`

**Step 1: Write failing tests (request id / baseline logging behavior)**

- 新增测试验证：响应带 `x-request-id`（或在 ASGI 测试可观测字段）且接口行为不变。
- 对关键错误路径（如 PRD generation failed）断言结构化错误保持不变。

**Step 2: Run tests to verify RED**

Run:

```bash
cd backend && uv run -m pytest tests/test_api_ideas_and_agents.py -k "request_id or prd" -q
```

Expected: 新增 request-id 断言先失败。

**Step 3: Minimal implementation**

- `logging_config.py`: 初始化统一日志格式（时间/级别/logger 名称/请求 id）。
- `request_logging.py`: HTTP middleware，记录 method/path/status/duration_ms，并生成或透传 `x-request-id`。
- `main.py`: 启动时初始化 logging + 注册 request logging middleware。
- `idea_agents.py`（及必要写路径）补关键结构化日志：
  - agent start/done/fail（含 `idea_id`、route、result kind）。
  - CAS conflict/archived/not_found 分支打 warning/info。

**Step 4: Run targeted tests to verify GREEN**

Run:

```bash
cd backend && uv run -m pytest tests/test_api_ideas_and_agents.py -q
```

Expected: PASS。

**Step 5: Commit**

```bash
git add backend/app/core/logging_config.py backend/app/core/request_logging.py backend/app/main.py backend/app/routes/idea_agents.py backend/app/routes/ideas.py backend/tests/test_api_ideas_and_agents.py
git commit -m "feat(backend): add request logging baseline and request id propagation"
```

## Task 4: Sub-agent Review + Integration（Agent D + Controller）

**Files:**

- Review all touched backend files

**Step 1: Spec compliance review**

- 检查是否满足 P0/P1/P2，不越界触碰 data model / API contract。
- 校验 AGENTS.md 约束：DAG SSE 格式未被破坏；agent mutating 路由 version/CAS 语义不变。

**Step 2: Code quality review**

- 重点看：并发安全（限流数据结构锁）、日志敏感信息脱敏、中间件性能影响。

**Step 3: Resolve conflicts centrally**

- 若 `main.py` 或测试文件冲突，由 controller 手工合并并保持两侧语义。

**Step 4: Final verification**

Run:

```bash
cd backend && uv run -m pytest tests/test_auth_api.py tests/test_dag_api.py tests/test_api_ideas_and_agents.py -q
```

Expected: PASS。

**Step 5: Squash not required; create final integration commit (if needed)**

```bash
git add <resolved-files>
git commit -m "chore(backend): integrate rate limit, error hardening, and logging baseline"
```

## 风险与回退

- 限流为单进程内存实现：多实例部署不共享计数，属已知限制；后续可替换为 Redis 令牌桶。
- SSE 脱敏后客户端失去细粒度错误文本：通过日志保留诊断能力。
- Request logging 可能增加日志量：默认 INFO，可通过运行时日志级别控制。

## 验收标准

- `/auth/login` 与 `/ideas/{idea_id}/agents/*` 在高频请求时返回 `429` 且错误结构稳定。
- `/ideas/{idea_id}/nodes/{node_id}/expand/stream` 的 `event:error` 不再泄露 `str(exc)`。
- 关键后端请求具备统一访问日志与 `x-request-id`。
- 指定测试集全部通过。
