# Demo Data Initialization Debugging Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Identify why demo/mock data is not present in some environments, then add a reliable and explicit seeding workflow that can initialize SQLite demo records and vector-store demo data together.

**Architecture:** Treat demo data as two separate persistence concerns: canonical SQLite records and Chroma vector cache. First verify where each environment actually reads and writes data from. Then add one explicit seed entrypoint that can initialize DB-only, vector-only, or both, without touching AI provider settings.

**Tech Stack:** FastAPI, SQLite, ChromaDB, existing bootstrap flow in `backend/app/db/bootstrap.py`, existing demo seed modules in `backend/app/db/seed_demo.py` and `backend/app/agents/memory/seed_data.py`, pytest, shell verification.

---

## 1. Root Cause Findings So Far

### 1.1 There are currently two distinct demo-data seed paths

- SQLite demo data is initialized from `backend/app/db/bootstrap.py`
- Vector-store demo data is initialized from `backend/app/agents/memory/seed_data.py`

These two paths are not unified behind one explicit operator command.

### 1.2 The existing standalone script is incomplete

Current script:

- `backend/scripts/seed_demo.py`

Current behavior:

- seeds Chroma/vector collections only
- does **not** seed SQLite demo ideas, DAG nodes, paths, baselines, notifications, decision events, or user preferences

This explains why a manual “seed demo” run may still leave the app without visible demo ideas.

### 1.3 Local environment already shows path divergence risk

Observed locally:

- repository root has `decisionos.db`
- `backend/decisionos.db` also exists

The app resolves `DECISIONOS_DB_PATH` relative to the process working directory when the path is not absolute. This means:

- running from repo root may point to one DB
- running from `backend/` may point to another DB
- remote environments may behave differently again

This is a likely root cause for “demo data exists locally but not remotely” or “seeding succeeded but UI still shows empty data”.

### 1.4 Current local data state

Observed:

- `backend/decisionos.db` contains app tables and demo rows
- repository-root `decisionos.db` appears to be a different file and is not the current app DB for normal `cd backend && uvicorn ...` startup

Implication:

- any reset or reseed step must target the actual runtime DB path intentionally
- blindly deleting one `decisionos.db` file is unsafe and may not affect the running app

---

## 2. Hypothesis

Primary hypothesis:

- The remote environment is either using a different DB/Chroma path than expected, or it has an already-initialized persistent volume that bypasses the fresh-start bootstrap assumptions.

Secondary hypothesis:

- Operators assume `backend/scripts/seed_demo.py` seeds all demo content, but it only seeds the vector store, leaving SQLite empty or stale.

---

## 3. Scope and Non-Goals

### 3.1 In Scope

- verify actual runtime DB path and Chroma path
- verify whether bootstrap is running
- verify whether SQLite demo seed and vector demo seed are both occurring
- add one explicit seed script
- define a safe local reset workflow that preserves AI provider settings

### 3.2 Out of Scope

- no automatic destructive reset during app startup
- no deletion of AI settings or provider credentials
- no speculative changes to remote infra before path verification

---

## 4. Target Design

### 4.1 Desired Operator Experience

One explicit command should exist for demo initialization, for example:

```bash
cd backend && python -m scripts.seed_demo_full
```

Optional modes:

- `--db-only`
- `--vector-only`
- `--reset-demo-data`

### 4.2 Safety Rules

- never delete `ai_settings`
- never delete provider/API configuration
- reset only demo-generated entities and demo vector collections when explicitly requested
- default seeding should be idempotent and non-destructive

---

## 5. Implementation Tasks

### Task 1: Document runtime path resolution and verify current startup behavior

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Test/Inspect: `backend/app/core/settings.py`
- Test/Inspect: `backend/app/db/engine.py`
- Test/Inspect: `backend/app/main.py`

**Step 1: Confirm current path behavior**

Verify and document:

- `DECISIONOS_DB_PATH` default is `./decisionos.db`
- `DECISIONOS_CHROMA_PATH` default is `./chroma_data`
- relative paths resolve against the process cwd

**Step 2: Record current startup assumptions**

Document that:

- `initialize_database()` runs at app startup
- bootstrap seeds SQLite demo data
- vector demo seeding only occurs when Chroma collections are empty

**Step 3: Update docs with operator warning**

Add a warning that starting from different working directories can create different SQLite files when env vars are not absolute.

**Step 4: Commit**

```bash
git add README.md backend/README.md
git commit -m "docs: clarify demo data path resolution and startup seeding behavior"
```

### Task 2: Add failing tests for a unified demo seed entrypoint

**Files:**
- Create: `backend/tests/test_seed_demo_full.py`

**Step 1: Write the failing test**

Cover:

- unified seed command populates SQLite demo ideas
- unified seed command populates vector store
- running twice is idempotent
- AI settings remain untouched

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_seed_demo_full.py -v --tb=short
```

Expected: FAIL because the unified seed entrypoint does not exist yet.

**Step 3: Commit**

```bash
git add backend/tests/test_seed_demo_full.py
git commit -m "test: add failing coverage for unified demo seed workflow"
```

### Task 3: Add a unified explicit seed script

**Files:**
- Create: `backend/scripts/seed_demo_full.py`
- Modify: `backend/scripts/seed_demo.py`
- Modify: `backend/app/db/bootstrap.py`
- Test: `backend/tests/test_seed_demo_full.py`

**Step 1: Implement explicit seed orchestration**

Add a script that:

- initializes schema/workspace/users safely
- runs SQLite demo seeding
- runs vector-store demo seeding
- supports `--db-only` and `--vector-only`

**Step 2: Keep bootstrap behavior simple**

Bootstrap may remain as-is, but the script becomes the explicit operator path for remote seeding and local reseeding.

**Step 3: Decide whether to keep or repurpose the old script**

Recommended:

- keep `seed_demo.py` as vector-only compatibility wrapper
- add clear help text pointing operators to `seed_demo_full.py`

**Step 4: Run tests to verify pass**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_seed_demo_full.py -v --tb=short
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/seed_demo_full.py backend/scripts/seed_demo.py backend/app/db/bootstrap.py backend/tests/test_seed_demo_full.py
git commit -m "feat: add unified demo seed script for sqlite and vector store"
```

### Task 4: Add a safe local reset workflow for demo data only

**Files:**
- Create: `backend/scripts/reset_demo_data.py`
- Test: `backend/tests/test_reset_demo_data.py`
- Modify: `README.md`
- Modify: `backend/README.md`

**Step 1: Write the failing reset test**

Cover:

- deletes demo ideas and related demo entities only
- clears demo vector data only
- preserves `ai_settings`
- preserves non-demo user-created records

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_reset_demo_data.py -v --tb=short
```

Expected: FAIL because no safe reset script exists yet.

**Step 3: Implement reset script**

Script behavior:

- target only rows/collections created by demo seeding
- remove demo ids/patterns/news from vector store
- leave provider/API settings intact

**Step 4: Run tests to verify pass**

Run:

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_reset_demo_data.py -v --tb=short
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/reset_demo_data.py backend/tests/test_reset_demo_data.py README.md backend/README.md
git commit -m "feat: add safe local demo reset workflow"
```

### Task 5: Verify the full reset-and-reseed flow locally

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`

**Step 1: Stop the local backend**

Ensure no process is holding the active SQLite file before reset.

**Step 2: Run the safe demo reset**

Run the new reset script against the actual runtime DB/Chroma paths.

**Step 3: Run the unified seed script**

Use the explicit seed command and verify:

- demo ideas exist in SQLite
- demo notifications exist
- vector collections contain demo ideas/news/patterns

**Step 4: Launch the app and verify UI**

Check:

- idea list shows demo ideas
- notifications are populated
- proactive features depending on vector seed behave as expected

**Step 5: Commit doc updates**

```bash
git add README.md backend/README.md
git commit -m "docs: add verified local reset and reseed workflow"
```

### Task 6: Define remote operator procedure

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Optionally Modify: deployment docs if applicable

**Step 1: Document remote checks**

Operators must verify:

- actual `DECISIONOS_DB_PATH`
- actual `DECISIONOS_CHROMA_PATH`
- whether storage is ephemeral or persistent

**Step 2: Document remote seed command**

Use the unified seed script rather than relying on startup bootstrap.

**Step 3: Document fallback diagnostics**

If remote still shows empty data, collect:

- effective env vars
- DB row counts
- vector collection counts
- startup logs showing bootstrap execution

**Step 4: Commit**

```bash
git add README.md backend/README.md
git commit -m "docs: add remote demo data seeding and diagnostics procedure"
```

---

## 6. Local Reset Execution Plan

This is the exact flow to run later after code exists and after user approval:

1. Identify the actual runtime DB and Chroma paths.
2. Stop the backend process so SQLite is not locked.
3. Run the safe demo reset script.
4. Run the unified seed script.
5. Restart backend.
6. Verify:
   - demo ideas count
   - demo notifications count
   - vector demo counts
   - UI visibility

Important:

- do not manually delete `ai_settings`
- do not blindly delete all tables
- do not assume repository-root `decisionos.db` is the active DB

---

## 7. Success Criteria

The issue is considered resolved only when:

- one explicit script can seed both SQLite and vector demo data
- local reset/reseed works without deleting AI provider settings
- docs clearly explain path resolution and runtime differences
- remote operators no longer rely on implicit startup side effects
