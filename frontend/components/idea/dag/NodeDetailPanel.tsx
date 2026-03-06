'use client'

import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { ExpansionPatternPicker } from './ExpansionPatternPicker'
import type { IdeaNode } from '../../../lib/dag-api'

type PanelMode = 'idle' | 'ai-expand' | 'user-expand'

interface Props {
  node: IdeaNode | null
  pathChain: string[]
  onExpandAI: (patternId: string) => Promise<void>
  onExpandUser: (description: string) => Promise<void>
  onConfirmPath: () => Promise<void>
  isConfirmed: boolean
  loading: boolean
}

export function NodeDetailPanel({
  node,
  pathChain,
  onExpandAI,
  onExpandUser,
  onConfirmPath,
  isConfirmed,
  loading,
}: Props) {
  const [mode, setMode] = useState<PanelMode>('idle')
  const [userInput, setUserInput] = useState('')

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[#64748B]">
        Click a node to view details
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex h-full flex-col gap-4 p-4"
    >
      <div>
        <div className="mb-1 text-xs text-[#64748B]">
          {node.edge_label ?? 'Root'} · Depth {node.depth}
        </div>
        <p className="text-sm leading-relaxed text-[#F8FAFC]">{node.content}</p>
      </div>

      <div className="text-xs text-[#475569]">Path length: {pathChain.length} hops</div>

      <div className="border-t border-[#1E293B]" />

      <AnimatePresence mode="wait">
        {mode === 'idle' && (
          <motion.div key="idle" className="flex flex-col gap-2">
            <button
              onClick={() => setMode('ai-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#b9eb10] disabled:opacity-50"
            >
              AI Expand
            </button>
            <button
              onClick={() => setMode('user-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#64748B] disabled:opacity-50"
            >
              Write My Own
            </button>
          </motion.div>
        )}

        {mode === 'ai-expand' && (
          <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="mb-2 text-xs text-[#64748B]">Choose expansion lens</div>
            <ExpansionPatternPicker
              onSelect={async (id) => {
                await onExpandAI(id)
                setMode('idle')
              }}
              loading={loading}
            />
            <button
              onClick={() => setMode('idle')}
              className="mt-2 cursor-pointer text-xs text-[#475569] hover:text-[#64748B]"
            >
              Cancel
            </button>
          </motion.div>
        )}

        {mode === 'user-expand' && (
          <motion.div
            key="user"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col gap-2"
          >
            <textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="Describe the direction you want to explore..."
              rows={3}
              className="w-full resize-none rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] placeholder-[#475569] focus:border-[#64748B] focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (userInput.trim()) {
                    await onExpandUser(userInput)
                    setUserInput('')
                    setMode('idle')
                  }
                }}
                disabled={loading || !userInput.trim()}
                className="flex-1 cursor-pointer rounded-lg border border-[#b9eb10]/40 bg-[#b9eb10]/10 py-2 text-sm text-[#1e1e1e] transition-all hover:bg-[#b9eb10]/20 disabled:opacity-50"
              >
                Generate
              </button>
              <button
                onClick={() => setMode('idle')}
                className="cursor-pointer rounded-lg border border-[#334155] px-3 py-2 text-sm text-[#64748B] hover:border-[#64748B]"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-auto">
        <button
          onClick={onConfirmPath}
          disabled={loading || isConfirmed}
          className="w-full cursor-pointer rounded-lg bg-[#b9eb10] px-3 py-2.5 text-sm font-semibold text-[#1e1e1e] transition-all hover:bg-[#d4f542] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isConfirmed ? 'Path Confirmed ✓' : 'Confirm This Path'}
        </button>
        {!isConfirmed && (
          <p className="mt-1 text-center text-xs text-[#475569]">Confirms and opens Feasibility</p>
        )}
      </div>
    </motion.div>
  )
}
