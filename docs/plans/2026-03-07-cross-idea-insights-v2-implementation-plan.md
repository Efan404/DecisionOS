# Cross-Idea Insights V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Cross-Idea Insights from a lightweight similarity notifier into a structured analysis layer that identifies reusable assets, merge candidates, and positioning conflicts across ideas.

**Architecture:** Build V2 on top of the existing multi-idea SQLite model and the new market evidence layer. Continue using vector retrieval to find candidate related ideas, then use bounded analysis over idea context, decision artifacts, and linked evidence to synthesize actionable insights. Do not introduce a graph database in V1; SQLite relations plus vector recall are sufficient.

**Tech Stack:** FastAPI, Pydantic, SQLite, existing repositories under `backend/app/db`, existing ChromaDB vector store under `backend/app/agents/memory`, APScheduler proactive agents, pytest, Next.js, Vitest.

---

## 1. Scope and Positioning

### 1.1 Why This Exists

Cross-Idea Insights V2 should answer questions the market evidence layer does not answer:

- Which ideas are duplicating effort?
- Which ideas can reuse scope, PRD requirements, or backlog assets?
- Which ideas should likely merge into one MVP?
- Which ideas target overlapping users but conflict in positioning?

This is an internal strategic analysis layer. It is not a competitor-analysis feature and should not be framed as one.

### 1.2 Dependency on Market Evidence Layer

This plan depends on `docs/plans/2026-03-07-market-evidence-layer-implementation-plan.md`.

V2 may read:

- idea summaries
- confirmed DAG path
- selected feasibility plan
- frozen scope baseline
- PRD requirements / backlog themes
- linked competitors
- linked market signals

Do not block V2 on every market-evidence feature. The minimum dependency is:

- idea-level evidence links exist
- vector retrieval can search idea/evidence chunks

### 1.3 Non-Goals

- No graph database introduction in V1.
- No full workspace-wide pairwise `n^2` analysis on every scheduler run.
- No autonomous merge operation between ideas.
- No cross-workspace insights.

---

## 2. Product Behavior

### 2.1 Output Shape

Replace plain freeform overlap text with a structured insight record.

Suggested fields:

- `id`
- `idea_a_id`
- `idea_b_id`
- `insight_type`
- `summary`
- `why_it_matters`
- `recommended_action`
- `confidence`
- `similarity_score`
- `evidence_refs`
- `created_at`

### 2.2 Insight Types

Support these V1 types:

- `execution_reuse`
- `merge_candidate`
- `positioning_conflict`
- `shared_audience`
- `shared_capability`
- `evidence_overlap`

### 2.3 Recommended Actions

Constrain actions to a small enum:

- `review`
- `compare_feasibility`
- `reuse_scope`
- `reuse_prd_requirements`
- `merge_ideas`
- `keep_separate`

The point of V2 is actionability. If an insight cannot recommend one of these actions, it is probably too weak to surface.

---

## 3. Retrieval and Analysis Model

### 3.1 Retrieval Strategy

V2 uses a two-step process:

1. Candidate recall
2. Structured analysis

Candidate recall sources:

- idea-summary vector similarity
- shared competitor links
- shared market signals
- overlapping scope or PRD themes

Do not send all ideas into the LLM. Use vector/relational prefiltering first.

### 3.2 Candidate Recall Rules

For one anchor idea, candidate ideas may enter analysis if any of these hold:

- idea-summary distance is below threshold
- they share at least one linked competitor
- they share at least one linked market signal
- they share at least one normalized capability/theme tag

Default V1 limits:

- max `5` candidate ideas per anchor idea
- max `1` synthesized insight per pair per run unless evidence materially changes

### 3.3 Analysis Inputs

For each candidate pair, assemble a bounded comparison pack:

- idea A title/seed/stage
- idea B title/seed/stage
- confirmed path summaries if available
- selected plan summaries if available
- frozen scope summaries if available
- top reusable PRD requirement themes if available
- shared competitor names
- shared signal summaries

Hard constraint:

- comparison pack target `<= 1000 tokens`
- estimate with `len(text) // 4`
- trim lower-priority evidence before LLM analysis

### 3.4 Why No Graph Database

Do not add Neo4j or similar in V1.

Reasoning:

- current relationships are simple enough for SQLite join tables
- candidate recall is better handled by vector similarity
- action synthesis happens per pair, not via deep multi-hop traversal

Revisit a graph database only if future requirements need:

- multi-hop dependency/path queries
- visual graph exploration as a core UX
- complex rule engines over many entity types

---

## 4. Backend Design

### 4.1 Persistence Model

Add a dedicated table instead of overloading notifications.

Suggested table: `cross_idea_insight`

Fields:

- `id` (TEXT PK)
- `workspace_id` (TEXT FK -> workspace.id)
- `idea_a_id` (TEXT FK -> idea.id)
- `idea_b_id` (TEXT FK -> idea.id)
- `insight_type` (TEXT)
- `summary` (TEXT)
- `why_it_matters` (TEXT)
- `recommended_action` (TEXT)
- `confidence` (REAL nullable)
- `similarity_score` (REAL nullable)
- `evidence_json` (TEXT JSON nullable)
- `fingerprint` (TEXT)
- `created_at` (TEXT ISO8601)
- `updated_at` (TEXT ISO8601)

Dedup rule:

- store idea pair in canonical order
- dedup on `(idea_a_id, idea_b_id, fingerprint)`

### 4.2 Service Boundary

Add a thin orchestration service, for example:

- `backend/app/services/cross_idea_insights_service.py`

Responsibilities:

- find candidate related ideas for an anchor idea
- assemble bounded comparison context
- call LLM for structured analysis
- persist insight rows
- mirror summary chunks to vector store if useful

This follows the same new service-layer pattern introduced by the market evidence plan.

### 4.3 Vector Store Extensions

Add or reuse chunk types for:

- `idea_summary`
- `scope_theme`
- `prd_requirement_theme`
- `cross_idea_insight_summary`

Metadata should include:

- `idea_id`
- `workspace_id`
- `entity_type`
- `created_at`

Do not add a second vector system. Reuse the existing ChromaDB integration.

---

## 5. Proactive Agent Design

### 5.1 Replace Current Analyzer Behavior

Current analyzer behavior in `backend/app/agents/graphs/proactive/cross_idea_analyzer.py` is:

- load idea summaries
- query similar summaries
- generate 1-2 sentence overlap explanation

V2 should instead:

- load anchor ideas needing analysis
- recall candidate related ideas using vector + relational filters
- synthesize structured insight types
- persist structured insights
- optionally generate notifications only for high-value cases

### 5.2 Trigger Strategy

Run V2 analysis only when one of these happens:

- idea is created
- confirmed DAG path changes
- selected feasibility plan changes
- frozen scope baseline changes
- linked market evidence changes materially

For the scheduler:

- process recently updated ideas only
- do not scan every pair in the workspace on every run

### 5.3 Notification Rules

Only notify on:

- `merge_candidate`
- `positioning_conflict`
- high-confidence `execution_reuse`

Do not notify on every weak similarity. Most insights should be visible in-product, not pushed.

---

## 6. Frontend Design

### 6.1 Surface Placement

Do not keep Cross-Idea Insights as a vague standalone novelty panel.

Recommended placements:

- idea list/detail badge:
  - “2 reusable related ideas”
  - “1 merge candidate”
- idea detail drawer/panel:
  - insight summary
  - why it matters
  - recommended action
  - linked related idea

### 6.2 UX Requirements

Each insight card should show:

- insight type badge
- related idea name
- concise summary
- recommended action
- confidence indicator

Useful CTA examples:

- `Compare Feasibility`
- `Open Related PRD`
- `Reuse Scope`

Avoid overexplaining raw similarity scores in the main UI.

---

## 7. Implementation Tasks

### Task 1: Add persistence and schemas for Cross-Idea Insights V2

**Files:**
- Create: `backend/app/db/repo_cross_idea_insights.py`
- Create: `backend/app/schemas/cross_idea_insights.py`
- Modify: `backend/app/db/init.sql`
- Test: `backend/tests/test_repo_cross_idea_insights.py`

**Step 1: Write the failing repository test**

Cover:

- create one insight row
- canonicalize idea pair ordering
- deduplicate by fingerprint
- list insights for one idea

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_cross_idea_insights.py -v --tb=short`

Expected: FAIL with missing repository/schema/table errors.

**Step 3: Add the table and repository**

Implement:

- `create_or_update_insight(...)`
- `list_for_idea(...)`
- `list_recent_for_workspace(...)`

**Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_cross_idea_insights.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/db/init.sql backend/app/db/repo_cross_idea_insights.py backend/app/schemas/cross_idea_insights.py backend/tests/test_repo_cross_idea_insights.py
git commit -m "feat: add structured cross-idea insight persistence"
```

### Task 2: Add candidate-recall helpers using vector and evidence links

**Files:**
- Create: `backend/app/services/cross_idea_candidate_service.py`
- Test: `backend/tests/test_cross_idea_candidate_service.py`

**Step 1: Write the failing service test**

Cover:

- finds related ideas via vector similarity
- boosts candidates sharing competitors or signals
- limits candidate count

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_candidate_service.py -v --tb=short`

Expected: FAIL with missing service.

**Step 3: Implement minimal candidate recall**

Methods:

- `find_related_ideas(anchor_idea_id, limit=5)`
- `score_candidate(anchor_idea_id, candidate_idea_id)`

Use:

- vector recall first
- relational boosts second

**Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_candidate_service.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/cross_idea_candidate_service.py backend/tests/test_cross_idea_candidate_service.py
git commit -m "feat: add cross-idea candidate recall service"
```

### Task 3: Add Cross-Idea Insights V2 orchestration service

**Files:**
- Create: `backend/app/services/cross_idea_insights_service.py`
- Test: `backend/tests/test_cross_idea_insights_service.py`
- Modify: `docs/architecture.md`

**Step 1: Write the failing service test**

Cover:

- assembles bounded comparison context
- calls LLM once per selected pair
- returns structured `insight_type` and `recommended_action`
- skips weak candidates

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_insights_service.py -v --tb=short`

Expected: FAIL with missing service.

**Step 3: Implement minimal orchestration**

Methods:

- `analyze_anchor_idea(anchor_idea_id)`
- `analyze_pair(idea_a_id, idea_b_id)`
- `build_pair_context(idea_a_id, idea_b_id)`

Constraints:

- `build_pair_context` must stay under the prompt budget
- low-confidence / low-signal pairs should not persist insights

**Step 4: Update architecture docs**

Document:

- Cross-Idea Insights V2 is a secondary analysis layer
- market evidence layer is a dependency
- no graph database in V1

**Step 5: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_insights_service.py -v --tb=short`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/services/cross_idea_insights_service.py docs/architecture.md backend/tests/test_cross_idea_insights_service.py
git commit -m "feat: add cross-idea insights v2 orchestration service"
```

### Task 4: Replace the proactive analyzer with V2 behavior

**Files:**
- Modify: `backend/app/agents/graphs/proactive/cross_idea_analyzer.py`
- Modify: `backend/app/core/scheduler.py`
- Test: `backend/tests/test_cross_idea_analyzer.py`

**Step 1: Write the failing analyzer test**

Cover:

- analyzer processes only recently updated ideas
- analyzer persists structured insights
- analyzer does not notify on weak similarity

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_analyzer.py -v --tb=short`

Expected: FAIL with legacy analyzer behavior.

**Step 3: Implement V2 analyzer**

Change behavior:

- use candidate service + orchestration service
- persist structured insight records
- emit high-value notifications only

Do not keep the old freeform overlap output as the primary contract.

**Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_cross_idea_analyzer.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/agents/graphs/proactive/cross_idea_analyzer.py backend/app/core/scheduler.py backend/tests/test_cross_idea_analyzer.py
git commit -m "feat(proactive): upgrade cross-idea analyzer to v2"
```

### Task 5: Add idea-scoped APIs for related insights

**Files:**
- Create: `backend/app/routes/idea_cross_insights.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_idea_cross_insights_routes.py`

**Step 1: Write the failing API test**

Cover:

- `GET /ideas/{idea_id}/cross-insights`
- `POST /ideas/{idea_id}/cross-insights/sync`

Envelope:

```json
{
  "idea_id": "uuid",
  "data": {}
}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_idea_cross_insights_routes.py -v --tb=short`

Expected: FAIL with route not found.

**Step 3: Implement minimal routes**

Route behavior:

- list persisted insights for one idea
- trigger one sync for one anchor idea

**Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_idea_cross_insights_routes.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routes/idea_cross_insights.py backend/app/main.py backend/tests/test_idea_cross_insights_routes.py
git commit -m "feat: add idea-scoped cross-idea insights apis"
```

### Task 6: Add frontend surfaces for V2 insights

**Files:**
- Create: `frontend/components/insights/CrossIdeaInsightList.tsx`
- Modify: `frontend/components/insights/CrossIdeaInsights.tsx`
- Modify: `frontend/lib/api.ts`
- Test: `frontend/components/insights/__tests__/CrossIdeaInsightList.test.tsx`

**Step 1: Write the failing frontend test**

Cover:

- renders structured insight type and action
- links to related idea
- hides weak implementation details like raw distance by default

**Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest frontend/components/insights/__tests__/CrossIdeaInsightList.test.tsx`

Expected: FAIL with missing component or outdated props.

**Step 3: Implement the minimal UI**

Requirements:

- show related idea title
- show insight type badge
- show concise summary and recommended action
- keep module visually secondary to main decision flow

**Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest frontend/components/insights/__tests__/CrossIdeaInsightList.test.tsx`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/components/insights/CrossIdeaInsightList.tsx frontend/components/insights/CrossIdeaInsights.tsx frontend/lib/api.ts frontend/components/insights/__tests__/CrossIdeaInsightList.test.tsx
git commit -m "feat(frontend): add cross-idea insights v2 surfaces"
```

### Task 7: Verification and docs

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Create: `docs/plans/2026-03-07-cross-idea-insights-v2-implementation-plan.md`

**Step 1: Update docs**

Document:

- what V2 insight types mean
- where they appear in product
- why no graph database is used in V1

**Step 2: Run targeted verification**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_cross_idea_insights.py tests/test_cross_idea_candidate_service.py tests/test_cross_idea_insights_service.py tests/test_cross_idea_analyzer.py tests/test_idea_cross_insights_routes.py -v --tb=short
cd frontend && pnpm vitest frontend/components/insights/__tests__/CrossIdeaInsightList.test.tsx
```

Expected: all targeted tests pass.

**Step 3: Commit**

```bash
git add README.md docs/architecture.md docs/plans/2026-03-07-cross-idea-insights-v2-implementation-plan.md
git commit -m "docs: document cross-idea insights v2 design and verification"
```

---

## 8. Rollout Order

Recommended order:

1. Structured persistence
2. Candidate recall
3. Pair-analysis orchestration
4. Proactive analyzer upgrade
5. API surface
6. Frontend surface

This keeps the feature grounded in reusable infrastructure before exposing it in UI.
