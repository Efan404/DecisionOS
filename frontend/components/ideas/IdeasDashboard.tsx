'use client'

import { FormEvent, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useTranslations } from 'next-intl'

import { CrossIdeaInsights } from '../insights/CrossIdeaInsights'
import { useIdeasStore } from '../../lib/ideas-store'

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 30) return `${diffDay}d ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function IdeasDashboard() {
  const t = useTranslations('ideas')
  const tCommon = useTranslations('common')
  const ideas = useIdeasStore((state) => state.ideas)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const loading = useIdeasStore((state) => state.loading)
  const error = useIdeasStore((state) => state.error)
  const loadIdeas = useIdeasStore((state) => state.loadIdeas)
  const createIdea = useIdeasStore((state) => state.createIdea)
  const setActiveIdeaId = useIdeasStore((state) => state.setActiveIdeaId)
  const deleteIdea = useIdeasStore((state) => state.deleteIdea)

  const [title, setTitle] = useState('')
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    void loadIdeas()
  }, [loadIdeas])

  const handleCreateIdea = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) {
      return
    }

    await createIdea(trimmed)
    setTitle('')
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <section className="rounded-2xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-[#1e1e1e]">{t('title')}</h1>
            <p className="mt-1 text-sm text-[#1e1e1e]/50">{t('subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={() => void loadIdeas()}
            className="rounded-lg border border-[#1e1e1e]/15 bg-white px-3 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
          >
            {t('refresh')}
          </button>
        </div>

        <form onSubmit={handleCreateIdea} className="mt-5 flex flex-col gap-2 sm:flex-row">
          <input
            value={title}
            onChange={(event) => setTitle(event.currentTarget.value)}
            placeholder="e.g. AI Copilot for PRD alignment"
            className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-4 py-2.5 text-sm text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/25"
          />
          <button
            id="onboarding-new-idea-btn"
            type="submit"
            className="shrink-0 rounded-xl bg-[#1e1e1e] px-5 py-2.5 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333]"
          >
            {t('newIdea')}
          </button>
        </form>

        {error ? (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        ) : null}

        {/* Skeleton loader */}
        {loading && ideas.length === 0 ? (
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="animate-pulse rounded-xl border border-[#1e1e1e]/10 bg-white p-4"
              >
                <div className="h-4 w-2/3 rounded-md bg-[#f0f0f0]" />
                <div className="mt-2 h-3 w-1/2 rounded-md bg-[#f0f0f0]" />
                <div className="mt-3 flex gap-2">
                  <div className="h-6 w-16 rounded-lg bg-[#f0f0f0]" />
                  <div className="h-6 w-20 rounded-lg bg-[#f0f0f0]" />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <div id="onboarding-ideas-list" className="mt-5 grid gap-3 md:grid-cols-2">
          {ideas.map((idea) => {
            const isActive = activeIdeaId === idea.id
            return (
              <article
                key={idea.id}
                className={`group relative rounded-xl border p-4 transition ${
                  isActive
                    ? 'border-[#b9eb10] bg-[#1e1e1e]'
                    : 'border-[#1e1e1e]/10 bg-white hover:border-[#1e1e1e]/20'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2
                      className={`text-sm font-semibold ${isActive ? 'text-[#b9eb10]' : 'text-[#1e1e1e]'}`}
                    >
                      {idea.title}
                    </h2>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          isActive ? 'bg-white/15 text-white/70' : 'bg-[#f5f5f5] text-[#1e1e1e]/50'
                        }`}
                      >
                        {idea.stage}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          idea.status === 'active'
                            ? isActive
                              ? 'bg-[#b9eb10]/20 text-[#b9eb10]'
                              : 'bg-[#b9eb10]/15 text-[#4a7300]'
                            : isActive
                              ? 'bg-white/10 text-white/50'
                              : 'bg-[#f5f5f5] text-[#1e1e1e]/40'
                        }`}
                      >
                        {idea.status}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveIdeaId(idea.id)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                      isActive
                        ? 'bg-[#b9eb10] text-[#1e1e1e]'
                        : 'border border-[#1e1e1e]/15 bg-[#f5f5f5] text-[#1e1e1e]/60 hover:bg-[#ebebeb]'
                    }`}
                  >
                    {isActive ? t('activeCheck') : t('setActive')}
                  </button>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <p
                    className={`text-[11px] ${isActive ? 'text-white/30' : 'text-[#1e1e1e]/25'}`}
                    title={idea.updated_at}
                  >
                    {formatRelativeTime(idea.updated_at)}
                  </p>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setConfirmingId(idea.id)
                    }}
                    className="rounded p-1 opacity-0 transition-opacity group-hover:opacity-100"
                    style={{ color: isActive ? '#ffffff66' : '#1e1e1e44' }}
                    aria-label={t('deleteIdea')}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </article>
            )
          })}

          {!loading && ideas.length === 0 ? (
            <div className="col-span-2 flex flex-col items-center justify-center rounded-xl border border-dashed border-[#1e1e1e]/15 p-12 text-center">
              <p className="text-sm font-medium text-[#1e1e1e]/50">No ideas yet</p>
              <p className="mt-1 text-xs text-[#1e1e1e]/30">
                Enter an idea title above and click &ldquo;New Idea&rdquo; to get started.
              </p>
            </div>
          ) : null}
        </div>
      </section>

      {/* Delete idea confirmation dialog */}
      <AnimatePresence>
        {confirmingId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={() => !deleting && setConfirmingId(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="mx-4 w-full max-w-sm rounded-xl border border-[#1e1e1e]/10 bg-white p-6 shadow-2xl"
            >
              <h3 className="text-base font-semibold text-[#1e1e1e]">{t('deleteTitle')}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#1e1e1e]/60">
                {t.rich('deleteBody', {
                  title: ideas.find((i) => i.id === confirmingId)?.title ?? '',
                  b: (chunks) => <span className="font-semibold text-[#1e1e1e]">{chunks}</span>,
                })}
              </p>
              <div className="mt-5 flex gap-3">
                <button
                  onClick={() => setConfirmingId(null)}
                  disabled={deleting}
                  className="flex-1 cursor-pointer rounded-lg border border-[#1e1e1e]/15 px-4 py-2.5 text-sm text-[#1e1e1e]/60 transition hover:border-[#1e1e1e]/30 hover:text-[#1e1e1e]"
                >
                  {tCommon('cancel')}
                </button>
                <button
                  onClick={async () => {
                    setDeleting(true)
                    try {
                      await deleteIdea(confirmingId)
                      setConfirmingId(null)
                    } finally {
                      setDeleting(false)
                    }
                  }}
                  disabled={deleting}
                  className="flex-1 cursor-pointer rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deleting ? t('deleting') : t('delete')}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <section className="mt-6">
        <CrossIdeaInsights />
      </section>
    </main>
  )
}
