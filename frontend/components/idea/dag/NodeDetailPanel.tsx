'use client'

import { useEffect, useState } from 'react'
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
  onDeleteNode?: (nodeId: string) => Promise<void>
  isConfirmed: boolean
  loading: boolean
}

export function NodeDetailPanel({
  node,
  pathChain,
  onExpandAI,
  onExpandUser,
  onConfirmPath,
  onDeleteNode,
  isConfirmed,
  loading,
}: Props) {
  const [mode, setMode] = useState<PanelMode>('idle')
  const [userInput, setUserInput] = useState('')
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    setShowDeleteDialog(false)
    setMode('idle')
  }, [node?.id])

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[#64748B]">
        Click a node to view details
      </div>
    )
  }

  return (
    <>
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

        <div className="mt-auto flex flex-col gap-2">
          {node.parent_id !== null && !isConfirmed && onDeleteNode && (
            <button
              onClick={() => setShowDeleteDialog(true)}
              disabled={loading || deleting}
              className="w-full cursor-pointer rounded-lg border border-red-500/30 px-3 py-2 text-sm text-red-400 transition-all hover:border-red-500/60 hover:bg-red-500/10 disabled:opacity-50"
            >
              Delete Node
            </button>
          )}
          <button
            onClick={onConfirmPath}
            disabled={loading || isConfirmed}
            className="w-full cursor-pointer rounded-lg bg-[#b9eb10] px-3 py-2.5 text-sm font-semibold text-[#1e1e1e] transition-all hover:bg-[#d4f542] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isConfirmed ? 'Path Confirmed ✓' : 'Confirm This Path'}
          </button>
          {!isConfirmed && (
            <p className="mt-1 text-center text-xs text-[#475569]">
              Confirms and opens Feasibility
            </p>
          )}
        </div>
      </motion.div>

      {/* Delete confirmation dialog */}
      <AnimatePresence>
        {showDeleteDialog && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => !deleting && setShowDeleteDialog(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="mx-4 w-full max-w-sm rounded-xl border border-[#334155] bg-[#1E293B] p-6 shadow-2xl"
            >
              <h3 className="text-base font-semibold text-[#F8FAFC]">Delete this node?</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#94A3B8]">
                This will permanently delete this node and all its descendants. This action cannot be
                undone.
              </p>
              <p className="mt-3 rounded-lg bg-[#0F172A] px-3 py-2 text-xs leading-relaxed text-[#64748B]">
                &ldquo;{node.content.length > 80 ? node.content.slice(0, 80) + '…' : node.content}&rdquo;
              </p>
              <div className="mt-5 flex gap-3">
                <button
                  onClick={() => setShowDeleteDialog(false)}
                  disabled={deleting}
                  className="flex-1 cursor-pointer rounded-lg border border-[#334155] px-4 py-2.5 text-sm text-[#94A3B8] transition-all hover:border-[#64748B] hover:text-[#F8FAFC]"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    setDeleting(true)
                    try {
                      await onDeleteNode!(node.id)
                      setShowDeleteDialog(false)
                    } finally {
                      setDeleting(false)
                    }
                  }}
                  disabled={deleting}
                  className="flex-1 cursor-pointer rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition-all hover:bg-red-700 disabled:opacity-50"
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
