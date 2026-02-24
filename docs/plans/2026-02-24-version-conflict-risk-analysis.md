# IDEA_VERSION_CONFLICT Risk Analysis

> **Status:** Read-only analysis. Implementation plan TBD.
> **Date:** 2026-02-24
> **Context:** Following the fix to `apply_agent_update()` (commit d2c582b), this report surveys remaining version conflict risks across the codebase.

---

## Executive Summary

The codebase uses optimistic locking on the `idea` table — every write does `WHERE id=? AND version=?`, bumping `version+1`. `apply_agent_update()` now auto-retries once on conflict, but **several HIGH/CRITICAL risk vectors remain**, particularly:

1. **Scope operations have no retry at all** (early guard fails hard → HTTP 409)
2. **Path summary background task** uses a stale version re-read (can race feasibility agent)
3. **PRD stream** (90s LLM window) only has one retry — two concurrent writes during that window still fail
4. **All non-streaming agent routes** rely solely on the single auto-retry in `apply_agent_update()`

---

## Root Causes

| #    | Root Cause                                                                       | Affected Operations                            |
| ---- | -------------------------------------------------------------------------------- | ---------------------------------------------- |
| RC-1 | Version captured at request time, used after LLM (~30–90s later)                 | All agent routes                               |
| RC-2 | Background task reads version at enqueue time, not at write time                 | Path summary (`_fill_path_summary_background`) |
| RC-3 | Scope operations use early guard without retry                                   | All scope repo operations                      |
| RC-4 | Only one auto-retry in `apply_agent_update()` — two concurrent writes still fail | All agent routes                               |

---

## Risk Matrix

| Operation               | Route                             | LLM Duration | Conflict Recovery          | Risk         |
| ----------------------- | --------------------------------- | ------------ | -------------------------- | ------------ |
| PRD stream (two-stage)  | `POST /agents/prd/stream`         | ~90s         | Auto-retry 1×              | **CRITICAL** |
| PRD non-stream          | `POST /agents/prd`                | ~90s         | Auto-retry 1×              | **CRITICAL** |
| Feasibility stream      | `POST /agents/feasibility/stream` | ~60s         | Auto-retry 1×              | **HIGH**     |
| Feasibility non-stream  | `POST /agents/feasibility`        | ~60s         | Auto-retry 1×              | **HIGH**     |
| Scope agent             | `POST /agents/scope`              | ~30s         | Auto-retry 1×              | **HIGH**     |
| Scope freeze            | `POST /scope/freeze`              | 0s (no LLM)  | **No retry** (early guard) | **HIGH**     |
| Scope bootstrap         | `POST /scope/draft/bootstrap`     | 0s           | **No retry**               | **HIGH**     |
| Scope new-version       | `POST /scope/new-version`         | 0s           | **No retry**               | **HIGH**     |
| Path summary background | Background task                   | ~10s         | Auto-retry 1×              | **HIGH**     |
| Opportunity stream      | `POST /agents/opportunity/stream` | ~10s         | Auto-retry 1×              | HIGH         |
| Opportunity non-stream  | `POST /agents/opportunity`        | ~10s         | Auto-retry 1×              | HIGH         |
| Scope patch             | `PATCH /scope/draft`              | 0s           | **No retry**               | MEDIUM       |
| PRD feedback            | `POST /prd/feedback`              | 0s           | Auto-retry 1×              | MEDIUM       |
| Path confirmation       | `POST /paths`                     | 0s (no LLM)  | Auto-retry 1×              | MEDIUM       |
| Update idea metadata    | `PATCH /ideas/{id}`               | 0s           | No retry                   | LOW          |

---

## Concrete Race Scenarios

### Scenario A — Path Summary Background Task + Feasibility Agent (REPRODUCIBLE)

```
T+0s   User clicks "Confirm Path"
         → POST /paths → apply_agent_update(version=V) → version bumped to V+1
         → Background task _fill_path_summary_background() enqueued

T+1s   User navigates to Feasibility, clicks "Generate Plans"
         → POST /agents/feasibility/stream with version=V+1 (fresh from response)
         → 3 parallel LLM calls start (~60s)

T+8s   Background task fires
         → Re-reads idea: gets version=V+1 (correct)
         → LLM summary runs (~10s)

T+18s  Background task finishes, calls apply_agent_update(version=V+1)
         → Bumps to V+2

T+60s  Feasibility LLM finishes, calls apply_agent_update(version=V+1)
         → First attempt: conflict (version is now V+2)
         → Auto-retry: re-reads V+2, retries → SUCCESS
```

**Currently rescued by auto-retry. But if a third write happens between retry attempts, user sees 409.**

---

### Scenario B — PRD Stream + Scope Freeze Race (REPRODUCIBLE)

```
T+0s   User clicks "Generate PRD"
         → POST /agents/prd/stream with version=V
         → Version check at line 418 passes
         → Stage A + Stage B LLM begin (~90s total)

T+45s  User navigates back, clicks "New Scope Version"
         → POST /scope/new-version with version=V
         → _check_idea_guard passes (version still V)
         → Scope repo writes: version bumped to V+1

T+90s  PRD LLM finishes, apply_agent_update(version=V)
         → First attempt: conflict (version is V+1)
         → Auto-retry: re-reads V+1, retries → SUCCESS

         (If another write happened between T+45s and T+90s, retry also fails → 409)
```

---

### Scenario C — Scope Early Guard Failure (REPRODUCIBLE)

```
T+0s   User on Feasibility page, frontend captures version=V

T+5s   Another tab / background op bumps version to V+1
         (e.g., path summary background task completes)

T+10s  User clicks "Bootstrap Scope"
         → POST /scope/draft/bootstrap with version=V
         → _check_idea_guard() in repo_scope.py: V ≠ V+1 → kind="conflict"
         → Returns HTTP 409 immediately, no retry
         → User sees error toast: must refresh and retry manually
```

**No auto-retry in any scope operation. User must manually retry.**

---

## Affected Files (by Risk Priority)

```
backend/app/db/repo_scope.py          ← Scope operations, no retry (lines 91, 132, 169, 216, 282)
backend/app/routes/idea_dag.py        ← Background task stale read (lines 338–346)
backend/app/routes/idea_agents.py     ← All agent routes use payload.version at write time
backend/app/db/repo_ideas.py          ← apply_agent_update: only 1 retry (lines 214–226)
```

---

## Recommendations (Priority Order)

### P1 — Scope operations: add retry (matches what `apply_agent_update` does)

`backend/app/db/repo_scope.py` — The `_update_idea_context()` helper and the early guard (`_check_idea_guard`) need a read-refresh-retry pattern. Since scope operations don't run LLM before writing, the conflict window is small but still real (background tasks).

### P2 — Background task: read version immediately before write, not at enqueue time

`backend/app/routes/idea_dag.py:338` — `_fill_path_summary_background()` re-reads idea version early in the function and stores it. This stale read races against feasibility/scope agents. Fix: don't pass version as a parameter; let `apply_agent_update()` itself fetch the latest version (which it now does on retry). Actually the background task already calls `apply_agent_update()` — the auto-retry covers this case already if only one other write occurs.

### P3 — Consider a second retry in `apply_agent_update` for very long LLM windows

For PRD stream (~90s), a single retry is insufficient if multiple concurrent ops fire. Could increase to 2 retries. Risk of infinite loop is low since each retry reads fresh version.

### P4 — Frontend: after receiving `done` SSE event, update local version state before allowing new writes

Already partially done (PrdPage calls `setIdeaVersion` on done). But Feasibility and Scope pages should also ensure they don't submit stale version after a long LLM operation.

---

## What's Already Fixed

- `apply_agent_update()` auto-retries once on version conflict (commit `d2c582b`)
- Covers: all agent routes (opportunity, feasibility, scope, PRD), path confirmation, path summary background task, PRD feedback

## What Remains Unfixed

- Scope repository operations (`repo_scope.py`): no retry → user-facing 409 on any concurrent write
- Double-concurrent writes during PRD stream (90s window): second retry not implemented
