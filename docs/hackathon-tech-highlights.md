# DecisionOS — AI 技术亮点说明

> 定位：面向 AI Hackathon 评委的技术深度说明，聚焦 RAG、Agent 架构、Memory 系统与 Context 管理。
>
> 评分维度对应：**技术前瞻（20分）** → 第一至六节 | **工具整合（15分）** → 第七至八节

---

## 一、Agent 架构：两类 LangGraph 图的设计分工

> 对应评分：技术前瞻 — Multi-Agent 深度融合，架构具前瞻性

DecisionOS 用 LangGraph 组织了两种不同模式的 Agent，这不是随意的分法，而是基于"状态是否跨想法共享"这一架构判断：

**类型 A：每想法工作流图（per-idea workflow）**

四个阶段（Opportunity / Feasibility / Scope / PRD）共享同一个 `DecisionOSState`——这是刻意的设计：共享状态让 `context_loader` 和 `memory_writer` 两个节点可以在四个阶段复用，不用重复实现。每个阶段触发后，前一阶段的输出（DAG 路径、选定的可行性方案、范围基线）已经存在于 State 中，直接被下一阶段的节点读取。

这意味着 PRD 生成时，AI 不是"从零开始"，而是站在用户前三步所有决策的肩膀上生成——这是跨节点、跨阶段的上下文传递，不是单轮 prompt。

**类型 B：主动后台图（proactive background）**

三个后台 Agent（News Monitor、Cross-Idea Analyzer、Pattern Learner）各自有独立 State 类型（`NewsMonitorState`、`CrossIdeaState`、`PatternLearnerState`），由 APScheduler 每 6 小时触发。它们跨用户、跨想法运行，不属于任何单个决策流，因此不共享 `DecisionOSState`。

这两种模式的并存体现了架构设计的清醒：per-idea 图强调状态积累与阶段传递，proactive 图强调跨想法的横向情报融合。两者通过 SQLite 和 ChromaDB 间接协同，而非直接耦合。

---

## 二、RAG：三层检索注入架构

> 对应评分：技术前瞻 — 高级 RAG，多源检索融合

每次 LangGraph 工作流启动，`context_loader` 节点在第一步执行三路检索，结果写入 State 供后续所有节点使用：

```python
# context_loader_node 核心逻辑（实际代码）
similar_ideas = vs.search_similar_ideas(query=idea_seed, n_results=3, exclude_id=idea_id)
patterns      = vs.search_patterns(query=idea_seed, n_results=3)
evidence      = retrieve_market_evidence_context(query=idea_seed)  # 市场证据，最多 800 tokens
```

**为什么是四个 Collection 而不是一个？**

把所有内容塞进单一 Collection 会导致检索混淆——新闻文章和竞品定位的语义空间不同，混合嵌入会拉低相似度精度。四个独立 Collection 保证了每次检索在语义上同质：

| Collection          | 存什么                                | 用于哪个阶段                            |
| ------------------- | ------------------------------------- | --------------------------------------- |
| `idea_summaries`    | 每个想法的文本摘要                    | 所有阶段：cross-idea 召回，避免重复方向 |
| `decision_patterns` | 可行性方案描述（每次生成后写入）      | PRD 阶段：注入历史策略偏好              |
| `news_items`        | HN 文章（title + content）            | News Monitor：用新闻文本反查相似想法    |
| `market_evidence`   | 竞品定位/功能/定价/评价、市场信号摘要 | Feasibility + PRD：外部市场上下文       |

全部使用余弦相似度（`hnsw:space: cosine`），ChromaDB 线程安全单例，支持持久化与内存两种模式（由 `DECISIONOS_CHROMA_PATH` 环境变量控制）。

**市场证据的 Token 预算管理（`evidence_retriever.py`）：**

```
检索 5 条
  → 超 800 tokens（约 3200 chars）？→ 降到 top-2
  → 仍超？→ 按字符截断每条（每条不超过 budget/2）
  → 最终 hard cap（3200 chars 强制截断）
```

这是明确的 context 预算控制——市场证据不能无限膨胀，否则会挤压 LLM 处理核心业务逻辑的空间。

**RAG 注入点——以 PRD 阶段为例（实际代码）：**

```python
# requirements_writer 节点（Stage-A 并行）
prompt = prompts.build_prd_requirements_prompt(context=slim_ctx)
if patterns:
    prompt += "\n\nUser decision patterns:\n" + ...  # 历史决策偏好（ChromaDB decision_patterns）
if evidence:
    prompt += "\n\n## Market Evidence\n" + evidence  # 竞品/市场信号（ChromaDB market_evidence）

# markdown_writer 节点（Stage-A 并行，与上方同时运行）
prompt = prompts.build_prd_markdown_prompt(context=slim_ctx)
if similar:
    prompt += "\n\nSimilar past ideas for reference:\n" + ...  # 相似想法（ChromaDB idea_summaries）
if evidence:
    prompt += "\n\n## Market Evidence\n" + evidence
```

两个并行节点注入的 RAG 内容有意差异化：`requirements_writer` 侧重决策模式和市场证据（影响需求方向），`markdown_writer` 侧重相似想法和市场证据（影响叙述角度）。

---

## 三、Memory：写入-读取的完整闭环

> 对应评分：技术前瞻 — 持续学习的记忆系统，AI 越用越懂用户

**写入时机（`memory_writer_node`，每个工作流结束时自动运行）：**

- **Opportunity 阶段完成** → 将想法种子 + 探索方向标题写入 `idea_summaries` Collection
- **Feasibility 阶段完成** → 将每个可行性方案（名称 + 摘要）写入 `decision_patterns` Collection，`pattern_id` 为 `{idea_id}-{plan_id}`

**读取时机（`context_loader_node`，每个工作流第一个节点）：**

- 检索 top-3 相似想法（余弦距离，排除当前 idea 自身）
- 检索 top-3 匹配决策模式
- 检索 top-5 市场证据 chunks（含 token 预算控制）

**长期偏好学习（Pattern Learner Agent）：**

Pattern Learner 不读向量库，而是读 SQLite 的 `decision_events` 表——这张表记录了用户每次的真实操作（确认 DAG 路径、选定方案、冻结范围、生成 PRD）。Agent 取最近 50 条（最多 30 条格式化进 prompt 避免 token 溢出），交给 LLM 提取 4 维偏好：

```
decision_history（SQLite decision_events，最近 50 条）
  → 格式化为文本（最多 30 条进 prompt，避免 token 溢出）
  → LLM 分析
  → {
      business_model_preference,  // e.g. "Bootstrapped, minimal investment"
      risk_tolerance,             // e.g. "Low — prefers incremental MVPs"
      focus_area,                 // e.g. "Developer tools and AI productivity"
      decision_style              // e.g. "Data-driven, iterative"
    }
  → 写入 SQLite user_preferences.learned_patterns_json
```

**增量缓存机制**：只在 `current_event_count`（传入时的真实 DB 事件数）与上次学习时不同时才重新调用 LLM，避免无意义的重复推理消耗。这是对"何时该重新学习"的显式工程判断，不是每次都跑。

---

## 四、Context 管理：PRD 阶段的 Slim Context 设计

> 对应评分：技术前瞻 — 有明显的 context 优化思考，信号密度优先于信息量

**问题**：PRD 有两个并行节点（`requirements_writer` + `markdown_writer`），两者都需要前三阶段的上下文，但完整的 `DecisionOSState` 包含大量无关字段（agent_thoughts 历史、所有中间结果等）。如果直接传整个 State，每个 LLM 调用都携带冗余信息，浪费 token 且降低信号密度。

**解法**：`context_loader` 在 PRD 阶段多做一步，从 State 中提取并压缩出 `prd_slim_context`：

```python
slim_ctx = {
    "idea_seed": ...,
    "confirmed_path_summary": dag_path.get("path_summary"),      # 来自 Step 2（DAG 确认）
    "leaf_node_content":      dag_path.get("leaf_node_content"),
    "selected_plan": {                                             # 来自 Step 3（可行性选择）
        "name", "summary", "score_overall", "recommended_positioning"
    },
    "in_scope":  scope.get("in_scope"),                           # 来自 Step 4（范围冻结）
    "out_scope": scope.get("out_scope"),
}
```

这个压缩后的字典通过 State 传给两个并行节点——它们只读 `prd_slim_context`，不读完整 State。SHA-256 指纹对 slim_ctx 做缓存校验，相同上下文不重复生成。

这是明确的 context 窗口管理，设计原则是：**给 LLM 的上下文应该是精炼的决策摘要，而不是原始数据的堆砌。**

---

## 五、并行 Agent 的 Fan-out / Fan-in（LangGraph Send）

> 对应评分：技术前瞻 — Multi-Agent 并行协同，LangGraph 高级原语的实际应用

PRD 图中用 `Send()` 实现真并行。`Send()` 是 LangGraph 的核心原语之一，允许从一个节点同时派发多个独立任务，各自持有完整的当前 State 副本，互不阻塞：

```python
# fan-out router（实际代码）
def _fan_out_to_parallel_writers(state: DecisionOSState) -> list[Send]:
    return [
        Send("requirements_writer", state),   # 生成 6-12 条结构化需求
        Send("markdown_writer", state),       # 生成 PRD 正文 + 6+ 章节
    ]

graph.add_conditional_edges(
    "context_loader",
    _fan_out_to_parallel_writers,
    ["requirements_writer", "markdown_writer"],
)

# fan-in：两个分支都 edge 到 backlog_writer，LangGraph 自动等待两者完成
graph.add_edge("requirements_writer", "backlog_writer")
graph.add_edge("markdown_writer", "backlog_writer")
```

**Fan-in 的语义**：LangGraph 在两个节点都写回 State 后才触发 `backlog_writer`。`backlog_writer` 读取 `state["prd_requirements"]`（来自 `requirements_writer`）里的 requirement ID 列表，生成与需求 ID 语义关联的 Backlog 条目——Backlog 不是独立凭空生成的，而是基于真实需求 ID 的下游输出，确保了需求与 Backlog 之间的语义一致性。

完整图拓扑：

```
START → context_loader
            ├─(Send)─► requirements_writer ─┐
            └─(Send)─► markdown_writer      ─┤ (fan-in，LangGraph 等两者均完成)
                                             └─► backlog_writer
                                                     └─► prd_reviewer（质量校验）
                                                             └─► memory_writer → END
```

`prd_reviewer` 节点做三项自动质检：markdown 长度 < 200 chars 报警、需求数 < 4 报警、范围条目是否在 PRD 正文中被提及（字符串匹配）。质检结果写入 `prd_review_issues`，通过 agent_thought SSE 事件实时推送到前端。

---

## 六、Cross-Idea Analyzer：向量 + 关系双路召回

> 对应评分：技术前瞻 — Hybrid Retrieval，超越纯向量相似度的复合评分设计

Cross-Idea Analyzer 的候选召回不是纯向量相似度，而是在向量基础上叠加了关系增益（`CrossIdeaCandidateService`）：

```python
# 复合评分公式（实际代码）
composite = similarity + (shared_competitors * 0.1) + (shared_signals * 0.05)
```

- `similarity`：ChromaDB 余弦距离转相似度（`1 - distance`）
- `shared_competitors`：两个想法关联了相同竞品实体 → 每个 +0.1
- `shared_signals`：两个想法关联了相同市场信号 → 每个 +0.05

**设计意图**：纯向量相似度只能捕捉语义表面的相似性，但两个想法如果面对同一个竞品（比如都在"对标 Notion"），它们的战略关联度远高于语义相似度能表达的。关系增益让评分体现了结构化知识（竞品图谱、市场信号关联）对语义检索的补充。

过滤掉 composite score ≤ 0.3 的弱候选后，构建 ≤ 1000 tokens 的比较上下文，送入 LLM 做结构化分析，输出 6 种洞察类型：

| 洞察类型               | 含义                           |
| ---------------------- | ------------------------------ |
| `merge_candidate`      | 两个想法高度重叠，建议合并     |
| `positioning_conflict` | 两个想法面向同一市场但定位冲突 |
| `execution_reuse`      | 两个想法的技术实现可以复用     |
| `shared_audience`      | 共同目标用户群                 |
| `shared_capability`    | 共同技术能力依赖               |
| `evidence_overlap`     | 共同市场信号支持               |

高置信度洞察（confidence ≥ 0.7）触发应用内通知，去重逻辑用规范化对顺序（`idea_a_id < idea_b_id`）+ fingerprint 保证幂等性。

---

## 七、Agent 决策链与工具整合可靠性

> 对应评分：工具整合 — 多步规划严密、有自主决策逻辑、非固定 API 堆砌、失败不崩溃

### 7.1 决策链：每个节点都在做判断，不是走流水线

DecisionOS 的 Agent 图不是"固定顺序调用 API"——每个节点读取前序结果，根据内容**动态决定自己的行为**：

**`context_loader` 节点：根据阶段动态扩展工作**

```python
# 仅在 PRD 阶段才额外构建 slim_context，其他阶段跳过
if stage == "prd":
    slim_ctx = { "idea_seed", "confirmed_path_summary", "selected_plan", "in_scope", "out_scope" }
    updates["prd_slim_context"] = slim_ctx
```

**`researcher` 节点：根据检索结果决定 prompt 内容**

```python
# 检索到相似想法 → 携带差异化建议；检索为空 → 明确告知 LLM "No similar ideas found"
if similar:
    analysis_parts.append(f"Found {len(similar)} similar ideas: {'; '.join(idea_titles)}")
else:
    analysis_parts.append("No similar ideas found in memory.")
```

**`plan_synthesizer` 节点：自主评估多方案，推荐最优**

```python
# 读取所有方案的 score_overall，自主排序，推荐最高分方案并输出推荐理由
sorted_plans = sorted(plans, key=lambda p: p.get("score_overall", 0), reverse=True)
best = sorted_plans[0]
detail = f"Recommended: '{best.get('name')}' (score: {best.get('score_overall')}). Key strength: {best.get('recommended_positioning')}"
```

**`backlog_writer` 节点：检查前置条件，缺失时自主跳过**

```python
# 若 requirements_writer 未产出有效 ID，自主决定跳过而非生成无效 backlog
if not requirement_ids:
    return {"prd_backlog_items": [], "agent_thoughts": [{"action": "skipped", "detail": "No requirement IDs available"}]}
```

**`pattern_matcher` 节点：检索后二次判断，更新或保留 State**

```python
# 有匹配结果才更新 retrieved_patterns，无结果时只记录 thought，不覆盖已有数据
if not patterns:
    return {"agent_thoughts": [{"action": "no_patterns_found", ...}]}
return {"retrieved_patterns": patterns, "agent_thoughts": [...]}
```

这五个例子共同说明：系统在每个节点都在基于当前 State 做判断，而不是无论输入如何都走相同路径。

---

### 7.2 任务拆解：从一个想法自动规划出多层子任务

以 PRD 阶段为例，用户只触发一次请求，系统自动完成以下任务拆解与编排：

```
用户请求：生成 PRD
    ↓ Agent 自动规划：
    1. context_loader   — 并发检索三路记忆（similar ideas / patterns / market evidence）
    2. requirements_writer + markdown_writer  — 并行拆解：需求与正文独立生成互不等待
    3. backlog_writer   — 依赖上游：读取需求 ID 生成关联 Backlog（非独立生成）
    4. prd_reviewer     — 自动质检：markdown 长度 / 需求数量 / scope 覆盖率三项校验
    5. memory_writer    — 持久化：将本次 PRD 模式写回向量存储供未来使用
```

整个链条中用户**零干预**，每一步的输入来自上一步的输出，最终结果是需求、文档、Backlog 三者语义一致的完整 PRD 包。

---

### 7.3 降级策略：失败不崩，每层都有兜底

**工具调用层（市场证据检索）**

```python
def retrieve_market_evidence_context(query: str) -> str:
    try:
        vs = get_vector_store()
        results = vs.search_market_evidence(query=query, n_results=5)
        return _format_evidence(results)
    except Exception:
        logger.warning("Market evidence retrieval failed — continuing without evidence")
        return ""   # 永远不抛出，生成流程不依赖外部数据源
```

下游节点检查返回值是否为空再决定是否注入 prompt：

```python
if evidence:   # 有证据才注入，空字符串不污染 prompt
    prompt += "\n\n## Market Evidence\n" + evidence
```

**后台 Agent 层（四个 Agent 互相隔离）**

```python
# scheduler.py — 每个 Agent 独立 try/except，一个失败不影响其余
try:
    graph = build_news_monitor_graph()
    result = await loop.run_in_executor(None, partial(graph.invoke, {...}))
except Exception:
    logger.warning("scheduler.news_monitor.failed", exc_info=True)
    # 继续执行 cross_idea_analyzer ...

try:
    graph = build_cross_idea_graph()
    ...
except Exception:
    logger.warning("scheduler.cross_idea.failed", exc_info=True)
    # 继续执行 pattern_learner ...
```

**Cross-Idea Analyzer 的局部失败处理**

```python
for entry in summaries:
    try:
        records = service.analyze_anchor_idea(idea_id, workspace_id)
    except Exception:
        logger.warning("failed to analyze idea %s", idea_id)
        continue   # 单个想法分析失败，跳过，继续处理下一个
```

**ChromaDB 空库防护**

```python
def search_similar_ideas(self, query, n_results=3, exclude_id=None):
    count = self._ideas.count()
    if count == 0:
        return []   # 向量库为空时直接返回，不发起无效查询
    fetch_n = min(fetch_n, count)   # 请求数不超过实际存量
    ...
```

---

### 7.4 结构化输出校验：防幻觉的完整链路

单靠 `response_format: json_object` 不够——许多免费或兼容层模型不遵守此字段。`ai_gateway.py` 实现三重保障：

**第一重：API 层** — 请求体携带 `response_format: {type: "json_object"}`（对支持的模型生效）

**第二重：Prompt 层** — 在用户 prompt 末尾注入完整 JSON Schema 字符串，兜底不支持 response_format 的模型：

```python
structured_prompt = (
    f"{user_prompt}\n\n"
    "IMPORTANT: Your response MUST be a valid JSON object only — "
    "no markdown, no code fences, no explanations.\n\n"
    f"JSON Schema (follow this exact structure): {schema_str}"
)
```

**第三重：解析层** — `_parse_json_from_content()` 处理 LLM 三种实际输出形态：

````python
# 形态 1：strip markdown 代码块（```json ... ```）
if text.startswith("```"):
    text = "\n".join(lines[1:-1]).strip()

# 形态 2：直接 json.loads
try:
    return json.loads(text)
except json.JSONDecodeError:
    pass

# 形态 3：从 prose 中提取第一个完整 JSON 对象（括号深度匹配算法）
start = text.find("{")
depth = 0
for i in range(start, len(text)):
    if text[i] == "{": depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            return json.loads(text[start:i+1])  # 提取成功
````

解析后 `schema_model.model_validate(raw)` 做 Pydantic 结构校验，字段类型不符抛出异常进入重试：

```python
for attempt in range(1, max_retries + 1):  # 最多 2 次重试
    try:
        raw = _invoke_provider(...)
        return schema_model.model_validate(raw)  # 成功即返回
    except Exception as exc:
        if attempt < max_retries:
            logger.warning("attempt=%d/%d FAILED (retrying)", attempt, max_retries)
            time.sleep(1)
        else:
            logger.error("attempt=%d/%d FAILED — giving up", attempt, max_retries)
raise last_exc
```

**多 Provider 无缝切换**

同一 `generate_structured()` 接口通过 `provider.kind` 路由，用户可在 Settings UI 切换，无需改代码：

| kind                | 协议                        | 典型 Provider                |
| ------------------- | --------------------------- | ---------------------------- |
| `openai_compatible` | OpenAI Chat Completions API | OpenRouter、本地模型、OpenAI |
| `anthropic`         | Anthropic Messages API      | Claude 系列                  |

---

## 八、前端 AI 体验工程

> 对应评分：工具整合 — Agent 决策可视化，SSE 实时流处理的工程细节

**SSE 事件流的前端处理**

后端定义了 7 种 SSE 事件类型，前端 `streamPost()` 对每种事件类型有独立处理路径：

| 事件            | 前端处理                                      |
| --------------- | --------------------------------------------- |
| `progress`      | 更新进度步骤 + 百分比，驱动 8 步状态机        |
| `agent_thought` | 推入 `AgentThoughtStream` 渲染队列            |
| `partial`       | Feasibility：每个方案完成即渲染，不等全部完成 |
| `requirements`  | PRD：需求批次就绪即渲染                       |
| `backlog`       | PRD：Backlog 条目就绪即渲染                   |
| `done`          | 触发 `loadIdeaDetail` 刷新完整上下文          |
| `error`         | toast 提示 + 解除 loading 状态                |

**AgentThoughtStream 的智能滚动**

不是简单的"有新内容就滚到底"——用户可能在阅读历史记录，强制滚动会打断体验：

```typescript
useEffect(() => {
  const container = scrollContainerRef.current
  if (!container) return
  const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
  // 只在用户已经接近底部（40px 内）时才自动滚动
  if (distanceFromBottom <= SCROLL_THRESHOLD_PX) {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }
}, [thoughts.length])
```

**PRD 页面的双重防重复触发**

React StrictMode 下 `useEffect` 会执行两次，加上用户可能快速切换页面，PRD 生成极易被重复触发导致双倍 LLM 调用：

```typescript
// 模块级 Set：跨组件实例去重
const globalPrdGenerationRequests = new Set<string>()

// 组件级 ref：组件内去重
const inFlightGenerationKeyRef = useRef<string | null>(null)

// 生成 key = JSON.stringify({ baseline_id, selected_plan_id, confirmed_path_id, retryNonce })
// 同一 key 的请求只允许一个在飞
if (globalPrdGenerationRequests.has(requestKey)) return
globalPrdGenerationRequests.add(requestKey)
```

注意 cleanup 函数中**不删除** `globalPrdGenerationRequests` 中的 key——删除在 `finally` 块中进行。如果在 cleanup 中删除，StrictMode 的第二次 Effect 执行会绕过这个锁。

**通知轮询的内存安全**

```typescript
const mountedRef = useRef(true)

// 轮询回调：只在组件仍挂载时 setState
const fetchNotifications = useCallback(async () => {
  const data = await getNotifications(true)
  if (mountedRef.current) {
    // 防止组件卸载后 setState 导致内存泄漏
    setNotifications(data)
  }
}, [])

// cleanup：标记卸载
useEffect(() => {
  mountedRef.current = true
  return () => {
    mountedRef.current = false
  }
}, [])
```

---

## 九、技术栈总览

| 层级       | 技术                                              | 关键设计决策                                        |
| ---------- | ------------------------------------------------- | --------------------------------------------------- |
| Agent 编排 | LangGraph（StateGraph + Send 并行 fan-out）       | 两类图模式：per-idea 共享状态 vs proactive 独立状态 |
| LLM 调用   | ai_gateway.py（OpenRouter / Anthropic）           | 三重防幻觉 + 括号匹配 JSON 提取 + 2 次重试          |
| 向量存储   | ChromaDB（4 Collections，余弦相似度）             | 语义同质分 Collection + Hybrid RAG 复合评分         |
| 结构化存储 | SQLite（权威源）                                  | ChromaDB 是可重建的语义缓存，不是主存储             |
| 后台调度   | APScheduler AsyncIOScheduler                      | 启动后 60s 首次运行（避免应用未就绪），每 6h 循环   |
| 实时推送   | Server-Sent Events（7 种事件类型）                | 前端 8 步状态机 + 双重防重复触发锁                  |
| 前端       | Next.js 14 App Router + TypeScript + Tailwind CSS | AgentThoughtStream 智能滚动 + mountedRef 内存安全   |
| 国际化     | next-intl                                         | 中英双语，语言切换器接入登录页和导航栏              |
