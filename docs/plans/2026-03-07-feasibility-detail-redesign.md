# Feasibility Plan Detail Redesign

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the feasibility plan detail page into a left-right split layout with "Confirm This Plan" inside the card and a new competitors panel on the right.

**Architecture:** Add a `competitors` field to the Plan schema (backend Pydantic + frontend Zod). Update the LLM prompt to generate competitor data. Add mock competitor data to seed_demo.py. Redesign PlanDetail.tsx as a two-column layout and move the confirm button from FeasibilityDetailClient into PlanDetail.

**Tech Stack:** FastAPI/Pydantic (backend schema), Zod/TypeScript (frontend schema), Tailwind CSS (layout), LangGraph feasibility subgraph (prompt)

---

### Task 1: Add `Competitor` model to backend schema

**Files:**
- Modify: `backend/app/schemas/common.py`
- Modify: `backend/app/schemas/feasibility.py`

**Step 1: Add Competitor model to common.py**

Add after `ReasoningBreakdown` (line 32):

```python
class Competitor(BaseModel):
    name: str
    url: str | None = None
    similarity: str
```

- `name`: competitor product name
- `url`: link to competitor (nullable — LLM may not always have a valid URL)
- `similarity`: one-sentence description of how this competitor is similar

**Step 2: Add competitors field to Plan model in feasibility.py**

Import `Competitor` from common and add to `Plan`:

```python
from app.schemas.common import ReasoningBreakdown, ScoreBreakdown, Competitor

class Plan(BaseModel):
    id: str
    name: str
    summary: str
    score_overall: float = Field(ge=0, le=10)
    scores: ScoreBreakdown
    reasoning: ReasoningBreakdown
    recommended_positioning: str
    competitors: list[Competitor] = Field(default_factory=list)
```

`default_factory=list` ensures backward compatibility — existing plans without competitors won't break.

**Step 3: Commit**

```bash
git add backend/app/schemas/common.py backend/app/schemas/feasibility.py
git commit -m "feat(schema): add Competitor model and competitors field to Plan"
```

---

### Task 2: Add competitor schema to frontend

**Files:**
- Modify: `frontend/lib/schemas.ts`

**Step 1: Add competitorSchema and update feasibilityPlanSchema**

After `reasoningBreakdownSchema` (line 53), add:

```typescript
export const competitorSchema = z.object({
  name: z.string().min(1),
  url: z.string().nullable().optional(),
  similarity: z.string().min(1),
})
```

Update `feasibilityPlanSchema` to include competitors:

```typescript
export const feasibilityPlanSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  summary: z.string().min(1),
  score_overall: z.number().min(0).max(10),
  scores: scoreBreakdownSchema,
  reasoning: reasoningBreakdownSchema,
  recommended_positioning: z.string().min(1),
  competitors: z.array(competitorSchema).default([]),
})
```

Add type export at bottom:

```typescript
export type Competitor = z.infer<typeof competitorSchema>
```

**Step 2: Commit**

```bash
git add frontend/lib/schemas.ts
git commit -m "feat(schema): add competitor schema to frontend"
```

---

### Task 3: Update LLM prompt to generate competitors

**Files:**
- Modify: `backend/app/core/prompts.py`

**Step 1: Update build_single_plan_prompt**

Add competitors to the MUST include list in `build_single_plan_prompt` (around line 88-97):

```python
    return (
        "Given the following product context, generate exactly ONE detailed feasibility plan "
        f"following {archetype}.\n\n"
        f"{context}\n"
        "The plan MUST include:\n"
        '  - id: a short unique slug (e.g. "plan1", "plan2", "plan3")\n'
        "  - name: concise plan name\n"
        "  - summary: one-sentence value proposition\n"
        "  - score_overall: float 0-10\n"
        "  - scores: object with keys technical_feasibility, market_viability, execution_risk (each float 0-10)\n"
        "  - reasoning: object with keys technical_feasibility, market_viability, execution_risk (each a short string)\n"
        "  - recommended_positioning: one sentence on go-to-market positioning\n"
        "  - competitors: array of 2-4 objects, each with name (product name), url (homepage URL or null), "
        "similarity (one sentence on what makes this competitor similar or relevant)\n"
        "Return a single JSON object representing this plan (not wrapped in an array or 'plans' key)."
    )
```

**Step 2: Commit**

```bash
git add backend/app/core/prompts.py
git commit -m "feat(prompt): add competitors field to feasibility plan generation"
```

---

### Task 4: Add mock competitor data to seed_demo.py

**Files:**
- Modify: `backend/app/db/seed_demo.py`

**Step 1: Add competitors to each plan in both demo ideas' context_json**

For Idea 1 (AI Recipe Recommender), add to each plan object:

Plan 1 (Bootstrapped MVP):
```python
"competitors": [
    {"name": "Mealime", "url": "https://www.mealime.com", "similarity": "Meal planning app with grocery lists, but lacks AI-driven personalization"},
    {"name": "Eat This Much", "url": "https://www.eatthismuch.com", "similarity": "Auto-generates meal plans based on nutrition goals, closest direct competitor"},
    {"name": "Whisk", "url": "https://whisk.com", "similarity": "Recipe aggregator with smart grocery lists, acquired by Samsung for food-tech platform"},
]
```

Plan 2 (VC-Funded Growth):
```python
"competitors": [
    {"name": "Noom", "url": "https://www.noom.com", "similarity": "Health coaching platform with meal tracking; validates enterprise wellness market"},
    {"name": "Lifesum", "url": "https://lifesum.com", "similarity": "Diet and nutrition app with meal plans, strong mobile presence"},
    {"name": "PlateJoy", "url": "https://www.platejoy.com", "similarity": "Personalized meal planning with grocery delivery, closest to the VC-funded vision"},
]
```

Plan 3 (Platform / Ecosystem):
```python
"competitors": [
    {"name": "Spoonacular API", "url": "https://spoonacular.com/food-api", "similarity": "Recipe and nutrition API used by fitness apps — direct competitor in the API space"},
    {"name": "Edamam", "url": "https://www.edamam.com", "similarity": "Nutrition analysis and recipe search API licensed to health platforms"},
    {"name": "Yummly", "url": "https://www.yummly.com", "similarity": "Recipe platform with taste profile engine, acquired by Whirlpool for appliance integration"},
]
```

For Idea 2 (Local Event Discovery), add similarly relevant competitors to each of its 3 plans.

**Step 2: Commit**

```bash
git add backend/app/db/seed_demo.py
git commit -m "feat(seed): add mock competitor data to demo feasibility plans"
```

---

### Task 5: Redesign PlanDetail.tsx — left-right split with confirm button

**Files:**
- Modify: `frontend/components/feasibility/PlanDetail.tsx`
- Modify: `frontend/components/feasibility/FeasibilityDetailClient.tsx`

**Step 1: Move confirm button logic into PlanDetail**

Update `PlanDetail` props to accept confirm handler and loading state:

```typescript
type PlanDetailProps = {
  plan: FeasibilityPlan | null
  onConfirm?: () => void
  confirming?: boolean
}
```

**Step 2: Redesign PlanDetail as two-column layout**

Left column (wider, ~60%): scores grid + reasoning sections + recommended positioning + confirm button at bottom.

Right column (~40%): "Similar Products" panel listing competitors with name, similarity text, and external link icon if URL exists.

Layout structure:
```tsx
<section className="mx-auto w-full max-w-5xl rounded-xl border border-[#1e1e1e]/15 bg-white p-6 shadow-sm">
  {/* Header: name + summary + overall score badge */}
  <div className="...">
    <h1 className="text-2xl font-bold text-[#1e1e1e]">{plan.name}</h1>
    <span className="... bg-[#b9eb10] ...">
      {plan.score_overall.toFixed(1)}
    </span>
  </div>
  <p className="mt-2 text-sm text-[#1e1e1e]/60">{plan.summary}</p>

  {/* Two-column body */}
  <div className="mt-6 grid gap-6 lg:grid-cols-5">
    {/* Left: 3 cols */}
    <div className="lg:col-span-3 space-y-4">
      {/* Score cards in 3-col grid */}
      {/* Reasoning sections */}
      {/* Recommended positioning */}
      {/* Confirm button */}
      {onConfirm && (
        <button onClick={onConfirm} disabled={confirming} className="...">
          {confirming ? 'Confirming...' : 'Confirm This Plan'}
        </button>
      )}
    </div>

    {/* Right: 2 cols — competitors */}
    <div className="lg:col-span-2">
      <div className="rounded-xl border border-[#1e1e1e]/10 bg-[#f5f5f5] p-4">
        <h3 className="text-sm font-semibold text-[#1e1e1e]">Similar Products</h3>
        <ul className="mt-3 space-y-3">
          {plan.competitors.map((c) => (
            <li key={c.name} className="...">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{c.name}</span>
                {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer">↗</a>}
              </div>
              <p className="text-xs text-[#1e1e1e]/50">{c.similarity}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  </div>
</section>
```

**Step 3: Simplify FeasibilityDetailClient**

Remove the confirm button div from FeasibilityDetailClient. Pass `onConfirm` and `confirming` props to PlanDetail instead:

```tsx
export function FeasibilityDetailClient({ planId }: FeasibilityDetailClientProps) {
  const [confirming, setConfirming] = useState(false)
  // ... existing state/hooks ...

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      // ... existing confirm logic (setPlan, patchIdeaContext, etc.) ...
    } finally {
      setConfirming(false)
    }
  }

  return (
    <PlanDetail plan={plan} onConfirm={handleConfirm} confirming={confirming} />
  )
}
```

**Step 4: Style the layout to match design system**

- Use `#b9eb10` lime accent for the overall score badge and confirm button
- Use `#1e1e1e` dark for text, `#f5f5f5` for card backgrounds
- Competitors panel: subtle border, each competitor in a mini card
- External links: small arrow icon, opens in new tab
- Responsive: stack columns on mobile (single column below `lg:`)

**Step 5: Commit**

```bash
git add frontend/components/feasibility/PlanDetail.tsx frontend/components/feasibility/FeasibilityDetailClient.tsx
git commit -m "feat(feasibility): redesign plan detail as left-right split with competitors panel"
```

---

### Task 6: Update local DB seed data and verify

**Step 1: Restart backend to pick up seed changes**

```bash
cd backend && python -m uvicorn app.main:app --reload
```

**Step 2: Verify in browser**

- Navigate to feasibility plan detail page
- Confirm left-right layout renders correctly
- Confirm "Similar Products" panel shows competitor data
- Confirm "Confirm This Plan" button works inside the card
- Test responsive layout (resize browser below lg breakpoint)

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(feasibility): complete plan detail redesign with competitors panel"
```
