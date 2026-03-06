'use client'

import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react'

export type DAGEdgeData = {
  label?: string
  isHighlighted?: boolean
}

type DAGEdgeType = Edge<DAGEdgeData, 'dagEdge'>

export function DAGEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
}: EdgeProps<DAGEdgeType>) {
  const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const isHighlighted = data?.isHighlighted

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: isHighlighted ? '#b9eb10' : '#334155',
          strokeWidth: isHighlighted ? 2 : 1,
        }}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)`,
            }}
            className="pointer-events-none rounded bg-[#0F172A] px-1 text-[10px] text-[#64748B]"
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
