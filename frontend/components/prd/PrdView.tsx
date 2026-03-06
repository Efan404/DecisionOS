'use client'

import { useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type {
  DecisionContext,
  PrdBundle,
  // DISABLED: PrdFeedbackDimensions, PrdFeedbackLatest — used by backlog/feedback panel
  PrdFeedbackDimensions,
  PrdFeedbackLatest,
  PrdOutput,
} from '../../lib/schemas'
// DISABLED: PrdBacklogPanel and PrdFeedbackCard — re-enable with Requirements/Backlog tabs
// import { PrdBacklogPanel } from './PrdBacklogPanel'
// import { PrdFeedbackCard } from './PrdFeedbackCard'

type PrdStreamPartials = {
  requirements: PrdOutput['requirements'] | null
  backlog: PrdOutput['backlog'] | null
}

type PrdViewProps = {
  prd?: PrdOutput
  bundle?: PrdBundle
  baselineId?: string | null
  feedbackLatest?: PrdFeedbackLatest
  context: DecisionContext
  loading?: boolean
  isRegenerate?: boolean
  errorMessage?: string | null
  onRetry?: () => void
  onSubmitFeedback?: (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
    comment?: string
  }) => Promise<void>
  feedbackSubmitting?: boolean
  feedbackError?: string | null
  streamPartials?: PrdStreamPartials | null
}

// Status banner — one state at a time: loading > error > idle
function StatusBanner({
  loading,
  isRegenerate,
  errorMessage,
  hasStaleOutput,
  onRetry,
}: {
  loading: boolean
  isRegenerate: boolean
  errorMessage: string | null
  hasStaleOutput: boolean
  onRetry?: () => void
}) {
  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700"
      >
        <span
          aria-hidden="true"
          className="inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-blue-400 border-t-transparent"
        />
        {isRegenerate ? 'Regenerating PRD and backlog\u2026' : 'Generating PRD and backlog\u2026'}
        {hasStaleOutput ? (
          <span className="text-xs text-blue-500">(previous output shown below)</span>
        ) : null}
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm leading-5 text-red-700">{errorMessage}</p>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="shrink-0 cursor-pointer rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors duration-150 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-400"
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

// Copy button with 2s feedback
function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard API unavailable — silent fail
    }
  }, [text])

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied!' : label}
      className="flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors duration-150 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
    >
      {copied ? (
        <>
          <svg
            aria-hidden="true"
            className="h-3.5 w-3.5 text-emerald-500"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l3.5 3.5L13 4.5" />
          </svg>
          Copied!
        </>
      ) : (
        <>
          <svg
            aria-hidden="true"
            className="h-3.5 w-3.5"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <rect x="5" y="5" width="8" height="9" rx="1.5" />
            <path
              strokeLinecap="round"
              d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v8A1.5 1.5 0 003.5 13H5"
            />
          </svg>
          {label}
        </>
      )}
    </button>
  )
}

// PRD document panel — rendered markdown + raw toggle + copy
function MarkdownPanel({ markdown }: { markdown: string }) {
  const [showRaw, setShowRaw] = useState(false)

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* toolbar */}
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-100 p-0.5">
          <button
            type="button"
            onClick={() => setShowRaw(false)}
            className={`cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
              !showRaw ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            Preview
          </button>
          <button
            type="button"
            onClick={() => setShowRaw(true)}
            className={`cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
              showRaw ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            Raw
          </button>
        </div>
        <CopyButton text={markdown} label="Copy Markdown" />
      </div>

      {/* content */}
      {showRaw ? (
        <pre className="max-h-[60vh] overflow-auto px-5 py-4 font-mono text-xs leading-6 break-words whitespace-pre-wrap text-slate-700">
          {markdown}
        </pre>
      ) : (
        <div className="max-h-[60vh] max-w-none overflow-auto px-5 py-5 text-sm leading-7 text-slate-700 [&_a]:font-medium [&_a]:text-blue-600 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-slate-300 [&_blockquote]:pl-4 [&_blockquote]:text-slate-500 [&_blockquote]:italic [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs [&_h1]:mt-6 [&_h1]:mb-4 [&_h1]:text-base [&_h1]:leading-8 [&_h1]:font-bold [&_h1]:text-slate-900 [&_h2]:mt-5 [&_h2]:mb-3 [&_h2]:text-sm [&_h2]:leading-7 [&_h2]:font-semibold [&_h2]:text-slate-900 [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:text-sm [&_h3]:font-medium [&_h3]:text-slate-800 [&_hr]:my-6 [&_hr]:border-slate-200 [&_li]:mb-1 [&_li]:leading-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-3 [&_pre]:rounded-lg [&_pre]:bg-slate-950 [&_pre]:p-4 [&_pre_code]:bg-transparent [&_pre_code]:text-slate-200 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-slate-200 [&_td]:px-3 [&_td]:py-2 [&_td]:text-xs [&_th]:border [&_th]:border-slate-200 [&_th]:bg-slate-50 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

// DISABLED: multi-tab type — only markdown tab is active
// type MainTab = 'markdown' | 'requirements' | 'sections'
type MainTab = 'markdown'

export function PrdView({
  prd,
  bundle,
  baselineId = null,
  feedbackLatest,
  context,
  loading = false,
  isRegenerate = false,
  errorMessage = null,
  onRetry,
  onSubmitFeedback,
  feedbackSubmitting = false,
  feedbackError = null,
  streamPartials = null,
}: PrdViewProps) {
  const output = prd ?? bundle?.output
  // DISABLED: requirement selection state (used by Requirements tab and Backlog panel)
  // const [selectedRequirementIdInput, setSelectedRequirementIdInput] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<MainTab>('markdown')

  // DISABLED: requirement selection logic
  // const selectedRequirementId = output?.requirements.some(
  //   (item) => item.id === selectedRequirementIdInput
  // )
  //   ? selectedRequirementIdInput
  //   : (output?.requirements[0]?.id ?? null)

  // DISABLED: requirements lookup map (used by right-column requirement filter)
  // const requirementsById = useMemo(
  //   () =>
  //     Object.fromEntries(
  //       (output?.requirements ?? []).map((item) => [item.id, item.title] as const)
  //     ),
  //   [output]
  // )

  const hasStaleOutput = Boolean(errorMessage && bundle?.output)

  // DISABLED: Requirements and Sections tabs
  // const tabs: { id: MainTab; label: string; count?: number }[] = output
  //   ? [
  //       { id: 'markdown', label: 'PRD' },
  //       { id: 'requirements', label: 'Requirements', count: output.requirements.length },
  //       { id: 'sections', label: 'Sections', count: output.sections.length },
  //     ]
  //   : []
  const tabs: { id: MainTab; label: string }[] = output ? [{ id: 'markdown', label: 'PRD' }] : []

  return (
    <section className="mx-auto w-full max-w-7xl space-y-4 px-6 py-5">
      {/* Page header */}
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-bold tracking-tight text-slate-900">PRD</h1>
        {baselineId ? (
          <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-400">
            {baselineId.slice(0, 8)}&hellip;
          </span>
        ) : null}
        {context.scope_frozen ? (
          <span className="flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700">
            <svg
              aria-hidden="true"
              className="h-3 w-3"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 6.5L4.5 9 10 3" />
            </svg>
            Scope frozen
          </span>
        ) : null}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            disabled={loading}
            className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <span
                aria-hidden="true"
                className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
              />
            ) : (
              <svg
                aria-hidden="true"
                className="h-3 w-3"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M13.5 2.5A6.5 6.5 0 1 1 2.5 8" />
                <path d="M2.5 2.5v3.5H6" />
              </svg>
            )}
            {output ? 'Regenerate' : 'Generate'}
          </button>
        ) : null}
      </header>

      {/* Status banner */}
      <StatusBanner
        loading={loading}
        isRegenerate={isRegenerate}
        errorMessage={errorMessage}
        hasStaleOutput={hasStaleOutput}
        onRetry={onRetry}
      />

      {/* Main content */}
      {output ? (
        <div className="space-y-4">
          {/* Tab bar — only PRD tab active; others disabled */}
          <div className="flex w-full max-w-fit items-center gap-0.5 overflow-x-auto rounded-lg border border-slate-200 bg-slate-100 p-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`cursor-pointer rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
                  activeTab === tab.id
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'markdown' ? <MarkdownPanel markdown={output.markdown} /> : null}

          {/* DISABLED: Requirements tab content */}
          {/* {activeTab === 'requirements' ? (
            <ul className="space-y-2">
              {output.requirements.map((item) => {
                const active = selectedRequirementId === item.id
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedRequirementIdInput(item.id)}
                      className={`w-full cursor-pointer rounded-xl border px-4 py-3.5 text-left transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400 ${
                        active
                          ? 'border-indigo-300 bg-indigo-50 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                            active
                              ? 'bg-indigo-100 text-indigo-700'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          {item.id}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm leading-5 font-semibold text-slate-900">
                            {item.title}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-slate-500">
                            {item.description}
                          </p>
                          {item.rationale ? (
                            <p className="mt-1.5 border-l-2 border-slate-200 pl-2 text-xs text-slate-400 italic">
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
          ) : null} */}

          {/* DISABLED: Sections tab content */}
          {/* {activeTab === 'sections' ? (
            <ul className="space-y-2">
              {output.sections.map((section, idx) => (
                <li
                  key={section.id}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-4"
                >
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <div>
                      <p className="text-xs font-semibold tracking-widest text-slate-500 uppercase">
                        {section.title}
                      </p>
                      <p className="mt-1.5 text-sm leading-6 text-slate-700">{section.content}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : null} */}

          {/* DISABLED: Right column — requirement filter + backlog panel + feedback */}
          {/* <div className="space-y-4">
            {selectedRequirementId ? (
              <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2">
                <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-700">
                  {selectedRequirementId}
                </span>
                <span className="truncate text-xs text-slate-600">
                  {requirementsById[selectedRequirementId] ?? ''}
                </span>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
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
          </div> */}
        </div>
      ) : (
        /* Empty state — loading spinner or placeholder */
        <div className="space-y-4">
          {/* DISABLED: progressive stream partials (requirements/backlog previews) */}
          {/* {loading && streamPartials?.requirements ? ( ... ) : null} */}
          {/* {loading && streamPartials?.backlog ? ( ... ) : null} */}
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-5 py-16 text-center">
            {loading ? (
              <>
                <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
                <p className="text-sm text-slate-500">Generating PRD&hellip;</p>
              </>
            ) : (
              <p className="text-sm text-slate-500">
                {errorMessage ? 'Generation failed.' : 'No PRD generated yet.'}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
