# PRD Stream 启用、禁用 Reasoning、版本冲突修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 禁用 OpenRouter reasoning/thinking 模式以加快响应速度，恢复后端两阶段并行 PRD 生成（requirements + markdown 并行，再串行 backlog），重新接通前端 SSE 流式渲染（requirements / backlog 提前显示），并修复双重请求导致的 IDEA_VERSION_CONFLICT。

**Architecture:**

- `ai_gateway.py` 在发送 OpenAI-compatible 请求时增加 `include_reasoning: false`（OpenRouter 专用参数），阻止模型返回 thinking tokens，从而大幅缩短 TTFT 和总响应时间。
- `idea_agents.py` 中恢复被注释的两阶段并行逻辑：Stage A 并行调用 `generate_prd_requirements` + `generate_prd_markdown`，完成后立刻 SSE emit `requirements` 事件；Stage B 串行调用 `generate_prd_backlog`，完成后 emit `backlog` 事件。同时修复双重请求问题：在 event_generator 入口加一个数据库层面的分布式锁（使用已有的 optimistic locking 提前 reserve version）。
- `PrdPage.tsx` + `PrdView.tsx` 恢复被注释的 `requirements` / `backlog` 流式更新逻辑，前端在收到 SSE 事件后立刻渲染对应区块（Progressive UI）。

**Tech Stack:** FastAPI, sse-starlette, asyncio ThreadPoolExecutor, React, TypeScript, Zod

---

## 背景：已知问题清单

测试中发现的需要修复的问题：

| #   | 严重程度 | 描述                                                                                              |
| --- | -------- | ------------------------------------------------------------------------------------------------- |
| B1  | 高       | PRD 生成极慢：reasoning tokens 未关闭 + 并行生成被注释                                            |
| B2  | 高       | 双重请求触发 IDEA_VERSION_CONFLICT：前端重复发送 prd/stream（React StrictMode dev double-invoke） |
| B3  | 中       | PRD requirements / backlog 流式 SSE 事件在前端被注释，用户看不到渐进式结果                        |
| B4  | 低       | `/icon.svg` 500 错误（低优先级，本计划不处理）                                                    |
| B5  | 中       | Feasibility plan 详情链接全指向 plan1（本计划不处理）                                             |

---

## Task 1: 禁用 OpenRouter reasoning/thinking

**目的：** OpenRouter 上的某些模型（stepfun/step-3.5-flash:free 等）默认开启 extended thinking，会输出大量 reasoning tokens 导致响应极慢。加入 `include_reasoning: false` 可彻底禁用。

**Files:**

- Modify: `backend/app/core/ai_gateway.py:263-318`

### Step 1: 查看当前 `_call_openai_compatible_provider` 函数

```bash
grep -n "response_format\|temperature\|include_reasoning\|thinking" \
  backend/app/core/ai_gateway.py
```

Expected: 只有 `temperature` 和 `response_format`，没有 reasoning 相关字段。

### Step 2: 在两个请求体中加入 `include_reasoning: false`

在 `backend/app/core/ai_gateway.py` 中找到 `_call_openai_compatible_provider`，在 **第一次请求 body**（json_schema 模式，约第 264 行）和 **fallback body**（约第 303 行）中均加入：

```python
"include_reasoning": False,
```

具体修改（json_schema body，第 264-278 行）：

```python
body: dict[str, object] = {
    "model": model,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ],
    "temperature": provider.temperature,
    "include_reasoning": False,          # ← 新增：禁用 OpenRouter reasoning
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "decisionos_response",
            "schema": response_schema,
        },
    },
}
```

fallback body（第 303-310 行）：

```python
fallback_body: dict[str, object] = {
    "model": model,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": fallback_prompt},
    ],
    "temperature": provider.temperature,
    "include_reasoning": False,          # ← 新增：禁用 OpenRouter reasoning
}
```

同样在 `_invoke_provider_text`（第 82-89 行）也加入：

```python
body: dict[str, object] = {
    "model": provider.model or "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ],
    "temperature": provider.temperature,
    "include_reasoning": False,          # ← 新增
}
```

### Step 3: 验证后端能启动

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python python -c "from app.core import ai_gateway; print('OK')"
```

Expected: `OK`

### Step 4: 快速 curl 测试（用 expand 接口验证速度）

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 记录调用时间
time curl -s -N -X POST \
  "http://127.0.0.1:8000/ideas/d0cc5e99-d29c-4ea8-89bf-90025dc6cb18/nodes/f1066f0a-eb69-4e0f-b65b-ffdce347941f/expand/stream?pattern_id=narrow_users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  --max-time 30
```

Expected: 响应应在 5-10 秒内完成（之前需要 30+ 秒）。

### Step 5: Commit

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
git add backend/app/core/ai_gateway.py
git commit -m "perf: disable OpenRouter reasoning/thinking tokens to reduce latency"
```

---

## Task 2: 修复双重请求 IDEA_VERSION_CONFLICT

**目的：** React StrictMode 在开发模式下会 double-invoke effects，导致 `prd/stream` 被同时调用两次。第一个请求成功后版本号 +1，第二个请求因版本号已变而失败。

**Root Cause 确认：**

```
React StrictMode dev → useEffect 运行两次 → 两个并发 prd/stream 请求
→ 第一个 LLM 调用成功并写库（version: 9 → 10）
→ 第二个 LLM 调用完成后尝试写库（version: 9），WHERE version=9 找不到行 → conflict
```

**Fix 策略：** 在前端使用 `useRef` 标记运行状态，防止 effect 被重复触发。

**Files:**

- Modify: `frontend/components/prd/PrdPage.tsx`

### Step 1: 查看 PrdPage.tsx 中的 effect/run 逻辑

```bash
grep -n "useEffect\|useRef\|run\(\)\|streamPost\|retryNonce" \
  frontend/components/prd/PrdPage.tsx | head -30
```

### Step 2: 添加 `runningRef` 防重入保护

在 `PrdPage.tsx` 的 `run` 函数调用处，添加 ref 保护：

找到 `run` 函数定义（约第 80-160 行），在其外部加：

```typescript
const runningRef = useRef(false)
```

在 `run` 函数体的最开头加：

```typescript
if (runningRef.current) return // 防止并发重复调用
runningRef.current = true
```

在 `run` 函数的 `finally` 块（或末尾）加：

```typescript
runningRef.current = false
```

如果 `run` 是在 `useEffect` 内定义的，确保 effect cleanup 也重置：

```typescript
useEffect(() => {
  runningRef.current = false // reset on remount
  run()
  return () => {
    runningRef.current = false
  }
}, [retryNonce, ...deps])
```

### Step 3: 验证前端能构建

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
pnpm --filter frontend type-check 2>/dev/null || npx tsc --noEmit -p frontend/tsconfig.json
```

Expected: 无 TypeScript 错误。

### Step 4: Commit

```bash
git add frontend/components/prd/PrdPage.tsx
git commit -m "fix: prevent duplicate prd/stream requests in React StrictMode dev"
```

---

## Task 3: 恢复后端两阶段并行 PRD 生成

**目的：** 当前后端只生成 markdown（单步，~30s），被注释的两阶段并行逻辑（requirements + markdown 并行，再生成 backlog）本应是默认流程。恢复它。

**Files:**

- Modify: `backend/app/routes/idea_agents.py:395-546`

### Step 1: 查看被注释的代码范围

```bash
grep -n "COMMENTED\|# fut_req\|# fut_md\|# req_result\|# bl_result\|generate_prd_requirements\|generate_prd_backlog" \
  backend/app/routes/idea_agents.py | head -40
```

### Step 2: 恢复两阶段并行逻辑

在 `stream_prd` 的 `event_generator` 内，替换当前简化逻辑：

**当前（简化）代码**（大约第 460-490 行）：

```python
# 仅单步 markdown
yield _sse_event("progress", {"step": "generating_markdown", "pct": 35})
loop = asyncio.get_running_loop()
md_result = await loop.run_in_executor(None, llm.generate_prd_markdown, slim_ctx)
```

**替换为完整两阶段**：

```python
# ---- Stage A: 并行生成 requirements + markdown ----
yield _sse_event("progress", {"step": "generating_requirements", "pct": 15})
loop = asyncio.get_running_loop()
with ThreadPoolExecutor(max_workers=2) as pool:
    fut_req = loop.run_in_executor(pool, llm.generate_prd_requirements, slim_ctx)
    fut_md  = loop.run_in_executor(pool, llm.generate_prd_markdown,     slim_ctx)
    try:
        req_result, md_result = await asyncio.gather(fut_req, fut_md)
    except Exception as exc:
        _logger.exception("agent.prd.stream.stage_a.failed idea_id=%s", idea_id)
        yield _sse_event("error", {
            "code": "PRD_GENERATION_FAILED",
            "message": "Stage A generation failed",
        })
        return

# Stage A 完成：立刻推送 requirements，前端可以开始渲染
yield _sse_event("requirements", {
    "requirements": [r.model_dump() for r in req_result.requirements],
})

# ---- Stage B: 串行生成 backlog（依赖 Stage A 的 requirement IDs）----
yield _sse_event("progress", {"step": "generating_backlog", "pct": 60})
requirement_ids = [r.id for r in req_result.requirements]
try:
    bl_result = await loop.run_in_executor(
        None, llm.generate_prd_backlog, slim_ctx, requirement_ids
    )
except Exception as exc:
    _logger.exception("agent.prd.stream.stage_b.failed idea_id=%s", idea_id)
    yield _sse_event("error", {
        "code": "PRD_GENERATION_FAILED",
        "message": "Stage B backlog generation failed",
    })
    return

yield _sse_event("backlog", {
    "items": [item.model_dump() for item in bl_result.backlog.items],
})
```

同时确保 `PRDOutput` 合并了三个结果：

```python
merged_output = PRDOutput(
    markdown=md_result.markdown,
    sections=md_result.sections,
    requirements=req_result.requirements,
    backlog=bl_result.backlog,
    generation_meta=PRDGenerationMeta(
        provider_id=provider_id,
        model=model_name,
        confirmed_path_id=confirmed_path_id,
        selected_plan_id=selected_plan_id,
        baseline_id=baseline_id,
    ),
)
```

### Step 3: 验证后端能启动

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python python -c \
  "from app.routes.idea_agents import router; print('OK')"
```

Expected: `OK`

### Step 4: curl 端到端测试 prd/stream

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 获取一个已有 baseline 的 idea
IDEA_ID="d0cc5e99-d29c-4ea8-89bf-90025dc6cb18"
BASELINE_ID="2cab7fa5-69dd-4546-9dbe-6ef6b08a394f"
VERSION=$(curl -s "http://127.0.0.1:8000/ideas/$IDEA_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")

echo "Current version: $VERSION"

time curl -s -N -X POST \
  "http://127.0.0.1:8000/ideas/$IDEA_ID/agents/prd/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "{\"baseline_id\": \"$BASELINE_ID\", \"version\": $VERSION}" \
  --max-time 120
```

Expected: 先收到 `requirements` 事件，再收到 `backlog` 事件，最后 `done`。全程 < 60s。

### Step 5: Commit

```bash
git add backend/app/routes/idea_agents.py
git commit -m "feat(prd): restore two-stage parallel PRD generation (requirements + markdown parallel, then backlog)"
```

---

## Task 4: 恢复前端 SSE 流式渲染（Progressive UI）

**目的：** 恢复 PrdPage.tsx 和 PrdView.tsx 中被注释的 requirements / backlog 渐进式渲染逻辑。

**Files:**

- Modify: `frontend/components/prd/PrdPage.tsx`
- Modify: `frontend/components/prd/PrdView.tsx`

### Step 1: 查看 PrdPage.tsx 中被注释的 SSE 处理代码

```bash
grep -n "requirements\|backlog\|streamPartials\|COMMENTED\|event.event" \
  frontend/components/prd/PrdPage.tsx | head -30
```

### Step 2: 恢复 PrdPage.tsx 中的 `requirements` / `backlog` 事件处理

在 `onEvent` handler 中，恢复以下被注释的代码：

```typescript
onEvent: (event) => {
  if (cancelled) return

  if (event.event === 'requirements') {
    const data = event.data as { requirements: PrdOutput['requirements'] }
    setStreamPartials((prev) => ({
      ...prev,
      requirements: data.requirements,
    }))
  }

  if (event.event === 'backlog') {
    const data = event.data as { items: PrdOutput['backlog']['items'] }
    setStreamPartials((prev) => ({
      ...prev,
      backlog: { items: data.items },
    }))
  }

  if (event.event === 'done') {
    donePayload = event.data
  }
},
```

确认 `streamPartials` state 传给 `PrdView`（或相关子组件）。

### Step 3: 查看 PrdView.tsx 中被注释的 requirements/backlog 渲染

```bash
grep -n "requirements\|backlog\|streamPartials\|COMMENTED\|tab\|Tab" \
  frontend/components/prd/PrdView.tsx | head -40
```

### Step 4: 恢复 PrdView.tsx 中 requirements 和 backlog tab

找到 tab 切换区域，恢复 `Requirements` 和 `Backlog` 标签页：

```tsx
{/* Tab 按钮 */}
<button onClick={() => setActiveTab('prd')}>PRD</button>
<button onClick={() => setActiveTab('requirements')}>Requirements</button>
<button onClick={() => setActiveTab('backlog')}>Backlog</button>

{/* Requirements 内容区 */}
{activeTab === 'requirements' && (
  <div>
    {(streamPartials?.requirements ?? prd?.requirements ?? []).map((req) => (
      <div key={req.id}>
        <h3>{req.title}</h3>
        <p>{req.description}</p>
        <ul>
          {req.acceptance_criteria.map((ac, i) => (
            <li key={i}>{ac}</li>
          ))}
        </ul>
      </div>
    ))}
  </div>
)}

{/* Backlog 内容区 */}
{activeTab === 'backlog' && (
  <div>
    {(streamPartials?.backlog?.items ?? prd?.backlog?.items ?? []).map((item) => (
      <div key={item.id}>
        <h3>{item.title}</h3>
        <span>{item.priority}</span>
        <span>{item.type}</span>
        <p>{item.summary}</p>
      </div>
    ))}
  </div>
)}
```

注意：使用 `streamPartials?.requirements` 优先（流式中间值），`prd?.requirements` 次之（加载完成后的持久值）。

### Step 5: 验证 TypeScript 编译

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
npx tsc --noEmit -p frontend/tsconfig.json 2>&1 | head -30
```

Expected: 无错误（或只有与本次改动无关的既有错误）。

### Step 6: Commit

```bash
git add frontend/components/prd/PrdPage.tsx frontend/components/prd/PrdView.tsx
git commit -m "feat(prd): restore progressive SSE rendering for requirements and backlog tabs"
```

---

## Task 5: 端到端 Playwright 验证

**目的：** 走完整流程确认所有修复有效。

### Step 1: 确认服务都在运行

```bash
curl -s http://127.0.0.1:8000/health && echo " backend OK"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000 && echo " frontend OK"
```

### Step 2: 用 Playwright 验证 PRD 生成

通过浏览器（Playwright MCP）：

1. 访问 `http://127.0.0.1:3000/login`，用 `test/test` 登录
2. 进入已有 idea 的 PRD 页面（step 5 已完成的 idea）
3. 点击 Regenerate，观察：
   - 应先出现 Requirements tab 数据（在 backlog 之前）
   - 然后 Backlog tab 数据出现
   - 最终显示完整 PRD markdown
4. 全程应在 60 秒内完成（之前需要 120+ 秒）

### Step 3: 验证无 IDEA_VERSION_CONFLICT

观察浏览器 Console 和 toast，确认无 version conflict 错误出现。

### Step 4: 记录性能数据

在后端日志中查找实际耗时：

```bash
grep "prd/stream\|duration_ms" /tmp/backend.log | tail -10
```

Expected: `duration_ms` < 60000（60秒）

---

## 实施顺序说明

按 Task 1 → 2 → 3 → 4 → 5 顺序执行。每个 Task 都可独立验证，独立 commit。

Task 1 和 Task 2 互不依赖，可并行实施。
Task 3 依赖 Task 1（先禁用 reasoning，再启动并行生成，否则两个并行 LLM 调用都会慢）。
Task 4 依赖 Task 3（后端先要 emit requirements/backlog 事件，前端才有东西处理）。
Task 5 依赖所有前序 Task。

---

## 参考文件

| 文件                                  | 用途                                                         |
| ------------------------------------- | ------------------------------------------------------------ |
| `backend/app/core/ai_gateway.py`      | 禁用 reasoning（Task 1）                                     |
| `backend/app/routes/idea_agents.py`   | 两阶段并行 PRD 生成（Task 3）                                |
| `frontend/components/prd/PrdPage.tsx` | 防重复请求 + SSE 事件处理（Task 2 & 4）                      |
| `frontend/components/prd/PrdView.tsx` | Requirements / Backlog tab 渲染（Task 4）                    |
| `backend/app/core/llm.py`             | `generate_prd_requirements`, `generate_prd_backlog` 函数参考 |
| `backend/app/schemas/prd.py`          | PRDRequirementsOutput, PRDBacklogOutput schema 参考          |
