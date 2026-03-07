# Market Evidence Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a unified market evidence layer that fuses structured `CompetitorCard` knowledge, dynamic news/signals, and existing internal semantic retrieval so DecisionOS can inject evidence into feasibility, scope, PRD, and proactive notifications.

**Architecture:** Keep SQLite as the source of truth for all structured market entities and evidence links. Use ChromaDB only as a semantic retrieval cache for chunked competitor snapshots, news summaries, and synthesized insights. Extend the existing proactive-news and idea-memory pipeline into a single evidence graph: `candidate discovery -> card analysis -> signal monitoring -> insight synthesis -> retrieval -> push`. Introduce a small backend service layer for market-evidence orchestration; this is a deliberate new pattern in this codebase and must be documented in architecture docs.

**Tech Stack:** FastAPI, Pydantic, SQLite, existing repositories under `backend/app/db`, existing ChromaDB vector store under `backend/app/agents/memory`, APScheduler proactive agents, Next.js frontend, pytest, Vitest.

---

## 1. Scope and Non-Goals

### 1.1 Goal of This Iteration

- Introduce first-class competitor entities and evidence links.
- Rework news collection so it enriches tracked competitors and ideas rather than acting as a standalone feed.
- Expose a unified retrieval surface that Feasibility and PRD generation can query.
- Preserve the current architecture rule: SQLite is canonical, vector store is disposable cache.

### 1.2 Non-Goals

- No generic web crawler platform.
- No multi-user evidence permissions.
- No autonomous pricing intelligence beyond lightweight extraction from public pages.
- No attempt to fully automate truth verification; every evidence object carries provenance and confidence.

### 1.3 User-Facing Outcome

- Each idea can accumulate a small set of relevant `CompetitorCard`s.
- News signals are linked to ideas and/or competitors instead of existing as isolated notifications.
- Feasibility and PRD can retrieve both static competitor understanding and recent market changes.
- Notifications can say not just “something happened” but “this change may affect your current idea.”

---

## 2. Domain Model

### 2.1 New Core Entities

#### Competitor

- Stable product/company identity.
- One row per canonical competitor.
- Workspace-scoped shared entity, not idea-owned.
- One competitor may be linked to many ideas within the same workspace through `IdeaEvidenceLink`.

Suggested fields:

- `id` (TEXT PK)
- `workspace_id` (TEXT FK -> workspace.id)
- `name` (TEXT)
- `canonical_url` (TEXT)
- `category` (TEXT)
- `status` (TEXT enum: `candidate|tracked|archived`)
- `created_at` (TEXT ISO8601)
- `updated_at` (TEXT ISO8601)

#### CompetitorSnapshot

- Versioned structured card extracted at a point in time.
- Latest snapshot powers the current `CompetitorCard`.

Suggested fields:

- `id` (TEXT PK)
- `competitor_id` (TEXT FK -> competitor.id)
- `snapshot_version` (INTEGER)
- `summary_json` (TEXT JSON)
- `quality_score` (REAL nullable)
- `traction_score` (REAL nullable)
- `relevance_score` (REAL nullable)
- `underrated_score` (REAL nullable)
- `confidence` (REAL nullable)
- `created_at` (TEXT ISO8601)

#### EvidenceSource

- Stores raw supporting sources for competitors, news, and insights.

Suggested fields:

- `id` (TEXT PK)
- `source_type` (TEXT enum: `website|pricing|docs|news|community|review`)
- `url` (TEXT)
- `title` (TEXT nullable)
- `snippet` (TEXT nullable)
- `published_at` (TEXT nullable)
- `fetched_at` (TEXT ISO8601)
- `confidence` (REAL nullable)
- `payload_json` (TEXT JSON nullable)

#### MarketSignal

- A dynamic event, usually derived from a news item or fresh source change.
- Workspace-scoped entity that may optionally be linked to zero, one, or many ideas.

Suggested fields:

- `id` (TEXT PK)
- `workspace_id` (TEXT FK -> workspace.id)
- `signal_type` (TEXT enum: `competitor_update|market_news|community_buzz|pricing_change`)
- `title` (TEXT)
- `summary` (TEXT)
- `severity` (TEXT enum: `low|medium|high`)
- `detected_at` (TEXT ISO8601)
- `evidence_source_id` (TEXT FK -> evidence_source.id nullable)
- `payload_json` (TEXT JSON nullable)

#### IdeaEvidenceLink

- Normalized linkage layer between ideas and evidence objects.

Suggested fields:

- `id` (TEXT PK)
- `idea_id` (TEXT FK -> idea.id)
- `entity_type` (TEXT enum: `competitor|signal|insight`)
- `entity_id` (TEXT)
- `link_reason` (TEXT)
- `relevance_score` (REAL nullable)
- `created_at` (TEXT ISO8601)

### 2.2 New Pydantic Shapes

Create schemas for:

- `CompetitorCard`
- `CompetitorSnapshotOut`
- `EvidenceSourceOut`
- `MarketSignalOut`
- `IdeaEvidenceLinkOut`
- `EvidenceInsight`

`CompetitorCard` should include:

- `basic_info`
- `positioning`
- `product`
- `business`
- `signals`
- `scores`
- `evidence`

Do not store only freeform markdown. Persist a strongly typed JSON shape so the UI and RAG layer can reuse fields deterministically.

### 2.3 Snapshot Lifecycle Rules

Define V1 snapshot behavior explicitly:

- Every successful competitor analysis run creates a new `competitor_snapshot`.
- `snapshot_version` increments monotonically per `competitor_id`.
- Keep the latest `5` snapshots.
- Older snapshots remain in SQLite for audit/history but must be marked non-latest and excluded from default retrieval/UI.
- Only the latest snapshot is indexed into the default retrieval flow unless a future “historical compare” feature requests older versions.

---

## 3. Retrieval Model

### 3.1 Canonical Rule

- SQLite stores entities, links, and snapshots.
- ChromaDB stores chunks derived from snapshots, signals, and insights.
- If ChromaDB is deleted, the app can rebuild it from SQLite.

### 3.2 Chunk Types

Add chunk writers for:

- `competitor_positioning`
- `competitor_features`
- `competitor_pricing`
- `competitor_reviews`
- `market_signal_summary`
- `evidence_insight`

Each chunk metadata must include:

- `entity_type`
- `entity_id`
- `workspace_id`
- `idea_id` or `global`
- `source_type`
- `created_at`
- `confidence`

### 3.3 Retrieval Injection Points

Use the unified evidence retrieval layer in only two places first:

- Feasibility generation
  - retrieve 3-5 relevant competitor/signal chunks
  - use them to sharpen differentiation and risk assessment
- PRD generation
  - retrieve 3-5 relevant competitor/signal chunks
  - use them to inform requirements, scope edges, and backlog wording

Do not inject evidence into every stage in V1. Keep prompt budget controlled.

---

## 4. Agent Design

### 4.1 Candidate Discovery Agent

Purpose:

- Find candidate competitors and evidence sources for an idea.

Responsibilities:

- derive search intents from `idea_seed`, confirmed DAG path, feasibility summaries
- collect candidate URLs and titles
- canonicalize obvious duplicates with simple rules (`canonical_url`, normalized hostname, normalized title)
- create raw `EvidenceSource` rows
- emit candidate competitor identities

V1 constraint:

- Use deterministic search adapters or curated public sources only.
- Do not introduce a full browser-based crawler in the first pass.
- Do not split discovery and normalization into separate agents in V1; keep the first pass compact to reduce serial LLM work.

### 4.2 Card Analysis Agent

Purpose:

- Build the structured `CompetitorCard` snapshot and score it.

Responsibilities:

- summarize product positioning, workflow, pricing, and visible traction
- calculate rule-based partial scores
- ask the LLM for bounded explanatory judgment
- persist `competitor_snapshot.summary_json`

Scoring rule:

- V1 final score = `30% rule-based heuristics + 70% bounded LLM judgment`
- V2 may shift weight toward deterministic external metrics after real provider integrations exist.

### 4.3 Signal Monitor Agent

Purpose:

- Extend the current news collector into idea-aware market monitoring.

Responsibilities:

- ingest fresh public news/posts
- match them to tracked competitors and/or ideas
- write `MarketSignal`
- optionally emit notifications when a signal maps to a current decision

Rollout rule:

- Do not replace the existing `news_monitor.py` in-place for V1.
- Create `signal_monitor.py` alongside the current monitor.
- Use a feature flag or scheduler wiring switch so the legacy path remains available until the new monitor is stable.

### 4.4 Insight Synthesizer

Purpose:

- Convert raw evidence and signals into decision-shaped insight.

Example outputs:

- “Three competitors emphasize collaboration, while this idea is strongest as a solo workflow tool.”
- “Recent community discussion suggests coding handoff is becoming a baseline expectation.”

These insights become both retrieval chunks and notification payloads.

### 4.5 Search Adapter Boundary

V1 must not hardcode one discovery source into business logic. Define a backend runtime adapter interface, for example:

- `search(query: str, limit: int) -> list[SearchResult]`

V1 implementation options:

- keep existing HN Algolia integration for news/signal collection
- add a dedicated runtime search provider later (for example Exa API, Tavily, SerpAPI, or another backend-usable provider)
- allow manual/direct URL seeding for development and deterministic tests

Important:

- MCP tools available in the coding environment are not product runtime dependencies and must not be treated as backend architecture.

---

## 5. Backend Implementation Plan

### Task 1: Add schema and repositories for market evidence

**Files:**
- Create: `backend/app/db/repo_competitors.py`
- Create: `backend/app/db/repo_market_signals.py`
- Create: `backend/app/schemas/market_evidence.py`
- Modify: `backend/app/db/init.sql`
- Modify: `backend/app/db/__init__.py`
- Test: `backend/tests/test_repo_competitors.py`
- Test: `backend/tests/test_repo_market_signals.py`

**Step 1: Write failing repository tests**

Add tests covering:

- create competitor
- add snapshot
- add evidence source
- link competitor/signal to idea
- list latest snapshots by idea linkage

**Step 2: Run repository tests to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_competitors.py tests/test_repo_market_signals.py -v --tb=short`

Expected: FAIL with missing repository/schema/table errors.

**Step 3: Add SQLite tables to `backend/app/db/init.sql`**

Create tables:

- `competitor`
- `competitor_snapshot`
- `evidence_source`
- `market_signal`
- `idea_evidence_link`

Add indexes for:

- `competitor(workspace_id, updated_at desc)`
- `competitor_snapshot(competitor_id, snapshot_version desc)`
- `market_signal(workspace_id, detected_at desc)`
- `idea_evidence_link(idea_id, entity_type, entity_id)`

**Step 4: Implement minimal schemas and repositories**

Support:

- `create_competitor`
- `create_snapshot`
- `create_evidence_source`
- `create_market_signal`
- `link_idea_entity`
- `list_linked_competitors_for_idea`
- `list_signals_for_idea`

**Step 5: Run repository tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_competitors.py tests/test_repo_market_signals.py -v --tb=short`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/db/init.sql backend/app/db/__init__.py backend/app/db/repo_competitors.py backend/app/db/repo_market_signals.py backend/app/schemas/market_evidence.py backend/tests/test_repo_competitors.py backend/tests/test_repo_market_signals.py
git commit -m "feat: add market evidence persistence primitives"
```

### Task 2: Extend vector store with evidence chunks

**Files:**
- Modify: `backend/app/agents/memory/vector_store.py`
- Test: `backend/tests/test_vector_store_market_evidence.py`

**Step 1: Write failing vector store tests**

Cover:

- adding competitor chunks
- adding signal chunks
- filtering retrieval by metadata
- rebuilding chunks from structured source data

**Step 2: Run test to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_vector_store_market_evidence.py -v --tb=short`

Expected: FAIL with missing methods.

**Step 3: Add chunk APIs**

Implement:

- `add_competitor_chunk(...)`
- `add_market_signal_chunk(...)`
- `add_evidence_insight_chunk(...)`
- `search_market_evidence(query, n_results, filters=None)`

Do not bypass metadata; every chunk write must include typed metadata.

**Step 4: Run tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_vector_store_market_evidence.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/agents/memory/vector_store.py backend/tests/test_vector_store_market_evidence.py
git commit -m "feat: add competitor and market signal vector chunks"
```

### Task 3: Add market evidence ingestion service layer

**Files:**
- Create: `backend/app/services/market_evidence_service.py`
- Test: `backend/tests/test_market_evidence_service.py`
- Modify: `docs/architecture.md`

**Step 1: Write failing service tests**

Cover service flows:

- create competitor from normalized candidate
- write snapshot and mirror chunks to vector store
- create signal and link it to idea
- derive one insight from competitor + signal inputs

**Step 2: Run test to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_market_evidence_service.py -v --tb=short`

Expected: FAIL with missing service or dependency wiring.

**Step 3: Implement minimal service**

Provide orchestration methods:

- `upsert_competitor_card(...)`
- `record_market_signal(...)`
- `link_evidence_to_idea(...)`
- `build_and_store_insight(...)`
- `rebuild_market_chunks_for_competitor(...)`

This service layer is a deliberate architectural addition. Document in `docs/architecture.md` that it is a thin orchestration layer for:

- repo composition
- vector-store mirroring
- notification/push side effects

It does not replace route handlers or LangGraph nodes; it centralizes business flows that must be reusable from API routes, schedulers, and rebuild commands.

**Step 4: Run tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_market_evidence_service.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/market_evidence_service.py backend/tests/test_market_evidence_service.py
git commit -m "feat: add market evidence orchestration service"
```

### Task 4: Add signal monitor beside the legacy news monitor

**Files:**
- Create: `backend/app/agents/graphs/proactive/signal_monitor.py`
- Modify: `backend/app/core/scheduler.py`
- Modify: `backend/app/routes/insights.py`
- Test: `backend/tests/test_news_monitor.py`

**Step 1: Write failing tests for signal mapping**

Add tests for:

- news item becomes `MarketSignal`
- signal links to idea when similarity threshold passes
- signal links to competitor when canonical URL or title matches tracked entity
- deduplication prevents repeated notifications

**Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_news_monitor.py -v --tb=short`

Expected: FAIL because the new signal monitor does not exist yet.

**Step 3: Implement parallel signal monitor rollout**

Change behavior:

- fetched news is stored as `EvidenceSource`
- relevant news creates `MarketSignal`
- signal is linked to idea and optionally competitor
- notification text references decision impact, not just raw story title

Retain:

- fail-open behavior on network issues
- ChromaDB matching for relevance

Rollout:

- keep `news_monitor.py` intact as fallback
- add `signal_monitor.py`
- wire scheduler/insight routes through a feature flag or explicit trigger path
- only remove the legacy monitor in a later cleanup once parity is validated

**Step 4: Run tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_news_monitor.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/agents/graphs/proactive/signal_monitor.py backend/app/core/scheduler.py backend/app/routes/insights.py backend/tests/test_news_monitor.py
git commit -m "feat(proactive): add market signal monitor alongside legacy news monitor"
```

### Task 5: Add competitor discovery and analysis endpoints

**Files:**
- Create: `backend/app/routes/idea_market_evidence.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_idea_market_evidence_routes.py`

**Step 1: Write failing API tests**

Cover:

- `POST /ideas/{idea_id}/evidence/competitors/discover`
- `GET /ideas/{idea_id}/evidence/competitors`
- `GET /ideas/{idea_id}/evidence/signals`
- `POST /ideas/{idea_id}/evidence/insights/sync`

Expected response envelopes:

```json
{
  "idea_id": "uuid",
  "data": {}
}
```

**Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_idea_market_evidence_routes.py -v --tb=short`

Expected: FAIL with route not found.

**Step 3: Implement routes**

Minimum behavior:

- discover competitors for one idea
- list linked competitors with latest snapshots
- list recent signals for one idea
- trigger one-shot insight synthesis

Do not expose generic workspace-wide crawl endpoints in V1.

**Step 4: Run tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_idea_market_evidence_routes.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routes/idea_market_evidence.py backend/app/main.py backend/tests/test_idea_market_evidence_routes.py
git commit -m "feat: add idea-scoped market evidence APIs"
```

### Task 6: Inject market evidence into Feasibility and PRD context assembly

**Files:**
- Modify: `backend/app/routes/idea_agents.py`
- Modify: `backend/app/agents/nodes/context_loader.py`
- Modify: `backend/app/agents/state.py`
- Test: `backend/tests/test_market_evidence_retrieval_integration.py`

**Step 1: Write failing integration tests**

Cover:

- Feasibility context includes retrieved evidence references
- PRD context pack includes evidence summaries
- prompts stay bounded when no evidence exists
- absence of evidence does not block generation

**Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_market_evidence_retrieval_integration.py -v --tb=short`

Expected: FAIL because market evidence is not yet present in state/context.

**Step 3: Implement retrieval injection**

Add:

- market evidence retrieval helper
- bounded top-k selection
- short evidence summary object in graph state

Do not dump raw article text into prompts. Use concise summarized context with source provenance.
Add a hard cap:

- target `evidence_context <= 800 tokens`
- estimate tokens with `len(text) // 4`
- if over budget, fall back to top-2 evidence entries
- if still over budget, trim summaries before prompt injection

**Step 4: Run tests to verify pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_market_evidence_retrieval_integration.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routes/idea_agents.py backend/app/agents/nodes/context_loader.py backend/app/agents/state.py backend/tests/test_market_evidence_retrieval_integration.py
git commit -m "feat: inject market evidence into feasibility and prd flows"
```

### Task 7a: Add frontend evidence types, mock data, and component skeletons

**Files:**
- Create: `frontend/components/evidence/CompetitorCardList.tsx`
- Create: `frontend/components/evidence/MarketSignalsPanel.tsx`
- Create: `frontend/lib/market-evidence.ts`
- Test: `frontend/components/evidence/__tests__/CompetitorCardList.test.tsx`
- Test: `frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

**Step 1: Write failing frontend tests**

Cover:

- competitor cards render latest scores and evidence counts
- signals panel renders title, severity, and decision impact
- empty states do not block page load

**Step 2: Run tests to verify failure**

Run: `cd frontend && pnpm vitest frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

Expected: FAIL with missing components.

**Step 3: Implement minimal UI**

Requirements:

- define API-facing frontend types
- add local mock fixtures
- render component skeletons and empty states
- do not block on backend completion

**Step 4: Run tests to verify pass**

Run: `cd frontend && pnpm vitest frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/components/evidence/CompetitorCardList.tsx frontend/components/evidence/MarketSignalsPanel.tsx frontend/lib/market-evidence.ts frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx
git commit -m "feat(frontend): add market evidence component skeletons"
```

### Task 7b: Connect frontend evidence components to real APIs

**Files:**
- Modify: `frontend/components/feasibility/FeasibilityPage.tsx`
- Modify: `frontend/components/prd/PrdPage.tsx`
- Modify: `frontend/lib/market-evidence.ts`
- Test: `frontend/components/evidence/__tests__/CompetitorCardList.test.tsx`
- Test: `frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

**Step 1: Write failing integration-oriented frontend tests**

Cover:

- competitor cards render latest scores and evidence counts from API data
- signals panel renders title, severity, and decision impact
- empty states do not block page load

**Step 2: Run tests to verify failure**

Run: `cd frontend && pnpm vitest frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

Expected: FAIL on missing real data integration.

**Step 3: Wire components into Feasibility and PRD**

Requirements:

- show 3-5 top competitors per idea
- show recent signals with source/time
- no separate dashboard needed in V1
- embed evidence beside Feasibility and PRD where it changes decision quality

**Step 4: Run tests to verify pass**

Run: `cd frontend && pnpm vitest frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/components/feasibility/FeasibilityPage.tsx frontend/components/prd/PrdPage.tsx frontend/lib/market-evidence.ts frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx
git commit -m "feat(frontend): connect market evidence components to idea APIs"
```

### Task 8: Update docs and add rebuild/verification commands

**Files:**
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Create: `docs/plans/2026-03-07-market-evidence-layer-implementation-plan.md`

**Step 1: Update architecture docs**

Document:

- new market evidence entities
- evidence chunk taxonomy
- signal-monitor behavior
- retrieval injection points

**Step 2: Add operator commands to README**

Include:

- how to trigger competitor discovery
- how to trigger signal sync
- how to rebuild vector chunks from SQLite

**Step 3: Verification run**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_repo_competitors.py tests/test_repo_market_signals.py tests/test_vector_store_market_evidence.py tests/test_market_evidence_service.py tests/test_news_monitor.py tests/test_idea_market_evidence_routes.py tests/test_market_evidence_retrieval_integration.py -v --tb=short
cd frontend && pnpm vitest frontend/components/evidence/__tests__/CompetitorCardList.test.tsx frontend/components/evidence/__tests__/MarketSignalsPanel.test.tsx
```

Expected: all targeted tests pass.

**Step 4: Commit**

```bash
git add docs/architecture.md README.md docs/plans/2026-03-07-market-evidence-layer-implementation-plan.md
git commit -m "docs: document market evidence layer architecture and operations"
```

---

## 6. Scoring Model

### 6.1 V1 Heuristic Scores

Implement bounded 0-10 scores for:

- `quality_score`
  - product clarity
  - feature completeness
  - workflow coherence
- `traction_score`
  - source count heuristics
  - freshness/update heuristics
  - visible evidence of community or review presence extracted from sources
- `relevance_score`
  - overlap with idea problem, user, and workflow
- `business_score`
  - pricing clarity
  - monetization legibility

V1 note:

- These are not internet-ground-truth metrics.
- They are heuristics derived from collected evidence objects and stable source features.
- Do not overstate them in UI or docs.

### 6.2 Derived Score

`underrated_score` should rise when:

- quality is high
- relevance is high
- traction is only low-to-medium

Do not rely on an opaque LLM-only scalar. Persist subscore breakdowns in `summary_json`.

### 6.3 V2 Metrics Upgrade Path

When real provider integrations are added, deterministic weight may increase using signals such as:

- real review counts from supported platforms
- GitHub stars/releases for developer tools
- structured launch/ranking metadata
- provider-backed freshness/change history

Do not assume these sources exist in V1.

---

## 7. Push Strategy

Only notify when one of these holds:

- a high-severity signal affects a linked competitor
- a new signal changes the likely feasibility ranking
- multiple low-severity signals cluster into one trend insight

Do not push every article. Notifications should be sparse and decision-shaped.

---

## 8. Risks and Controls

### Risk: noisy evidence

Control:

- enforce typed sources and confidence
- cap retrieved evidence count
- deduplicate on canonical URL/title hash

### Risk: prompt bloat

Control:

- summarize evidence before injection
- use top-k retrieval only
- pass source references, not full raw pages

### Risk: stale vector cache

Control:

- all chunk writes happen after SQLite persistence
- provide rebuild command from canonical DB records

### Risk: product confusion

Control:

- present evidence only where it changes a decision
- do not create a separate analyst dashboard in V1

---

## 9. Rollout Order

Recommended rollout:

1. Persistence primitives
2. Chunk storage + retrieval
3. Frontend skeletons and types
4. Signal monitor parallel rollout
5. Competitor discovery APIs
6. Feasibility/PRD retrieval injection
7. Frontend real API integration

This order keeps the evidence model coherent before it is exposed in generation or UI.
