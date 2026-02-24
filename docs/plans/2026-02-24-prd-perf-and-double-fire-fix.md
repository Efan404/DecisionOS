# PRD 性能与双发请求修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除 PRD 生成时的重复 HTTP 往返（json_schema fallback）、修复生成完成后前端内容空白、修复 React StrictMode 导致的双发 SSE 请求。

**Architecture:**

- Task 1（后端）：`ai_gateway.py` 加模块级 `_json_schema_unsupported: set[tuple[str,str]]`，第一次 400 失败后记住该 provider+model 组合，后续直接走 plain-prompt fallback，无需任何 schema/DB 改动。
- Task 2（前端）：`PrdPage.tsx` 调整 `done` 事件处理顺序：先 `await loadIdeaDetail` + `replaceContext`，再 `setLoading(false)` + `setStreamPartials(null)`，消除数据未就绪就关 loading 导致的空白窗口。
- Task 3（前端）：新增 `next.config.ts`（3 行）关闭 `reactStrictMode`，消除开发环境双重 effect 触发根源；同时修 `PrdPage.tsx` cleanup，不在 cleanup 里删 `globalPrdGenerationRequests`，防止页面卸载再挂载时全局锁被误删。

**Tech Stack:** Python/FastAPI（后端），Next.js 14 App Router + React 18（前端），无新依赖。

---

## 根因速查

| 问题                         | 根因                                                                                                               | 文件                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------- |
| 每次 LLM 调用多一次无效 HTTP | `_call_openai_compatible_provider` 每次先试 json_schema，stepfun 模型永远 400                                      | `backend/app/core/ai_gateway.py`                         |
| 生成完成后前端空白           | `setLoading(false)` 在 `loadIdeaDetail` 完成前执行，streamPartials 被清空而 context 未更新                         | `frontend/components/prd/PrdPage.tsx:130-139`            |
| 双发 SSE 请求                | Next.js 14 默认开启 `reactStrictMode`，StrictMode 双重执行 effect 后立即 cleanup，cleanup 删掉全局锁导致第二次通过 | `frontend/next.config.ts`（新建），`PrdPage.tsx:162-167` |

---

## Task 1：后端 — json_schema 失败自动记忆，避免重复无效请求

**Files:**

- Modify: `backend/app/core/ai_gateway.py`

**Step 1: 定位现有 fallback 逻辑**

打开 `backend/app/core/ai_gateway.py`，找到函数 `_call_openai_compatible_provider`（约第 252 行）。
当前逻辑：每次都先用 `json_schema` response_format，失败后 warning + fallback。

**Step 2: 在模块顶部加缓存 set**

在 `logger = logging.getLogger(__name__)` 这行下方（约第 18 行），添加：

```python
# Tracks (provider_id, model) pairs that don't support json_schema response_format.
# Populated at runtime on first 400 failure; reset on process restart.
_json_schema_unsupported: set[tuple[str, str]] = set()
```

**Step 3: 修改 `_call_openai_compatible_provider`，跳过已知不支持的组合**

将现有函数体替换为以下逻辑（保持函数签名不变）：

```python
def _call_openai_compatible_provider(
    *,
    provider: AIProviderConfig,
    user_prompt: str,
    response_schema: dict[str, object],
) -> dict[str, object]:
    endpoint = provider.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    model = provider.model or "gpt-4o-mini"
    cache_key = (provider.id, model)

    # Only attempt json_schema if this (provider, model) hasn't failed before
    if cache_key not in _json_schema_unsupported:
        body: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": provider.temperature,
            "include_reasoning": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "decisionos_response",
                    "schema": response_schema,
                },
            },
        }
        logger.debug("_call_openai_compatible_provider url=%s model=%s (json_schema)", endpoint, model)
        try:
            decoded = _post_json(
                url=endpoint,
                body=body,
                timeout_seconds=provider.timeout_seconds,
                api_key=provider.api_key,
            )
            content = _extract_content_from_choices(decoded)
            return _parse_json_from_content(content)
        except Exception as exc:
            _json_schema_unsupported.add(cache_key)
            logger.warning(
                "_call_openai_compatible_provider json_schema failed (%s), "
                "caching as unsupported for %s/%s, retrying with plain prompt",
                exc, provider.id, model,
            )
    else:
        logger.debug(
            "_call_openai_compatible_provider skipping json_schema (cached unsupported) "
            "url=%s model=%s", endpoint, model,
        )

    # Fallback: plain prompt asking for JSON
    schema_str = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
    fallback_prompt = (
        f"{user_prompt}\n\n"
        "IMPORTANT: Your response MUST be a single valid JSON object only — "
        "no markdown, no code fences, no explanations, no text before or after the JSON. "
        f"Use exactly these field names as defined in this JSON Schema: {schema_str}"
    )
    fallback_body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": fallback_prompt},
        ],
        "temperature": provider.temperature,
        "include_reasoning": False,
    }
    logger.debug("_call_openai_compatible_provider url=%s model=%s (plain prompt fallback)", endpoint, model)
    decoded = _post_json(
        url=endpoint,
        body=fallback_body,
        timeout_seconds=provider.timeout_seconds,
        api_key=provider.api_key,
    )
    content = _extract_content_from_choices(decoded)
    return _parse_json_from_content(content)
```

**Step 4: 手动验证（无自动化测试，观察日志）**

重启后端进程，触发一次 PRD 生成，观察日志：

- 第一次调用应出现：`json_schema failed ... caching as unsupported`
- 后续调用应出现：`skipping json_schema (cached unsupported)`
- 不再出现多余的 400 warning

```bash
tail -f /tmp/backend.log | grep -E "json_schema|skipping"
```

**Step 5: Commit**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
git add backend/app/core/ai_gateway.py
git commit -m "perf(ai): cache json_schema-unsupported provider+model to skip redundant HTTP round-trip"
```

---

## Task 2：前端 — 修复 done 事件处理顺序，消除生成后空白

**Files:**

- Modify: `frontend/components/prd/PrdPage.tsx:130-139`

**Step 1: 定位问题代码**

打开 `frontend/components/prd/PrdPage.tsx`，找到 `run` 函数内 `if (!cancelled && donePayload)` 块（约第 130 行）：

```typescript
// 当前错误顺序：
if (!cancelled && donePayload) {
  const envelope = donePayload
  setIdeaVersion(activeIdeaId, envelope.idea_version)
  setLoading(false)                          // ← 1. loading 关掉
  const detail = await loadIdeaDetail(...)   // ← 2. 异步，还没完成
  if (detail) replaceContext(detail.context) // ← 3. context 才更新
  setRetryNonce(0)
  setStreamPartials({ requirements: null, backlog: null }) // ← 4. 清空
}
```

问题：step 1 执行后，`PrdView` 收到 `loading=false`，`streamPartials` prop 变为 `null`（因为 `loading ? streamPartials : null`），而 `context.prd_bundle` 还没更新，导致空白渲染。

**Step 2: 调整顺序**

将该块替换为：

```typescript
if (!cancelled && donePayload) {
  const envelope = donePayload
  setIdeaVersion(activeIdeaId, envelope.idea_version)
  // Load and apply context BEFORE turning off loading,
  // so PrdView sees prd_bundle populated when it re-renders.
  const detail = await loadIdeaDetail(activeIdeaId)
  if (!cancelled) {
    if (detail) {
      replaceContext(detail.context)
    }
    setRetryNonce(0)
    setStreamPartials({ requirements: null, backlog: null })
    setLoading(false)
  }
}
```

注意：在 `loadIdeaDetail` 完成后再检查一次 `cancelled`，防止组件已卸载时仍然 setState。

**Step 3: 验证**

启动前端开发服务器，触发 PRD 生成，等待完成，确认：

- 生成完成后内容直接显示，不需要手动刷新
- 控制台无 React state update on unmounted component 警告

**Step 4: Commit**

```bash
git add frontend/components/prd/PrdPage.tsx
git commit -m "fix(prd): load context before setLoading(false) to prevent blank flash after generation"
```

---

## Task 3：前端 — 关闭 StrictMode + 修 cleanup 防双发

**Files:**

- Create: `frontend/next.config.ts`
- Modify: `frontend/components/prd/PrdPage.tsx:162-167`（cleanup 函数）

**Step 1: 新建 `next.config.ts`**

在 `frontend/` 目录下创建 `next.config.ts`：

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  reactStrictMode: false,
}

export default nextConfig
```

这关闭了 Next.js 14 默认启用的 `reactStrictMode`，消除开发环境双重 effect 触发。

**Step 2: 修 cleanup — 不删全局锁**

打开 `frontend/components/prd/PrdPage.tsx`，找到 `useEffect` 的 return cleanup 函数（约第 162 行）：

```typescript
// 当前 cleanup（有问题）：
return () => {
  cancelled = true
  if (inFlightGenerationKeyRef.current === requestKey) {
    inFlightGenerationKeyRef.current = null
  }
  globalPrdGenerationRequests.delete(requestKey) // ← 问题：删掉全局锁让第二次通过
}
```

**问题**：StrictMode 触发 cleanup 时，把 `globalPrdGenerationRequests` 里的 key 删掉，第二次 effect 执行时全局锁已空，双发成功绕过。

将 cleanup 改为（不删 `globalPrdGenerationRequests`，只清组件内的 ref）：

```typescript
return () => {
  cancelled = true
  if (inFlightGenerationKeyRef.current === requestKey) {
    inFlightGenerationKeyRef.current = null
  }
  // Do NOT delete from globalPrdGenerationRequests here.
  // The set is cleaned up in the finally block of run().
  // Deleting here would allow a second effect (e.g. StrictMode) to bypass the guard.
}
```

**Step 3: 确认 `finally` 块仍然清理全局锁**

检查 `run()` 的 `finally` 块（约第 151-157 行）：

```typescript
} finally {
  if (inFlightGenerationKeyRef.current === requestKey) {
    inFlightGenerationKeyRef.current = null
  }
  globalPrdGenerationRequests.delete(requestKey)  // ← 正确位置，请求完成后才删
  setLoading(false)
}
```

确认 `globalPrdGenerationRequests.delete(requestKey)` 仍在 `finally` 里，确保请求真正完成后锁才释放。（`setLoading(false)` 在 Task 2 已移到 `done` 处理内，这里的 `setLoading(false)` 是错误路径兜底，保留。）

**Step 4: 验证**

重启 Next.js dev server，在 Network 面板观察 PRD 生成过程：

- 只应有一个 `/agents/prd/stream` 请求，不再有两个

```bash
# 或观察后端日志，只应有一条 agent.prd.stream.start
tail -f /tmp/backend.log | grep "agent.prd.stream"
```

**Step 5: Commit**

```bash
git add frontend/next.config.ts frontend/components/prd/PrdPage.tsx
git commit -m "fix(prd): disable StrictMode and fix cleanup to prevent double SSE request"
```

---

## 验收标准

1. 后端日志：第二次及以后的 LLM 调用不再出现 `json_schema failed` warning，改为出现 `skipping json_schema (cached unsupported)`
2. 前端：PRD 生成完成后内容立即展示，无需手动刷新
3. Network：每次 PRD 生成只有一条 `/agents/prd/stream` 请求
4. 无回归：feasibility stream、opportunity stream 正常工作
