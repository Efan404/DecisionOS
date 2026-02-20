# AGENTS.md — DecisionOS Architecture Guardrails (v2)

本文件定义当前仓库的执行边界与架构约束。目标是把 DecisionOS 从单 idea 流程升级为单用户、单 workspace、多 ideas 的可持续产品底座。

## 1. Product Scope (Current)

- 用户模型：默认单用户。
- 工作区模型：默认单 workspace（系统自动创建 `default`）。
- 业务主体：`idea` 是一等实体，一个 workspace 下必须支持多个 ideas。
- 每个 idea 都有独立决策流程：
  - Idea Canvas
  - Feasibility
  - Scope Freeze
  - PRD

## 2. Non-Negotiable Architecture

### 2.1 Backend

- 必须使用 SQLite 做持久化（可迁移到 Postgres）。
- 必须有 `workspace` 与 `idea` 表；`idea` 存储完整 `context_json` 与 `version`。
- 所有 agent 能力都必须按 `idea_id` 作用域执行并落库。
- 所有写操作（包含 agent 生成）都必须做版本冲突保护（optimistic locking）。
- 保持 FastAPI + Pydantic，JSON/SSE 输出结构与前端 schema 对齐。
- 归档以 `status` 为唯一真源，`archived_at` 只做派生审计字段并保持一致性约束。

### 2.2 Frontend

- 不再以全局单例 `context` 作为最终真源。
- 前端必须有 idea 列表与 idea 切换能力。
- 决策页面必须是 idea-scoped 路由（`/ideas/[ideaId]/...`）。
- Zustand 可用于 UI cache，但后端是持久化真源。

## 3. Data Model Requirements

### Workspace

- `id`, `name`, `created_at`, `updated_at`

### Idea

- `id`, `workspace_id`, `title`, `idea_seed`
- `stage`, `status`
- `context_json`, `version`
- `created_at`, `updated_at`, `archived_at`

### IdeaNode (DAG Canvas)

- `id`, `idea_id`, `parent_id` (NULL = root)
- `content`, `expansion_pattern`, `edge_label`, `depth`
- `status` (`active` | `deleted`), `created_at`

### IdeaPath (Confirmed Decision Path)

- `id`, `idea_id`
- `node_chain` (JSON array of node ids, root → leaf)
- `path_md` (Markdown narrative, LLM context for Feasibility/PRD)
- `path_json` (structured JSON with node chain + AI summary)
- `created_at`

## 4. API Baseline

- `GET /ideas`
- `POST /ideas`
- `GET /ideas/{idea_id}`
- `PATCH /ideas/{idea_id}`
- `PATCH /ideas/{idea_id}/context`

约束：

- `GET /ideas` 固定排序 `updated_at DESC, id DESC`，cursor 格式必须稳定，`status` 过滤语义必须覆盖 `draft|active|frozen|archived`。
- `POST /ideas` 必须写入 canonical default context（含 schema version）。
- `PATCH /ideas/{idea_id}` 不接收独立 `archived` 布尔值，使用 `status` 统一控制归档，且必须携带 `version`。

Agent 路由必须迁移为 idea-scoped：

- `/ideas/{idea_id}/agents/opportunity`
- `/ideas/{idea_id}/agents/opportunity/stream`
- `/ideas/{idea_id}/agents/feasibility`
- `/ideas/{idea_id}/agents/feasibility/stream`
- `/ideas/{idea_id}/agents/scope`
- `/ideas/{idea_id}/agents/prd`

DAG canvas 路由（idea-scoped）：

- `GET /ideas/{idea_id}/nodes`
- `POST /ideas/{idea_id}/nodes`
- `GET /ideas/{idea_id}/nodes/{node_id}`
- `POST /ideas/{idea_id}/nodes/{node_id}/expand/user`
- `POST /ideas/{idea_id}/nodes/{node_id}/expand/stream`
- `POST /ideas/{idea_id}/paths`
- `GET /ideas/{idea_id}/paths/latest`

Agent 契约：

- `idea_id` 仅存在于 route，不在 request body 重复。
- mutating request 必须携带 `version`。
- response 使用固定 envelope：`{ idea_id, idea_version, data }`。
- SSE 仅在 `done` 事件落库并 bump 版本，`partial` 事件不落库；`done` 落库必须做 compare-and-swap（version 一致性检查）。

## 5. Vector Search Readiness (Reserved)

当前阶段不强制接入向量数据库，但必须预留：

- idea context 更新事件（例如 `IDEA_CONTEXT_UPDATED`）
- chunk 级文本抽取接口（seed/direction/plan/scope/prd）
- 未来语义检索接口占位（可先返回 501）

## 6. Execution Principles

- 小步提交，先保证数据模型与 API 稳定，再改 UI。
- 新功能优先补契约测试（schema + endpoint）。
- 若文档与代码冲突，以最新 `docs/plans/*multi-idea*` 设计文档为准并同步更新本文件。

## 7. Source of Truth Documents

- Architecture design: `docs/plans/2026-02-20-single-workspace-multi-idea-sqlite.md`
- Project readme: `README.md`
