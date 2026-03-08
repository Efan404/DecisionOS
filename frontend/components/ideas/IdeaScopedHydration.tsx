'use client'

import { useEffect, useState } from 'react'

import { useIdeasStore } from '../../lib/ideas-store'
import { useDecisionStore } from '../../lib/store'

type IdeaScopedHydrationProps = Readonly<{
  ideaId: string
  children: React.ReactNode
}>

export function IdeaScopedHydration({ ideaId, children }: IdeaScopedHydrationProps) {
  const [ready, setReady] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const loadIdeaDetail = useIdeasStore((state) => state.loadIdeaDetail)
  const setActiveIdeaId = useIdeasStore((state) => state.setActiveIdeaId)
  const replaceContext = useDecisionStore((state) => state.replaceContext)

  useEffect(() => {
    let mounted = true
    setReady(false)
    setErrorMessage(null)

    const run = async () => {
      setActiveIdeaId(ideaId)
      const detail = await loadIdeaDetail(ideaId)
      if (!mounted) {
        return
      }
      if (!detail) {
        setErrorMessage('Idea not found or unavailable.')
        return
      }

      replaceContext(detail.context)
      setReady(true)
    }

    void run()

    return () => {
      mounted = false
    }
  }, [ideaId, loadIdeaDetail, replaceContext, setActiveIdeaId])

  if (errorMessage) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <section className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900 shadow-sm">
          <p>{errorMessage}</p>
          <a
            href="/ideas"
            className="inline-flex rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-medium text-amber-900 transition hover:bg-amber-100"
          >
            Back to ideas
          </a>
        </section>
      </main>
    )
  }

  if (!ready) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <section className="rounded-xl border border-slate-200 bg-white/95 p-6 text-sm text-slate-600 shadow-sm">
          Syncing idea context...
        </section>
      </main>
    )
  }

  return <>{children}</>
}
