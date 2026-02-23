# PRD Prompt Quality Improvement — Design Doc

**Goal:** Improve PRD markdown depth and requirement acceptance criteria quality without changing schemas, routes, or frontend.

**Problem:** After the parallel SSE refactor, prompts were slimmed aggressively. The result:

- PRD section `content` fields are 1-2 sentences — too thin for PMs or developers to act on
- Requirement `acceptance_criteria` are vague assertions, not verifiable behaviour descriptions

**Approach:** Method A — add writing-spec + inline bad/good example to the two affected prompt builders. No schema changes. No token explosion.

---

## Changes

### `build_prd_requirements_prompt`

Add field-level writing rules:

- `description`: 2-3 sentences covering "what this requirement is + why it's needed"
- `rationale`: business/user value, must not repeat description
- `acceptance_criteria`: 3-6 items, each a verifiable behaviour statement in the form "[Actor] can/should [specific action + observable outcome]"
- Inline contrast: one good AC example vs one bad AC example

### `build_prd_markdown_prompt`

Add section-level writing rules:

- Each section `content` must be ≥3 sentences
- Must follow the arc: background → problem/opportunity → approach/decision → expected outcome
- Named section guidance:
  - **Executive Summary**: what the product is, who it's for, core value prop (3-5 sentences)
  - **Problem Statement**: specific pain point + why existing solutions fall short
  - **User Personas**: 1-2 typical users with role / goal / pain
  - **Key Capabilities**: user-facing capabilities, not implementation details
  - **Out of Scope**: explicit exclusions to prevent scope creep
  - All other sections: min 3 sentences, self-contained (reader needs no external context)

---

## Non-changes

- `build_prd_backlog_prompt`: no change (backlog quality acceptable)
- All schemas, routes, frontend: no change
- Token budget: estimate +300-500 chars per prompt call — acceptable

---

## Validation

- Run existing 91 backend tests — must still pass
- Playwright E2E: navigate to PRD page for an idea with a frozen baseline, trigger generation, verify:
  1. SSE stream shows progressive requirements then backlog
  2. Final PRD renders with substantive section content
  3. Requirements have ≥3 acceptance criteria each with concrete language
