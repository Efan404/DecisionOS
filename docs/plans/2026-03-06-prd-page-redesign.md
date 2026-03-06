# PRD Page Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify PRD page loading UX, combine Requirements + Backlog into a left-right split, and move export buttons into the backlog panel.

**Architecture:** Three surgical edits to existing components. No new files needed. PrdView gets a new split-pane layout for the Requirements tab. PrdBacklogPanel gains export button props. StatusBanner loading branch and empty-state spinner are removed.

**Tech Stack:** React, TypeScript, Tailwind CSS

---

### Task 1: Remove redundant loading indicators from PrdView

**Files:**
- Modify: `frontend/components/prd/PrdView.tsx:40-97` (StatusBanner loading branch)
- Modify: `frontend/components/prd/PrdView.tsx:471-487` (empty state spinner)

**Changes:**
1. In `StatusBanner`, remove the `if (loading)` branch entirely — keep only the error branch
2. In the empty state (no output), replace the spinner with static text "Waiting for agent..."

### Task 2: Add export button props to PrdBacklogPanel

**Files:**
- Modify: `frontend/components/prd/PrdBacklogPanel.tsx`

**Changes:**
1. Add `onExportJson`, `onExportCsv`, `exporting` to component props
2. Render export buttons in the panel header, next to the "Linked to req" toggle

### Task 3: Requirements tab becomes left-right split with backlog

**Files:**
- Modify: `frontend/components/prd/PrdView.tsx`

**Changes:**
1. Move the requirement-filter indicator + PrdBacklogPanel + requirement selection state into the Requirements tab content area
2. Use a `grid grid-cols-1 lg:grid-cols-2 gap-4` layout: left = requirements list, right = backlog panel
3. Remove backlog panel and requirement filter from the bottom area (where it currently shows on all tabs)
4. Move export button props from PrdView header to PrdBacklogPanel

### Task 4: Remove export buttons from PrdView header

**Files:**
- Modify: `frontend/components/prd/PrdView.tsx:304-329` (header export buttons)

**Changes:**
1. Remove the `onExportJson`/`onExportCsv`/`exporting` rendering from the page `<header>`
2. Pass them through to PrdBacklogPanel instead

### Task 5: Update tests

**Files:**
- Modify: `frontend/components/prd/__tests__/PrdPageBaseline.test.tsx`

**Changes:**
1. Export button tests: click Requirements tab first, then find Export buttons inside the backlog panel
2. Verify existing tests still pass with layout changes
