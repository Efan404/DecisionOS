import { useMemo, useState } from 'react'

import type {
  DecisionContext,
  PrdBundle,
  PrdFeedbackDimensions,
  PrdFeedbackLatest,
  PrdOutput,
} from '../../lib/schemas'
import { PrdBacklogPanel } from './PrdBacklogPanel'
import { PrdFeedbackCard } from './PrdFeedbackCard'

type PrdViewProps = {
  prd?: PrdOutput
  bundle?: PrdBundle
  baselineId?: string | null
  feedbackLatest?: PrdFeedbackLatest
  context: DecisionContext
  loading?: boolean
  errorMessage?: string | null
  onRetry?: () => void
  onSubmitFeedback?: (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
    comment?: string
  }) => Promise<void>
  feedbackSubmitting?: boolean
  feedbackError?: string | null
}

// Status banner — only one state rendered at a time (loading > error > idle)
function StatusBanner({
  loading,
  errorMessage,
  hasStaleOutput,
  onRetry,
}: {
  loading: boolean
  errorMessage: string | null
  hasStaleOutput: boolean
  onRetry?: () => void
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
        <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
        Generating PRD and backlog&hellip;
        {hasStaleOutput ? (
          <span className="text-xs text-blue-500">(previous output shown below)</span>
        ) : null}
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm leading-5 text-red-700">{errorMessage}</p>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="shrink-0 cursor-pointer rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-400"
            >
              Retry
            </button>
          ) : null}
        </div>
        {hasStaleOutput ? (
          <p className="mt-1.5 text-xs text-amber-700">
            Showing last successful output as stale snapshot.
          </p>
        ) : null}
      </div>
    )
  }

  return null
}

export function PrdView({
  prd,
  bundle,
  baselineId = null,
  feedbackLatest,
  context,
  loading = false,
  errorMessage = null,
  onRetry,
  onSubmitFeedback,
  feedbackSubmitting = false,
  feedbackError = null,
}: PrdViewProps) {
  const output = prd ?? bundle?.output
  const [selectedRequirementIdInput, setSelectedRequirementIdInput] = useState<string | null>(null)
  const [showMarkdown, setShowMarkdown] = useState(false)
  const [activeTab, setActiveTab] = useState<'requirements' | 'sections'>('requirements')

  const selectedRequirementId = output?.requirements.some(
    (item) => item.id === selectedRequirementIdInput
  )
    ? selectedRequirementIdInput
    : (output?.requirements[0]?.id ?? null)

  const inScopeTitles = context.scope?.in_scope.map((item) => item.title) ?? []

  const requirementsById = useMemo(
    () =>
      Object.fromEntries(
        (output?.requirements ?? []).map((item) => [item.id, item.title] as const)
      ),
    [output]
  )

  // Bug fix: was `Boolean(errorMessage && bundle?.output)` — same logic, kept identical
  const hasStaleOutput = Boolean(errorMessage && bundle?.output)

  return (
    <section className="mx-auto w-full max-w-7xl space-y-5 p-6">
      {/* ── Page header ── */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">PRD + Backlog</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Product requirements synthesized from decisions.
            {baselineId ? (
              <span className="ml-2 font-mono text-xs text-slate-400">
                baseline: {baselineId}
              </span>
            ) : null}
          </p>
        </div>
        {output ? (
          <button
            type="button"
            onClick={() => setShowMarkdown((previous) => !previous)}
            className="cursor-pointer rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
          >
            {showMarkdown ? 'Hide Markdown' : 'View Raw Markdown'}
          </button>
        ) : null}
      </header>

      {/* ── Status banner: only one state at a time ── */}
      <StatusBanner
        loading={loading}
        errorMessage={errorMessage}
        hasStaleOutput={hasStaleOutput}
        onRetry={onRetry}
      />

      {/* ── Decision context — compact horizontal strip ── */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-4">
        <p className="mb-3 text-[10px] font-semibold tracking-widest text-slate-400 uppercase">
          Decision Context
        </p>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">
              Idea
            </dt>
            <dd
              className="mt-0.5 truncate text-sm text-slate-800"
              title={context.idea_seed ?? undefined}
            >
              {context.idea_seed ?? 'N/A'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">
              Confirmed Path
            </dt>
            <dd className="mt-0.5 truncate text-sm text-slate-800">
              {context.confirmed_dag_path_id ?? 'N/A'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">
              Selected Plan
            </dt>
            <dd className="mt-0.5 truncate text-sm text-slate-800">
              {context.selected_plan_id ?? 'N/A'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">
              Scope Frozen
            </dt>
            <dd className="mt-0.5 text-sm text-slate-800">
              {context.scope_frozen ? 'Yes' : 'No'}
            </dd>
          </div>
          {inScopeTitles.length > 0 ? (
            <div className="sm:col-span-2 lg:col-span-4">
              <dt className="text-[10px] font-medium tracking-wide text-slate-400 uppercase">
                In Scope
              </dt>
              <dd className="mt-0.5 text-sm text-slate-800">{inScopeTitles.join(' · ')}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      {/* ── Raw markdown (collapsible, hidden by default) ── */}
      {showMarkdown && output ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-2.5">
            <span className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase">
              Raw Markdown
            </span>
            <button
              type="button"
              onClick={() => setShowMarkdown(false)}
              className="cursor-pointer text-xs text-slate-500 transition-colors hover:text-slate-300"
            >
              Close
            </button>
          </div>
          <pre className="max-h-[40vh] overflow-auto px-5 py-4 text-xs leading-6 break-words whitespace-pre-wrap text-slate-200">
            {output.markdown}
          </pre>
        </div>
      ) : null}

      {/* ── Main content or empty state ── */}
      {output ? (
        <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
          {/* ── Left: tabbed Requirements / Sections ── */}
          <div className="space-y-4">
            {/* Tab switcher */}
            <div className="flex w-fit gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-1">
              {(['requirements', 'sections'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`cursor-pointer rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
                    activeTab === tab
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {tab}
                  <span className="ml-1.5 rounded bg-slate-200 px-1 py-0.5 text-[10px] font-semibold text-slate-500">
                    {tab === 'requirements' ? output.requirements.length : output.sections.length}
                  </span>
                </button>
              ))}
            </div>

            {/* Requirements list */}
            {activeTab === 'requirements' ? (
              <ul className="space-y-2">
                {output.requirements.map((item) => {
                  const active = selectedRequirementId === item.id
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedRequirementIdInput(item.id)}
                        className={`w-full cursor-pointer rounded-xl border px-4 py-3.5 text-left transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                          active
                            ? 'border-cyan-400 bg-cyan-50 shadow-sm ring-1 ring-cyan-200'
                            : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          <span
                            className={`mt-0.5 shrink-0 font-mono text-[10px] font-bold ${active ? 'text-cyan-600' : 'text-slate-400'}`}
                          >
                            {item.id}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold leading-5 text-slate-900">
                              {item.title}
                            </p>
                            <p className="mt-1 text-xs leading-5 text-slate-600">
                              {item.description}
                            </p>
                            {item.rationale ? (
                              <p className="mt-1.5 text-xs italic text-slate-400">
                                {item.rationale}
                              </p>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            ) : null}

            {/* Sections list */}
            {activeTab === 'sections' ? (
              <ul className="space-y-2">
                {output.sections.map((section) => (
                  <li
                    key={section.id}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-3.5"
                  >
                    <p className="text-[10px] font-semibold tracking-widest text-slate-400 uppercase">
                      {section.title}
                    </p>
                    <p className="mt-1.5 text-sm leading-6 text-slate-800">{section.content}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          {/* ── Right: selected-req chip + Backlog + Feedback ── */}
          <div className="space-y-4">
            {/* Selected requirement context chip */}
            {selectedRequirementId ? (
              <div className="flex items-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2">
                <span className="shrink-0 font-mono text-[10px] font-bold text-cyan-600">
                  {selectedRequirementId}
                </span>
                <span className="truncate text-xs text-slate-600">
                  {requirementsById[selectedRequirementId] ?? ''}
                </span>
              </div>
            ) : (
              <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-400">
                Select a requirement to filter linked backlog items.
              </p>
            )}

            <PrdBacklogPanel
              items={output.backlog.items}
              selectedRequirementId={selectedRequirementId}
              onSelectRequirement={setSelectedRequirementIdInput}
            />

            {baselineId && onSubmitFeedback ? (
              <PrdFeedbackCard
                key={`${baselineId}:${feedbackLatest?.submitted_at ?? 'draft'}`}
                baselineId={baselineId}
                latest={feedbackLatest}
                disabled={feedbackSubmitting}
                submitting={feedbackSubmitting}
                errorMessage={feedbackError}
                onSubmit={onSubmitFeedback}
              />
            ) : null}
          </div>
        </div>
      ) : (
        /* ── Empty / no-output state ── */
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center">
          {loading ? (
            <p className="text-sm text-slate-500">Preparing PRD and backlog&hellip;</p>
          ) : (
            <>
              <p className="text-sm text-slate-600">
                {errorMessage ? 'Generation failed.' : 'No PRD generated yet.'}
              </p>
              {onRetry && !loading ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-4 cursor-pointer rounded-lg border border-slate-300 bg-white px-5 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
                >
                  Generate
                </button>
              ) : null}
            </>
          )}
        </div>
      )}
    </section>
  )
}
