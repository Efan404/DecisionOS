'use client'

import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'

export type DAGNodeData = {
  content: string
  status: 'active' | 'confirmed' | 'generating'
  isSelected: boolean
  isOnSelectedPath: boolean
}

type DAGNodeType = Node<DAGNodeData, 'dagNode'>

export function DAGNode({ data }: NodeProps<DAGNodeType>) {
  return (
    <div
      className={clsx(
        'relative max-w-[200px] cursor-pointer rounded-xl border px-4 py-3 text-sm transition-all duration-200',
        'bg-[#0F172A] text-[#F8FAFC]',
        data.isSelected
          ? 'border-[#b9eb10] shadow-[0_0_16px_rgba(185,235,16,0.4)]'
          : data.isOnSelectedPath
            ? 'border-[#b9eb10]/50'
            : 'border-[#334155] hover:border-[#64748B] hover:shadow-md',
        data.status === 'confirmed' && 'border-[#b9eb10] bg-[#b9eb10]/10',
        data.status === 'generating' && 'animate-pulse border-dashed border-[#334155]'
      )}
    >
      <p className="line-clamp-3 leading-snug">{data.content}</p>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-[#334155]" />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !border-0 !bg-[#334155]"
      />
    </div>
  )
}
