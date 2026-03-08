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
  const loadIdeaDetail = useIdeasStore((state) => state.loadIdeaDetail)
  const setActiveIdeaId = useIdeasStore((state) => state.setActiveIdeaId)
  const replaceContext = useDecisionStore((state) => state.replaceContext)

  useEffect(() => {
    let mounted = true
    setReady(false)

    const run = async () => {
      setActiveIdeaId(ideaId)
      const detail = await loadIdeaDetail(ideaId)
      if (!mounted || !detail) {
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
