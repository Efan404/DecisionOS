# Architecture Overview

This document covers the AI agent architecture, memory system, and proactive intelligence layer in DecisionOS.

> For project setup and usage, see [README.md](../README.md).

## Table of Contents

- [LangGraph Agent Architecture](#langgraph-agent-architecture)
- [Per-Idea Workflow Graphs](#per-idea-workflow-graphs)
- [Proactive Background Agents](#proactive-background-agents)
- [Memory & Vector Store](#memory--vector-store)
- [Notification System](#notification-system)
- [SSE Streaming Protocol](#sse-streaming-protocol)
- [AI Gateway](#ai-gateway)

---

## LangGraph Agent Architecture

DecisionOS uses [LangGraph](https://langchain-ai.github.io/langgraph/) to orchestrate all AI workflows. There are two categories of graphs:

| Category | State Type | Trigger | Purpose |
|----------|-----------|---------|---------|
| **Per-idea workflow** | `DecisionOSState` (shared) | User action (SSE stream) | Guides one idea through stages |
| **Proactive background** | Own state per agent | APScheduler (every 6h) | Cross-idea intelligence |

### Why Two State Patterns?

Per-idea graphs share `DecisionOSState` so that `context_loader` and `memory_writer` nodes can be reused across stages (opportunity, feasibility, scope, PRD). Proactive agents operate across users/ideas and have no overlap with per-idea workflow, so each defines its own lightweight state.

---

## Per-Idea Workflow Graphs

Each stage of the decision flow corresponds to a LangGraph graph:

```
Idea Canvas ──► Feasibility ──► Scope Freeze ──► PRD Generation
(opportunity)   (feasibility)   (scope)          (prd)
```

### Shared State: DecisionOSState

All per-idea graphs share this state type (`backend/app/agents/state.py`):

```
idea_id, idea_seed, current_stage
opportunity_output, dag_path, feasibility_output, selected_plan_id, scope_output, prd_output
prd_slim_context, prd_requirements, prd_markdown, prd_sections, prd_backlog_items, prd_review_issues
agent_thoughts (accumulates via operator.add)
retrieved_patterns, retrieved_similar_ideas, user_preferences
```

### Shared Nodes

- **`context_loader`** — Retrieves similar ideas and decision patterns from ChromaDB vector store. For PRD stage, also builds `prd_slim_context` shared by parallel writers.
- **`memory_writer`** — Persists generated outputs back to vector store. Opportunity stage writes idea summaries; feasibility writes plan descriptions as patterns.

### 1. Opportunity Graph

Explores initial idea directions via AI-generated alternatives.

```
START → context_loader → researcher → direction_generator → memory_writer → END
```

- **researcher**: Analyzes retrieved context (similar ideas + patterns)
- **direction_generator**: Calls LLM to generate 3-6 directions, each with title, one-liner, and pain tags
- **Output**: `OpportunityOutput` with `directions[]`

### 2. Feasibility Graph

Evaluates three implementation approaches concurrently via SSE streaming.

```
START → context_loader → plan_generator → plan_synthesizer → pattern_matcher → memory_writer → END
```

- **plan_generator**: Three sequential LLM calls, each with a different archetype hint:
  1. Bootstrapped / capital-light
  2. VC-funded / growth-first
  3. Platform / ecosystem / partner-led
- **plan_synthesizer**: Sorts plans by `score_overall`, emits ranking thought
- **Output**: `FeasibilityOutput` with 3 `Plan` objects (scores, reasoning, positioning)

Each plan streams to the frontend as it completes via SSE `partial` events, with skeleton placeholders for pending plans.

### 3. PRD Graph (Most Complex)

Generates structured PRD with true parallel fan-out via LangGraph's `Send()`:

```
START
  → context_loader
      ├─(Send)→ requirements_writer ─┐
      └─(Send)→ markdown_writer      ─┤ (fan-in)
                                      └─► backlog_writer
                                              └─► prd_reviewer
                                                  └─► memory_writer → END
```

**Two-stage generation:**

- **Stage A** (parallel): `requirements_writer` generates 6-12 requirements; `markdown_writer` generates full PRD narrative + 6+ sections. Both run concurrently.
- **Stage B** (sequential): `backlog_writer` reads requirement IDs from Stage A, generates 8-15 backlog items linked to requirements.
- **prd_reviewer**: Quality checks (markdown length, requirement count, scope coverage)

**Context assembly** (`_build_prd_context_pack`):
- Validates frozen scope baseline, confirmed DAG path, selected feasibility plan
- Assembles `PrdContextPack` with step2 (path), step3 (feasibility plan), step4 (scope items)
- SHA-256 fingerprint for cache validation

**Output**: `PRDOutput` with markdown, sections, requirements, backlog, and generation_meta.

---

## Proactive Background Agents

Three agents run automatically on a schedule, providing cross-idea intelligence without user intervention.

### Scheduler

Uses APScheduler (`AsyncIOScheduler`):
- **Startup**: Runs all 3 agents 60 seconds after app initialization
- **Recurring**: Runs every 6 hours

All agents execute sequentially within each run. Each agent's output is deduplicated before creating notifications.

### 1. News Monitor

Matches Hacker News stories to user's ideas via vector similarity.

**State**: `NewsMonitorState` — `{user_id, idea_summaries, notifications, agent_thoughts}`

```
START → load_ideas_for_topics → fetch_news → match_news_to_ideas → END
```

- **load_ideas_for_topics**: Loads all idea summaries from ChromaDB
- **fetch_news**: Extracts keywords from ideas, searches HN via Algolia API (`hn.algolia.com`), stores stories in ChromaDB `news_items` collection
- **match_news_to_ideas**: Vector similarity search between news and ideas. Cosine distance threshold: **0.35** (lower = more similar)
- **Deduplication**: `(news_id, idea_id)` composite key checked before notification insert
- **Notification type**: `news_match`

### 2. Cross-Idea Analyzer

Discovers strategic overlaps between user's ideas using vector similarity + LLM analysis.

**State**: `CrossIdeaState` — `{user_id, idea_summaries, insights, agent_thoughts}`

```
START → load_ideas → find_similar_pairs → END
```

- **load_ideas**: Loads all idea summaries from ChromaDB
- **find_similar_pairs**: For each idea, queries similar ideas (threshold: **0.40** cosine distance). For each match, calls LLM to explain the strategic overlap in 1-2 sentences. Deduplicates pairs via `frozenset({idea_a, idea_b})`.
- **Deduplication**: Order-independent `(idea_a_id, idea_b_id)` check
- **Notification type**: `cross_idea_insight`

### 3. Pattern Learner

Extracts user decision preferences from historical events using LLM analysis.

**State**: `PatternLearnerState` — `{user_id, current_event_count, decision_history, learned_preferences, agent_thoughts}`

```
START → load_history → extract_patterns → END
```

- **load_history**: Loads real decision events from `decision_events` table (up to 50). Event types: `dag_path_confirmed`, `feasibility_plan_selected`, `scope_frozen`, `prd_generated`
- **extract_patterns**: Formats history into text, calls LLM to extract preference JSON with keys:
  - `business_model_preference`
  - `risk_tolerance`
  - `focus_area`
  - `decision_style`
- **Persistence**: Saves to `user_preferences.learned_patterns_json` with `last_learned_event_count` for cache invalidation
- **Notification type**: `pattern_learned`

---

## Memory & Vector Store

### Architecture

```
SQLite (source of truth)          ChromaDB (semantic cache)
├── idea table (context_json)     ├── idea_summaries collection
├── decision_events               ├── news_items collection
├── user_preferences              └── decision_patterns collection
├── notification
└── agent_trace (schema only)
```

**SQLite** is the canonical source for all structured data. **ChromaDB** provides semantic similarity search and is non-critical — the app starts fine without it.

### ChromaDB Collections

| Collection | Purpose | Key Methods |
|-----------|---------|-------------|
| `idea_summaries` | Stores idea text for cross-idea matching | `add_idea_summary()`, `search_similar_ideas()` |
| `news_items` | Stores HN stories for news-to-idea matching | `add_news_item()`, `match_news_to_ideas()` |
| `decision_patterns` | Stores strategy patterns for context enrichment | `add_decision_pattern()`, `search_patterns()` |

All collections use cosine similarity. Vector store is a thread-safe singleton (`get_vector_store()`).

**Persistence**: Controlled by `DECISIONOS_CHROMA_PATH` env var:
- Directory path (default `./chroma_data`) → persistent via `PersistentClient`
- Empty string `""` → in-memory (used in tests)

### Decision Events

The `decision_events` table records every significant user decision as an audit trail:

| Event Type | Trigger | Payload |
|-----------|---------|---------|
| `dag_path_confirmed` | User confirms a DAG path | `{path_id, leaf_node_id}` |
| `feasibility_plan_selected` | User selects a plan | `{selected_plan_id, plan_name, score_overall}` |
| `scope_frozen` | User freezes scope baseline | `{baseline_id, version}` |
| `prd_generated` | PRD generation completes | `{baseline_id, fingerprint}` |

These events feed the Pattern Learner agent for preference extraction.

---

## Notification System

### Flow

```
Proactive Agent → Scheduler (dedup check) → notification table → Frontend (poll)
                                                                      ↓
                                                                Email (opt-in)
```

### Notification Types

| Type | Source Agent | Example |
|------|------------|---------|
| `news_match` | News Monitor | "HN: GitHub Copilot AI review expansion" matched to your code review idea |
| `cross_idea_insight` | Cross-Idea Analyzer | "Your meal-planning app and recipe platform share dietary personalization" |
| `pattern_learned` | Pattern Learner | "Updated preference profile: risk_tolerance=conservative" |

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/notifications` | List notifications (query: `unread_only`) |
| `POST` | `/notifications/{id}/dismiss` | Mark as read |
| `POST` | `/insights/news-scan` | Manually trigger news monitor |
| `POST` | `/insights/cross-idea-analysis` | Manually trigger cross-idea analyzer |
| `POST` | `/insights/learn-patterns` | Manually trigger pattern learner |
| `GET` | `/insights/user-patterns` | Fetch learned patterns |

### Frontend

- **NotificationBell**: Polls every 30s, shows unread count badge, per-notification dismiss
- **CrossIdeaInsights**: Manual trigger + insight display with HoverCards
- **UserPatternCard**: 3-column grid showing learned preferences (e.g., `risk_tolerance: conservative`)

### Email Dispatch

Optional email notifications for opted-in users:
- Configured via `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`
- Users opt-in per notification type via Profile page (`notify_enabled` + `notify_types`)
- Graceful degradation: silently skips if SMTP not configured

---

## SSE Streaming Protocol

All LLM-powered workflows use Server-Sent Events for real-time progress:

### Event Types

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{step, pct}` | Workflow stage transitions |
| `agent_thought` | `{agent, thought}` | Each LangGraph node emits activity |
| `partial` | Plan object | Feasibility: each plan as it completes |
| `requirements` | `{requirements: [...]}` | PRD: requirements batch ready |
| `backlog` | `{items: [...]}` | PRD: backlog items ready |
| `done` | `{idea_id, idea_version, ...}` | Generation complete |
| `error` | `{code, message}` | Any failure |

### Frontend Handling

The `AgentThoughtStream` component renders agent thoughts in a dark terminal-style panel, serving as the sole loading indicator during generation. Requirements and backlog items render progressively as their SSE events arrive.

---

## AI Gateway

### Provider Abstraction

The AI gateway (`backend/app/core/ai_gateway.py`) supports multiple LLM providers:

| Provider Kind | Protocol | Example |
|--------------|----------|---------|
| `generic_json` | Custom JSON API | ModelScope |
| `openai_compatible` | OpenAI-compatible API | OpenRouter, local models |

### Key Features

- **Structured output**: All LLM calls validate against Pydantic schemas
- **Retry logic**: Up to 2 retries on failure with robust JSON extraction
- **Response robustness**: Strips markdown fences, extracts JSON from prose
- **Task routing**: Different prompts per task type (opportunity, feasibility, scope, PRD stages)
- **Configurable via UI**: AI settings stored in `ai_settings` table, editable through admin API

### Current Default

`stepfun/step-3.5-flash:free` via OpenRouter — a free-tier model. The system is designed to minimize LLM calls due to latency constraints.
