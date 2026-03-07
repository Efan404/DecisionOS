'use client'

import { useState, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslations } from 'next-intl'

import type {
  DecisionContext,
  PrdBundle,
  PrdFeedbackDimensions,
  PrdFeedbackLatest,
  PrdOutput,
} from '../../lib/schemas'
import { type ProgressStep, GenerationProgress } from '../common/GenerationProgress'
import { HoverCard } from '../common/HoverCard'
import { PrdBacklogPanel } from './PrdBacklogPanel'
import { PrdFeedbackBubble } from './PrdFeedbackBubble'

type PrdViewProps = {
  prd?: PrdOutput
  bundle?: PrdBundle
  baselineId?: string | null
  feedbackLatest?: PrdFeedbackLatest
  context: DecisionContext
  loading?: boolean
  progressSteps?: ProgressStep[]
  progressPct?: number
  errorMessage?: string | null
  onRetry?: () => void
  onSubmitFeedback?: (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
  }) => Promise<void>
  feedbackSubmitting?: boolean
  onExportJson?: () => Promise<void> | void
  onExportCsv?: () => Promise<void> | void
  exporting?: boolean
  onGeneratePpt?: () => Promise<void>
  pptSubmitting?: boolean
}

// Status banner — one state at a time: loading > error > idle
function StatusBanner({
  errorMessage,
  hasStaleOutput,
  onRetry,
}: {
  errorMessage: string | null
  hasStaleOutput: boolean
  onRetry?: () => void
}) {
  const t = useTranslations('prd')
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
          <p className="mt-1.5 text-xs text-amber-700">{t('staleSnapshot')}</p>
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

// Cursor logo icon
function CursorIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="currentColor"
      fillRule="evenodd"
      viewBox="0 0 24 24"
    >
      <path d="M22.106 5.68L12.5.135a.998.998 0 00-.998 0L1.893 5.68a.84.84 0 00-.419.726v11.186c0 .3.16.577.42.727l9.607 5.547a.999.999 0 00.998 0l9.608-5.547a.84.84 0 00.42-.727V6.407a.84.84 0 00-.42-.726zm-.603 1.176L12.228 22.92c-.063.108-.228.064-.228-.061V12.34a.59.59 0 00-.295-.51l-9.11-5.26c-.107-.062-.063-.228.062-.228h18.55c.264 0 .428.286.296.514z" />
    </svg>
  )
}

// Open-in-Cursor button — sends PRD content directly to Cursor Composer via deeplink
function OpenInCursorButton({ markdown }: { markdown: string }) {
  const t = useTranslations('prd')
  const [state, setState] = useState<'idle' | 'opening'>('idle')

  const handleOpen = useCallback(() => {
    // Build the prompt: instruction + full PRD content.
    // Cursor deeplink limit is ~8000 chars for the URL. If the PRD exceeds that,
    // we truncate and add a note. Most PRDs fit within this limit.
    const instruction =
      'Below is a PRD exported from DecisionOS. ' +
      'Please create a file called `docs/prd.md` with this content, ' +
      'then review it and suggest implementation tasks.\n\n---\n\n'

    const maxPromptLength = 7500
    let prdContent = markdown
    if (instruction.length + prdContent.length > maxPromptLength) {
      const available = maxPromptLength - instruction.length - 100
      prdContent =
        prdContent.slice(0, available) +
        '\n\n[... PRD truncated due to URL length limit. Full content has been copied to clipboard.]'
      // Copy full content to clipboard as fallback for truncated PRDs
      navigator.clipboard.writeText(markdown).catch(() => {})
    }

    const prompt = encodeURIComponent(instruction + prdContent)
    const deeplink = `cursor://anysphere.cursor-deeplink/prompt?text=${prompt}`

    setState('opening')
    setTimeout(() => setState('idle'), 3000)

    window.open(deeplink, '_self')
  }, [markdown])

  return (
    <button
      type="button"
      onClick={handleOpen}
      className="flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors duration-150 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
    >
      {state === 'opening' ? (
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
          {t('openingCursor')}
        </>
      ) : (
        <>
          <CursorIcon className="h-3.5 w-3.5" />
          {t('openInCursor')}
        </>
      )}
    </button>
  )
}

// PRD document panel — rendered markdown + raw toggle + copy
function MarkdownPanel({ markdown }: { markdown: string }) {
  const t = useTranslations('prd')
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
            {t('preview')}
          </button>
          <button
            type="button"
            onClick={() => setShowRaw(true)}
            className={`cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
              showRaw ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t('raw')}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <CopyButton text={markdown} label={t('copyMarkdown')} />
          <OpenInCursorButton markdown={markdown} />
        </div>
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

type MainTab = 'markdown' | 'requirements'

export function PrdView({
  prd,
  bundle,
  baselineId = null,
  feedbackLatest,
  context,
  loading = false,
  progressSteps,
  progressPct,
  errorMessage = null,
  onRetry,
  onSubmitFeedback,
  feedbackSubmitting = false,
  onExportJson,
  onExportCsv,
  exporting = false,
  onGeneratePpt,
  pptSubmitting = false,
}: PrdViewProps) {
  const t = useTranslations('prd')
  const output = prd ?? bundle?.output
  const [selectedRequirementIdInput, setSelectedRequirementIdInput] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<MainTab>('markdown')
  const [feedbackDismissed, setFeedbackDismissed] = useState(false)

  const showFeedbackBubble =
    !loading &&
    !feedbackDismissed &&
    !feedbackLatest &&
    Boolean(output) &&
    Boolean(onSubmitFeedback)

  const selectedRequirementId = output?.requirements.some(
    (item) => item.id === selectedRequirementIdInput
  )
    ? selectedRequirementIdInput
    : (output?.requirements[0]?.id ?? null)

  const requirementsById = useMemo(
    () =>
      Object.fromEntries(
        (output?.requirements ?? []).map((item) => [item.id, item.title] as const)
      ),
    [output]
  )

  const hasStaleOutput = Boolean(errorMessage && bundle?.output)

  const tabs: { id: MainTab; label: string; count?: number }[] = output
    ? [
        { id: 'markdown', label: t('tabMarkdown') },
        { id: 'requirements', label: t('tabRequirements'), count: output.requirements.length },
      ]
    : []

  return (
    <section id="onboarding-prd-content" className="mx-auto w-full max-w-7xl space-y-4 px-6 py-5">
      {/* Page header */}
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-bold tracking-tight text-slate-900">{t('title')}</h1>
        {baselineId ? (
          <HoverCard
            align="left"
            trigger={
              <span className="cursor-default rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-400">
                {baselineId.slice(0, 8)}&hellip;
              </span>
            }
          >
            <p className="mb-1 font-mono text-[11px] break-all text-slate-600">{baselineId}</p>
            {bundle ? (
              <div className="mt-1.5 space-y-1 border-t border-slate-100 pt-1.5">
                <p className="text-[11px] text-slate-500">
                  <span className="font-medium text-slate-600">Generated:</span>{' '}
                  {bundle.generated_at}
                </p>
                <p className="text-[11px] break-all text-slate-500">
                  <span className="font-medium text-slate-600">Fingerprint:</span>{' '}
                  {bundle.context_fingerprint}
                </p>
              </div>
            ) : null}
          </HoverCard>
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
            {t('scopeFrozen')}
          </span>
        ) : null}
        {onRetry ? (
          <div className="ml-auto flex items-center gap-2">
            {output && onGeneratePpt ? (
              <button
                type="button"
                onClick={() => void onGeneratePpt()}
                disabled={loading || pptSubmitting}
                className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 transition-colors duration-150 hover:bg-indigo-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pptSubmitting ? (
                  <span
                    aria-hidden="true"
                    className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-700"
                  />
                ) : null}
                {pptSubmitting ? t('generatingPpt') : t('generatePpt')}
              </button>
            ) : null}
            <button
              type="button"
              onClick={onRetry}
              disabled={loading}
              className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
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
              {output ? t('regenerate') : t('generate')}
            </button>
          </div>
        ) : null}
      </header>

      {/* Status banner */}
      <StatusBanner errorMessage={errorMessage} hasStaleOutput={hasStaleOutput} onRetry={onRetry} />

      {/* Generation progress — shown whenever loading, regardless of existing output */}
      {loading && progressSteps ? (
        <GenerationProgress steps={progressSteps} isActive={loading} pct={progressPct} />
      ) : null}

      {/* Main content */}
      {output && !loading ? (
        <div className="space-y-4">
          {/* Tab bar */}
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
                {tab.count !== undefined ? (
                  <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                    {tab.count}
                  </span>
                ) : null}
              </button>
            ))}
          </div>

          {activeTab === 'markdown' ? <MarkdownPanel markdown={output.markdown} /> : null}

          {activeTab === 'requirements' ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Left: Requirements list */}
              <ul className="space-y-2 overflow-auto lg:max-h-[65vh]">
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
                          <HoverCard
                            align="left"
                            trigger={
                              <span
                                className={`mt-0.5 shrink-0 cursor-default rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                                  active
                                    ? 'bg-indigo-100 text-indigo-700'
                                    : 'bg-slate-100 text-slate-500'
                                }`}
                              >
                                {item.id}
                              </span>
                            }
                          >
                            {item.acceptance_criteria.length > 0 ? (
                              <div className="mb-1.5">
                                <p className="mb-1 text-[11px] font-medium text-slate-600">
                                  {t('acceptanceCriteria')}
                                </p>
                                <ul className="list-disc space-y-0.5 pl-3.5 text-[11px] text-slate-500">
                                  {item.acceptance_criteria.map((ac, i) => (
                                    <li key={i}>{ac}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                            {item.source_refs.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {item.source_refs.map((ref) => (
                                  <span
                                    key={ref}
                                    className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500"
                                  >
                                    {ref}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </HoverCard>
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

              {/* Right: Backlog panel filtered by selected requirement */}
              <div className="space-y-3">
                {selectedRequirementId ? (
                  <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2">
                    <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-700">
                      {selectedRequirementId}
                    </span>
                    <HoverCard
                      align="left"
                      trigger={
                        <span className="cursor-default truncate text-xs text-slate-600">
                          {requirementsById[selectedRequirementId] ?? ''}
                        </span>
                      }
                    >
                      {(() => {
                        const req = output.requirements.find((r) => r.id === selectedRequirementId)
                        if (!req) return null
                        return (
                          <div className="space-y-1.5">
                            <p className="text-xs font-semibold text-slate-800">{req.title}</p>
                            <p className="text-[11px] leading-relaxed text-slate-500">
                              {req.description}
                            </p>
                            {req.acceptance_criteria.length > 0 ? (
                              <div>
                                <p className="mb-0.5 text-[11px] font-medium text-slate-600">
                                  {t('acceptanceCriteria')}
                                </p>
                                <ul className="list-disc space-y-0.5 pl-3.5 text-[11px] text-slate-500">
                                  {req.acceptance_criteria.map((ac, i) => (
                                    <li key={i}>{ac}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        )
                      })()}
                    </HoverCard>
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
                    {t('selectRequirement')}
                  </p>
                )}
                <PrdBacklogPanel
                  items={output.backlog.items}
                  selectedRequirementId={selectedRequirementId}
                  onSelectRequirement={setSelectedRequirementIdInput}
                  requirementsById={requirementsById}
                  onExportJson={onExportJson}
                  onExportCsv={onExportCsv}
                  exporting={exporting}
                />
              </div>
            </div>
          ) : null}
        </div>
      ) : !loading ? (
        /* Empty state — only shown when not loading and no output */
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-5 py-16 text-center">
          <p className="text-sm text-slate-500">
            {errorMessage ? t('generationFailed') : t('noOutput')}
          </p>
        </div>
      ) : null}

      {showFeedbackBubble && onSubmitFeedback ? (
        <PrdFeedbackBubble
          onSubmit={onSubmitFeedback}
          submitting={feedbackSubmitting}
          onDismiss={() => setFeedbackDismissed(true)}
        />
      ) : null}
    </section>
  )
}
