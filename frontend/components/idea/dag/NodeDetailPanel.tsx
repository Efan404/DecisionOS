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
        点击节点查看详情
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
          {node.edge_label ?? '根节点'} · 深度 {node.depth}
        </div>
        <p className="text-sm leading-relaxed text-[#F8FAFC]">{node.content}</p>
      </div>

      <div className="text-xs text-[#475569]">链路长度：{pathChain.length} 跳</div>

      <div className="border-t border-[#1E293B]" />

      <AnimatePresence mode="wait">
        {mode === 'idle' && (
          <motion.div key="idle" className="flex flex-col gap-2">
            <button
              onClick={() => setMode('ai-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#22C55E] disabled:opacity-50"
            >
              AI 扩展
            </button>
            <button
              onClick={() => setMode('user-expand')}
              disabled={loading || isConfirmed}
              className="w-full cursor-pointer rounded-lg border border-[#334155] bg-[#1E293B] px-3 py-2 text-sm text-[#F8FAFC] transition-all hover:border-[#64748B] disabled:opacity-50"
            >
              我来写方向
            </button>
          </motion.div>
        )}

        {mode === 'ai-expand' && (
          <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="mb-2 text-xs text-[#64748B]">选择扩展维度</div>
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
              取消
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
              placeholder="描述你想探索的方向..."
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
                className="flex-1 cursor-pointer rounded-lg border border-[#22C55E]/40 bg-[#22C55E]/10 py-2 text-sm text-[#22C55E] transition-all hover:bg-[#22C55E]/20 disabled:opacity-50"
              >
                生成
              </button>
              <button
                onClick={() => setMode('idle')}
                className="cursor-pointer rounded-lg border border-[#334155] px-3 py-2 text-sm text-[#64748B] hover:border-[#64748B]"
              >
                取消
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-auto">
        <button
          onClick={onConfirmPath}
          disabled={loading || isConfirmed}
          className="w-full cursor-pointer rounded-lg bg-[#22C55E] px-3 py-2.5 text-sm font-semibold text-[#0F172A] transition-all hover:bg-[#16A34A] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isConfirmed ? '路径已确认' : '确认此路径'}
        </button>
        {!isConfirmed && (
          <p className="mt-1 text-center text-xs text-[#475569]">确认后进入 Feasibility 分析</p>
        )}
      </div>
    </motion.div>
  )
}
