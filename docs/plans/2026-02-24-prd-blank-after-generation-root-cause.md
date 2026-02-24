# Bug: PRD blank after generation, requires page refresh

**Date:** 2026-02-24
**Symptom:** PRD generates successfully (backend logs show `agent.prd.stream.done`), but the frontend shows blank content. Refreshing the page reveals the content.

## Root Cause

Two `next.config` files existed in the repo:

| File                                         | Used by Next.js?                         | `reactStrictMode`         |
| -------------------------------------------- | ---------------------------------------- | ------------------------- |
| `/next.config.mjs` (project root)            | **Yes** — Next.js reads config from root | `true` (original)         |
| `/frontend/next.config.ts` (frontend subdir) | **No** — never loaded                    | `false` (our fix attempt) |

`next dev frontend` is run from the project root with `next dev frontend`, so Next.js reads `next.config.mjs` at the root, not anything inside `frontend/`. The `frontend/next.config.ts` we created was silently ignored.

Because `reactStrictMode: true` remained active, React 18 StrictMode double-invoked every `useEffect` in development:

1. **Effect run #1** starts: `cancelled = false`, `inFlightGenerationKeyRef = requestKey`, SSE stream begins.
2. **StrictMode cleanup** fires immediately: `cancelled = true`, `inFlightGenerationKeyRef = null`.
3. **Effect run #2** starts: `globalPrdGenerationRequests.has(requestKey)` is `true` (set in run #1), so no new SSE request is sent — correct.
4. **Run #1's `async run()`** is still executing in the background (the SSE stream is live).
5. ~20 seconds later, backend finishes, `streamPost` resolves, `donePayload` is set.
6. Code checks `if (!cancelled && donePayload)` — **`cancelled` is `true`** → the block is skipped.
7. `loadIdeaDetail` and `replaceContext` are never called → frontend store is never updated → blank page.

### Evidence from backend logs

```
14:32:05.637  POST /prd/stream  start
14:32:25.913  generate_structured SUCCESS
14:32:26.004  agent.prd.stream.done idea_version=41
14:32:26.005  HTTP 200 done (20368ms)
14:33:29.160  GET /ideas/...     ← 63 seconds later, triggered by manual refresh
```

The 63-second gap between stream completion and the GET confirms `loadIdeaDetail` was never called after the stream finished.

Also observed: two nearly-simultaneous `GET /ideas/` requests just before `POST /prd/stream` — the StrictMode double-invocation of the page's mount effects.

## Fix

1. Set `reactStrictMode: false` in `/next.config.mjs` (the file Next.js actually reads).
2. Delete `/frontend/next.config.ts` (was never loaded, caused confusion).

```js
// next.config.mjs
const config = {
  reactStrictMode: false,  // was: true
  async rewrites() { ... }
}
```

**Requires restarting the Next.js dev server** — `next.config` is read at startup, not hot-reloaded.

## Why `cancelled` flag exists

The `cancelled` ref in `PrdPage.tsx` is intentional: it prevents a stale async callback from updating React state after the component unmounts or its effect reruns (e.g. navigating away mid-generation). In production (no StrictMode), it works correctly. The bug was purely a dev-mode artifact from StrictMode's deliberate double-invocation.
