'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export type AgentThought = {
  agent: string
  thought: string
  timestamp: number
}

const AGENT_COLORS: Record<string, string> = {
  Researcher: 'text-blue-400',
  Generator: 'text-[#b9eb10]',
  Critic: 'text-orange-400',
  Reviewer: 'text-orange-400',
  Architect: 'text-purple-400',
  'Memory Writer': 'text-green-400',
  'Pattern Matcher': 'text-pink-400',
}

const getAgentColor = (agent: string) => AGENT_COLORS[agent] ?? 'text-zinc-400'

type Props = {
  thoughts: AgentThought[]
  isActive?: boolean
}

export function AgentThoughtStream({ thoughts, isActive = false }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thoughts.length])

  if (thoughts.length === 0 && !isActive) return null

  return (
    <div className="rounded-xl border border-zinc-700/50 bg-zinc-900/95 p-4 backdrop-blur-sm">
      <div className="mb-2 flex items-center gap-2">
        {isActive && (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#b9eb10] opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#b9eb10]" />
          </span>
        )}
        <span className="text-xs font-medium tracking-wide text-zinc-400 uppercase">
          Agent Activity
        </span>
      </div>
      <div className="max-h-36 space-y-1.5 overflow-y-auto">
        {thoughts.map((t, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className={`shrink-0 font-medium ${getAgentColor(t.agent)}`}>{t.agent}</span>
            <span className="text-zinc-400">{t.thought}</span>
          </div>
        ))}
        {isActive && thoughts.length === 0 && (
          <p className="text-xs text-zinc-500">Initializing agents...</p>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

export function useAgentThoughts() {
  const [thoughts, setThoughts] = useState<AgentThought[]>([])

  const addThought = useCallback((data: { agent: string; thought: string }) => {
    setThoughts((prev) => [...prev, { ...data, timestamp: Date.now() }])
  }, [])

  const reset = useCallback(() => setThoughts([]), [])

  return { thoughts, addThought, reset }
}
