# Multi-Agent + Memory System Hackathon Design

> **Date:** 2026-03-06
> **Goal:** Upgrade DecisionOS backend to showcase deep multi-agent orchestration, memory/learning system, and proactive agent capabilities for hackathon judging.
> **Timeline:** 3-5 days
> **Approach:** LangGraph orchestration layer on top of existing ai_gateway.py (Option C)

---

## 1. Architecture Overview

```
                         Frontend (Next.js)
                              |
                    SSE Events (agent thoughts,
                     progress, partials, done)
                              |
                    FastAPI SSE Endpoints
                              |
               +--------------+--------------+
               |                             |
         LangGraph Core                 Existing Routes
         (new orchestration)            (unchanged CRUD)
               |
    +----------+----------+----------+
    |          |          |          |
  Stage      Stage      Stage     Proactive
  Agents     Agents     Agents    Agents
  (Opp/      (Feas/     (PRD)     (News/Cross-
   DAG)       Scope)               Idea/Pattern)
    |          |          |          |
    +----------+----------+----------+
               |
         ai_gateway.py (UNCHANGED)
         (LLM calls via OpenAI-compatible API)
               |
    +----------+----------+
    |                     |
  LangGraph             LangGraph
  Checkpointer          Store
  (Thread State,        (Cross-idea memory,
   SQLite)               user patterns,
                         decision history)
               |
         ChromaDB / FAISS
         (Vector embeddings
          for RAG retrieval)
```

### Key Principle: Additive, Not Replacement

- `ai_gateway.py`, `prompts.py`, `schemas/` remain **unchanged**
- LangGraph is an **orchestration layer above** the existing LLM call layer
- Each LangGraph Node wraps a call to `ai_gateway.generate_structured()` or `ai_gateway.generate_text()`
- Existing non-streaming routes (`POST /agents/opportunity` etc.) continue to work
- New streaming routes use LangGraph's `astream_events` piped to SSE

---

## 2. LangGraph State Design

### 2.1 Thread State (per-session, auto-managed by Checkpointer)

```python
from langgraph.graph import MessagesState
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class DecisionOSState(TypedDict):
    # Core flow state
    idea_id: str
    idea_seed: str
    current_stage: str  # "opportunity" | "feasibility" | "scope" | "prd"

    # Accumulated outputs from each stage (reducers append, never overwrite)
    opportunity_output: dict | None
    dag_path: dict | None
    feasibility_output: dict | None
    selected_plan_id: str | None
    scope_output: dict | None
    prd_output: dict | None

    # Agent working memory (intermediate reasoning visible to frontend)
    agent_thoughts: Annotated[list[dict], add_messages]
    # Each thought: {"agent": "researcher", "action": "analyzing...", "detail": "..."}

    # Memory retrieval results (injected from Store at key nodes)
    retrieved_patterns: list[dict]    # from cross-idea analysis
    retrieved_similar_ideas: list[dict]  # from vector search
    user_preferences: dict | None     # from Store

    # Human-in-the-loop
    pending_human_input: str | None   # what we're waiting for
    human_response: str | None        # what the user provided
```

### 2.2 Store (cross-session, explicit read/write via LangGraph Store)

```
Namespace structure:
  users/{user_id}/preferences     -> user style preferences, detail level, domain focus
  users/{user_id}/patterns        -> learned decision patterns (e.g. "tends to choose bootstrapped plans")
  ideas/{idea_id}/summary         -> compressed idea summary for cross-idea retrieval
  ideas/{idea_id}/decisions       -> key decision points and outcomes
  ideas/{idea_id}/feedback        -> user feedback on generated outputs
  global/news_cache               -> recent news items matched to ideas
  global/cross_idea_insights      -> cross-idea analysis results
```

### 2.3 Vector Store (for RAG)

```
ChromaDB collections:
  idea_summaries    -> embedded summaries of all ideas (for cross-idea similarity)
  decision_patterns -> embedded decision histories (for pattern matching)
  news_items        -> embedded news articles (for proactive matching)
```

---

## 3. Multi-Agent Graph Topology

### 3.1 Core Decision Flow Graph

```
START
  |
  v
[ContextLoader] -- reads from Store: user_preferences, similar_ideas
  |
  v
[Router] -- routes to correct stage based on current_stage
  |
  +---> [OpportunitySubgraph]
  |         |
  |    [Researcher] -> analyze idea seed + retrieved context
  |         |
  |    [DirectionGenerator] -> generate opportunity directions
  |         |
  |    [Critic] -> self-evaluate and refine
  |         |
  |    [MemoryWriter] -> save idea summary to Store + vector DB
  |
  +---> [FeasibilitySubgraph]
  |         |
  |    [PlanGenerator x3] -> parallel plan generation (existing pattern)
  |         |
  |    [PlanSynthesizer] -> cross-evaluate plans, rank
  |         |
  |    [PatternMatcher] -> compare with historical decision patterns from Store
  |         |
  |    [MemoryWriter] -> save feasibility decisions
  |
  +---> [ScopeSubgraph]
  |         |
  |    [ScopeAnalyzer] -> generate scope from plan + context
  |         |
  |    [ScopeValidator] -> validate against similar ideas' scopes
  |
  +---> [PRDSubgraph]
            |
       [ContextAssembler] -> build PrdContextPack (existing logic)
            |
       [PRDWriter] -> generate markdown + sections
            |
       [PRDReviewer] -> self-review against scope and requirements
            |
       [MemoryWriter] -> save PRD pattern for future few-shot
  |
  v
[PersistNode] -- writes to SQLite via existing repo layer
  |
  v
END
```

### 3.2 Proactive Agent Graph (background, scheduled)

```
[Trigger] -- cron or on-demand
  |
  +---> [NewsMonitorAgent]
  |         |
  |    [NewsFetcher] -> fetch recent news (API or pre-seeded for demo)
  |         |
  |    [NewsAnalyzer] -> analyze relevance to user's ideas
  |         |
  |    [IdeaMatcher] -> vector similarity: news <-> idea_summaries
  |         |
  |    [NotificationWriter] -> generate insight + email notification
  |
  +---> [CrossIdeaAnalyzerAgent]
  |         |
  |    [IdeaCollector] -> load all user ideas from Store
  |         |
  |    [PatternDetector] -> find common themes, complementary ideas
  |         |
  |    [InsightGenerator] -> generate cross-idea insights
  |         |
  |    [MemoryWriter] -> save patterns to Store
  |
  +---> [UserPatternLearnerAgent]
            |
       [DecisionHistoryLoader] -> load all decisions from Store
            |
       [PatternExtractor] -> identify user's thinking patterns
            |
       [PreferenceUpdater] -> update user preferences in Store
```

### 3.3 Human-in-the-Loop (Interrupt Points)

LangGraph `interrupt()` is used at these decision points:

1. **After Opportunity generation** -> user confirms direction / picks path
2. **After Feasibility plans** -> user selects plan
3. **After Scope generation** -> user adjusts scope (drag-drop), freezes
4. **After PRD draft** -> user reviews, requests revision

These map to the existing frontend pages. The interrupt saves state via Checkpointer; user's next action resumes the graph.

---

## 4. Memory & RAG Integration

### 4.1 Memory Write Points (when data flows INTO Store)

| Event                     | What gets stored                       | Namespace                       |
| ------------------------- | -------------------------------------- | ------------------------------- |
| Opportunity generated     | Idea summary embedding + text          | `ideas/{id}/summary` + ChromaDB |
| User picks DAG path       | Path decision + reasoning              | `ideas/{id}/decisions`          |
| User selects plan         | Plan choice + alternatives considered  | `ideas/{id}/decisions`          |
| PRD generated             | PRD summary + generation pattern       | `ideas/{id}/summary`            |
| User gives feedback       | Rating + text                          | `ideas/{id}/feedback`           |
| Cross-idea analysis runs  | Detected patterns                      | `users/{id}/patterns`           |
| User interacts repeatedly | Style preferences (detail level, tone) | `users/{id}/preferences`        |

### 4.2 Memory Read Points (when data flows FROM Store into prompts)

| Stage       | What gets retrieved      | How it improves output                                                  |
| ----------- | ------------------------ | ----------------------------------------------------------------------- |
| Opportunity | Similar past ideas       | Avoids duplicate directions, references successful patterns             |
| Feasibility | Historical plan outcomes | "Users with similar ideas chose bootstrapped approach 70% of the time"  |
| Scope       | Similar ideas' scopes    | "Based on 3 similar projects, these features are commonly out-of-scope" |
| PRD         | Successful PRD examples  | Few-shot examples in prompt for consistent quality                      |

### 4.3 RAG Pipeline (per-node)

```python
# Inside a LangGraph Node:
async def researcher_node(state: DecisionOSState, store: BaseStore):
    # 1. Retrieve from vector DB
    similar = vector_db.query(state["idea_seed"], n_results=3)

    # 2. Retrieve from Store
    user_prefs = store.get(("users", user_id, "preferences"))
    past_patterns = store.get(("users", user_id, "patterns"))

    # 3. Inject into prompt context
    enriched_prompt = prompts.build_enriched_opportunity_prompt(
        idea_seed=state["idea_seed"],
        similar_ideas=similar,
        user_preferences=user_prefs,
        decision_patterns=past_patterns,
    )

    # 4. Call existing ai_gateway (UNCHANGED)
    result = ai_gateway.generate_structured(
        task="opportunity",
        user_prompt=enriched_prompt,
        schema_model=OpportunityOutput,
    )

    # 5. Emit agent thought (visible to frontend via SSE)
    thought = {
        "agent": "researcher",
        "action": "analyzed_context",
        "detail": f"Found {len(similar)} similar ideas, user prefers {user_prefs.get('style', 'detailed')} output",
    }

    return {"opportunity_output": result.model_dump(), "agent_thoughts": [thought]}
```

---

## 5. SSE Streaming: Agent Thoughts Visualization

### 5.1 New SSE Event Types

Existing: `progress`, `partial`, `done`, `error`

New events for agent visibility:

```
event: agent_thought
data: {"agent": "researcher", "action": "retrieving_similar_ideas", "detail": "Searching vector DB...", "pct": 10}

event: agent_thought
data: {"agent": "researcher", "action": "found_patterns", "detail": "Found 2 similar ideas: 'AI Writing Tool', 'Code Assistant'", "pct": 25}

event: agent_thought
data: {"agent": "critic", "action": "evaluating", "detail": "Checking direction consistency with user's preference for B2B focus", "pct": 60}

event: agent_thought
data: {"agent": "memory_writer", "action": "saving_pattern", "detail": "Saved idea summary to long-term memory", "pct": 90}

event: memory_insight
data: {"type": "similar_idea", "idea_title": "AI Writing Tool", "relevance": 0.87, "insight": "Both target developer productivity"}

event: done
data: {"idea_id": "...", "idea_version": 3, "data": {...}}
```

### 5.2 Frontend Agent Thought Panel

New component: `AgentThoughtStream` — a collapsible panel showing real-time agent activity:

```
+--------------------------------------------------+
| Agent Activity                              [^]  |
|--------------------------------------------------|
| > Researcher: Searching for similar ideas...     |
|   Found 2 matches (AI Writing Tool, Code Helper) |
| > Direction Generator: Creating 3 directions...  |
|   Using user preference: B2B focus               |
| > Critic: Evaluating direction quality...        |
|   Score: 8.5/10 - all directions are distinct    |
| > Memory: Saved idea summary to long-term memory |
+--------------------------------------------------+
```

This panel is shown alongside the existing UI during generation. It directly demonstrates multi-agent collaboration to judges.

---

## 6. Proactive Agent: News Monitor + Cross-Idea Analysis

### 6.1 News Monitor Flow (demo-ready with pre-seeded data)

**Backend:**

1. Pre-seed `news_items` ChromaDB collection with 20-30 tech news articles (embedded)
2. `NewsMonitorAgent` graph: fetch from collection -> match against user's ideas -> generate insights
3. Store matched insights in `global/news_cache` with idea associations
4. Create notification record in new `notifications` DB table

**API:**

```
GET  /notifications                -> list recent notifications
POST /notifications/{id}/dismiss   -> mark as read
POST /agents/news-scan             -> trigger news scan (for demo)
```

**Frontend:**

- Notification bell icon in header with badge count
- Dropdown shows: "We found a news article about [topic] that relates to your idea [Idea Title]"
- Click opens detail modal with the insight and suggested action

### 6.2 Cross-Idea Analysis Flow

**Backend:**

1. On each idea creation/update, embed idea summary in ChromaDB
2. `CrossIdeaAnalyzerAgent` graph: load all ideas -> pairwise similarity -> pattern detection
3. Generates insights like: "Ideas A and B share a common user persona — consider merging"
4. Stores insights in `global/cross_idea_insights`

**API:**

```
GET  /insights/cross-idea          -> list cross-idea insights
POST /agents/cross-idea-analysis   -> trigger analysis (for demo)
```

**Frontend:**

- New "Insights" section on Ideas list page
- Cards showing cross-idea relationships with visual connections
- "Your ideas 'AI Tutor' and 'Code Mentor' target the same persona (developers learning new tech)"

### 6.3 User Pattern Learning

**Backend:**

1. After each stage completion, log decision to Store
2. `UserPatternLearnerAgent`: analyze decision history -> extract patterns
3. Patterns feed back into prompts: "Based on your past decisions, you prefer bootstrapped approaches"

**Frontend:**

- "About You" section in Settings showing learned preferences
- "The system has learned: You tend to focus on B2B SaaS, prefer minimal MVP scope, value technical feasibility over market size"
- User can confirm/reject learned preferences

---

## 7. Database Changes

### 7.1 New Tables

```sql
-- Notification records for proactive agent alerts
CREATE TABLE IF NOT EXISTS notification (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    type TEXT NOT NULL CHECK (type IN ('news_match', 'cross_idea_insight', 'pattern_learned')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    read_at TEXT,
    created_at TEXT NOT NULL
);

-- Agent execution log (for tracing/debugging visualization)
CREATE TABLE IF NOT EXISTS agent_trace (
    id TEXT PRIMARY KEY,
    idea_id TEXT,
    graph_name TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);
```

### 7.2 Existing Tables: No Changes

`idea`, `workspace`, `idea_nodes`, `idea_paths`, `scope_baselines`, `ai_settings` — all unchanged.

### 7.3 LangGraph Checkpointer

Uses `langgraph-checkpoint-sqlite` for thread state persistence. Stored in same SQLite database file, separate tables managed by LangGraph.

---

## 8. Dependency Changes

### 8.1 New Python Dependencies

```
langgraph>=0.3.0
langchain-core>=0.3.0
langgraph-checkpoint-sqlite>=2.0.0
chromadb>=0.5.0
```

### 8.2 What We DON'T Add

- No `langchain` (full package) — only `langchain-core` (pulled by langgraph)
- No `langchain-openai` or `langchain-community` — we keep our own `ai_gateway.py`
- No external vector DB services — ChromaDB runs embedded (in-process)
- No email service SDK — email notification is mock/log for demo

---

## 9. File Structure (New/Modified)

```
backend/app/
  agents/                          # NEW: LangGraph agent layer
    __init__.py
    state.py                       # DecisionOSState TypedDict
    graphs/
      __init__.py
      decision_flow.py             # Main decision flow graph
      opportunity_subgraph.py      # Opportunity stage agents
      feasibility_subgraph.py      # Feasibility stage agents
      scope_subgraph.py            # Scope stage agents
      prd_subgraph.py              # PRD stage agents
      proactive/
        __init__.py
        news_monitor.py            # News monitoring agent graph
        cross_idea_analyzer.py     # Cross-idea analysis graph
        user_pattern_learner.py    # Pattern learning graph
    nodes/                         # Individual agent nodes
      __init__.py
      context_loader.py            # Loads from Store + vector DB
      researcher.py                # Research + RAG retrieval
      critic.py                    # Self-evaluation
      memory_writer.py             # Writes to Store + vector DB
      plan_synthesizer.py          # Cross-evaluates feasibility plans
      pattern_matcher.py           # Matches against historical patterns
    tools/                         # LangGraph tools
      __init__.py
      vector_search.py             # ChromaDB query tool
      store_ops.py                 # Store read/write operations
      news_fetch.py                # News API / pre-seeded data
    memory/
      __init__.py
      store_setup.py               # LangGraph Store configuration
      vector_store.py              # ChromaDB setup + embedding
      seed_data.py                 # Pre-seeded demo data
  routes/
    idea_agents.py                 # MODIFIED: new streaming routes using LangGraph
    notifications.py               # NEW: notification CRUD
    insights.py                    # NEW: cross-idea insights
  db/
    models.py                      # MODIFIED: add notification + agent_trace tables
    repo_notifications.py          # NEW
    repo_agent_trace.py            # NEW

frontend/
  components/
    agent/
      AgentThoughtStream.tsx       # NEW: real-time agent activity panel
      AgentThoughtBubble.tsx       # NEW: single thought bubble
    notifications/
      NotificationBell.tsx         # NEW: header notification icon
      NotificationDropdown.tsx     # NEW: notification list
      NotificationDetail.tsx       # NEW: detail modal
    insights/
      CrossIdeaInsights.tsx        # NEW: cross-idea insight cards
      UserPatternCard.tsx          # NEW: learned preferences display
  lib/
    sse.ts                         # MODIFIED: handle new event types (agent_thought, memory_insight)
```

---

## 10. Demo Script (for Hackathon Presentation)

### Scene 1: "The System Learns" (2 min)

1. Create Idea A: "AI-powered code review tool"
2. Show agent thought stream: Researcher analyzing, Critic evaluating, Memory saving
3. Create Idea B: "Developer productivity dashboard"
4. Show: "Found similar idea in memory: 'AI code review tool' — both target developers"
5. Show cross-idea insight notification

### Scene 2: "Deep Multi-Agent PRD Generation" (2 min)

1. Walk through Idea A to PRD stage
2. Show agent thought stream during PRD generation:
   - "Researcher: Retrieved 1 similar idea pattern from memory"
   - "PRD Writer: Generating sections using learned preference: detailed technical focus"
   - "PRD Reviewer: Cross-checking against scope... 2 suggestions incorporated"
   - "Memory Writer: Saved successful PRD pattern for future reference"
3. Show the PRD quality improvement narrative

### Scene 3: "Proactive Intelligence" (1 min)

1. Trigger news scan
2. Show notification: "News: 'GitHub launches AI code review feature' — this relates to your idea 'AI code review tool'. Consider: differentiate by focusing on security-specific reviews"
3. Show user pattern page: "You tend to prefer B2B SaaS, bootstrapped approach, technical feasibility > market size"

### Scene 4: "Architecture Deep Dive" (1 min)

1. Show LangGraph topology diagram (Mermaid rendered)
2. Show memory architecture diagram (Thread State + Store + Vector DB)
3. Show agent trace log: node execution times, token usage
4. Narrative: "Every agent decision is checkpointed — we can time-travel to any point"

---

## 11. Implementation Priority (3-5 Day Plan)

### Day 1: LangGraph Core + State

- Set up LangGraph with Checkpointer (SQLite)
- Implement DecisionOSState
- Wrap existing opportunity generation as first LangGraph graph
- Verify: existing SSE route works with LangGraph orchestration
- Add `agent_thought` SSE event emission

### Day 2: Memory System + RAG

- Set up ChromaDB (embedded)
- Implement Store namespaces
- Add ContextLoader node (reads from Store + vector DB)
- Add MemoryWriter node (writes to Store + vector DB)
- Implement memory read/write for Opportunity and Feasibility stages
- Seed demo data (5-10 pre-embedded idea summaries)

### Day 3: Multi-Agent Subgraphs + Proactive Agents

- Implement Critic and PlanSynthesizer nodes
- Implement CrossIdeaAnalyzerAgent graph
- Implement NewsMonitorAgent graph (pre-seeded news data)
- Add notification table + API routes
- Implement UserPatternLearnerAgent graph

### Day 4: Frontend Visualization

- Build AgentThoughtStream component
- Build NotificationBell + dropdown
- Build CrossIdeaInsights cards
- Build UserPatternCard in Settings
- Wire new SSE events to frontend

### Day 5: Demo Polish + Architecture Diagrams

- End-to-end demo walkthrough
- Fix edge cases and timing issues
- Create Mermaid architecture diagrams for presentation
- Prepare demo script with pre-seeded data
- Record backup demo video (in case of live demo failure)

---

## 12. Risk Mitigation

| Risk                                     | Mitigation                                                                                                            |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| LangGraph learning curve eats Day 1      | Fallback: wrap just PRD stage in LangGraph, keep others as-is. Even 1 stage with full multi-agent is enough for demo. |
| ChromaDB setup issues                    | Fallback: use in-memory dict with cosine similarity on sentence embeddings. Less impressive but functional.           |
| LLM calls too slow for multi-agent demo  | Pre-compute some agent outputs, cache in Store. Demo shows the flow; not every call needs to be live.                 |
| SSE event ordering issues with LangGraph | Buffer events in graph, emit in order at stage boundaries.                                                            |
| Demo data doesn't look convincing        | Spend 1-2 hours curating realistic demo ideas and news articles.                                                      |
| Run out of time before frontend          | Prioritize AgentThoughtStream (highest visual impact). Skip notifications/insights if needed — they're nice-to-have.  |

---

## 13. What We Show vs What's Real

| Feature                   | Real Implementation                         | Demo Enhancement                        |
| ------------------------- | ------------------------------------------- | --------------------------------------- |
| Multi-agent orchestration | Real LangGraph graphs with real nodes       | -                                       |
| Agent thought stream      | Real SSE events from LangGraph execution    | -                                       |
| Memory (Store)            | Real LangGraph Store with SQLite backend    | -                                       |
| Vector RAG                | Real ChromaDB with real embeddings          | Pre-seeded data                         |
| Cross-idea analysis       | Real vector similarity + LLM analysis       | Pre-seeded ideas                        |
| News monitoring           | Real LLM matching pipeline                  | Pre-seeded news articles (not live API) |
| Email notification        | Mock (log to console + in-app notification) | Show notification UI only               |
| User pattern learning     | Real pattern extraction from Store data     | Pre-seeded decision history             |
| Checkpoint time-travel    | Real LangGraph checkpointer                 | May not demo if time is short           |
