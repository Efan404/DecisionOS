'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { useDAGStore } from '../../../lib/dag-store'
import { useIdeasStore } from '../../../lib/ideas-store'
import { useDecisionStore } from '../../../lib/store'
import {
  listNodes,
  createRootNode,
  expandUserNode,
  deleteNode,
  confirmPath,
  buildConfirmedPathContext,
  getLatestPath,
  type IdeaNode,
} from '../../../lib/dag-api'
import { toast } from 'sonner'
import { streamPost } from '../../../lib/sse'
import { DAGNode, type DAGNodeData } from './DAGNode'
import { DAGEdge, type DAGEdgeData } from './DAGEdge'
import { NodeDetailPanel } from './NodeDetailPanel'

type DAGNodeType = Node<DAGNodeData, 'dagNode'>
type DAGEdgeType = Edge<DAGEdgeData, 'dagEdge'>

const nodeTypes = { dagNode: DAGNode }
const edgeTypes = { dagEdge: DAGEdge }

function buildPathChain(nodes: IdeaNode[], targetId: string): string[] {
  const map = new Map(nodes.map((n) => [n.id, n]))
  const chain: string[] = []
  let cur: IdeaNode | undefined = map.get(targetId)
  while (cur) {
    chain.unshift(cur.id)
    cur = cur.parent_id ? map.get(cur.parent_id) : undefined
  }
  return chain
}

interface Props {
  ideaId: string
}

export function IdeaDAGCanvas({ ideaId }: Props) {
  const router = useRouter()
  const {
    nodes: dagNodes,
    selectedNodeId,
    confirmedPath,
    expandingNodeId,
    setNodes,
    addNodes,
    removeNode,
    selectNode,
    setConfirmedPath,
    setExpandingNode,
    reset,
  } = useDAGStore()

  // Tracks whether the user confirmed a path in *this* session.
  // Loading a historical path from the backend should not lock the canvas.
  const [sessionConfirmed, setSessionConfirmed] = useState(false)

  // Mobile detection (SSR-safe, responds to resize/rotation)
  const [isMobile, setIsMobile] = useState(false)
  const [landscapeDismissed, setLandscapeDismissed] = useState(false)
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const [rfNodes, setRFNodes, onNodesChange] = useNodesState<DAGNodeType>([])
  const [rfEdges, setRFEdges, onEdgesChange] = useEdgesState<DAGEdgeType>([])

  const selectedPathChain = useMemo(() => {
    if (!selectedNodeId) return []
    return buildPathChain(dagNodes, selectedNodeId)
  }, [dagNodes, selectedNodeId])

  // Convert DAG nodes to React Flow nodes/edges
  useEffect(() => {
    const LEVEL_HEIGHT = 140
    const NODE_WIDTH = 220
    const byDepth: Record<number, IdeaNode[]> = {}
    dagNodes.forEach((n) => {
      ;(byDepth[n.depth] ??= []).push(n)
    })

    const newRFNodes: DAGNodeType[] = dagNodes.map((n) => {
      const siblings = byDepth[n.depth] ?? []
      const idx = siblings.indexOf(n)
      const x = (idx - (siblings.length - 1) / 2) * (NODE_WIDTH + 32)
      const y = n.depth * LEVEL_HEIGHT
      const data: DAGNodeData = {
        content: n.content,
        status: n.id === expandingNodeId ? 'generating' : (n.status as DAGNodeData['status']),
        isSelected: n.id === selectedNodeId,
        isOnSelectedPath: selectedPathChain.includes(n.id),
        edge_label: n.edge_label,
      }
      return { id: n.id, type: 'dagNode' as const, position: { x, y }, data }
    })

    const newRFEdges: DAGEdgeType[] = dagNodes
      .filter((n) => n.parent_id)
      .map((n) => ({
        id: `e-${n.parent_id}-${n.id}`,
        source: n.parent_id!,
        target: n.id,
        type: 'dagEdge' as const,
        data: {
          label: n.edge_label ?? undefined,
          isHighlighted:
            selectedPathChain.includes(n.parent_id!) && selectedPathChain.includes(n.id),
        },
      }))

    setRFNodes(newRFNodes)
    setRFEdges(newRFEdges)
  }, [dagNodes, selectedNodeId, selectedPathChain, expandingNodeId, setRFNodes, setRFEdges])

  // Init: reset store on ideaId change, then load or create root node
  useEffect(() => {
    reset()
    setSessionConfirmed(false)
    let cancelled = false
    ;(async () => {
      const [existing, latestPath] = await Promise.all([
        listNodes(ideaId),
        getLatestPath(ideaId).catch(() => null),
      ])
      if (cancelled) return
      if (existing.length > 0) {
        setNodes(existing)
      } else {
        const contextSeed = useDecisionStore.getState().context.idea_seed?.trim()
        const fallbackIdea = useIdeasStore
          .getState()
          .ideas.find((candidate) => candidate.id === ideaId)
        const fallbackSeed = fallbackIdea?.idea_seed?.trim() || fallbackIdea?.title?.trim()
        const rootSeed = contextSeed || fallbackSeed || 'Untitled idea'

        const root = await createRootNode(ideaId, rootSeed)
        if (cancelled) return
        setNodes([root])
      }
      if (latestPath) {
        setConfirmedPath(latestPath)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [ideaId, setNodes, setConfirmedPath, reset])

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: DAGNodeType) => {
      selectNode(node.id)
    },
    [selectNode]
  )

  const handleExpandAI = async (patternId: string) => {
    if (!selectedNodeId) return
    setExpandingNode(selectedNodeId)
    try {
      await streamPost<Record<string, never>, unknown, unknown, { nodes: IdeaNode[] }>(
        `/ideas/${ideaId}/nodes/${selectedNodeId}/expand/stream?pattern_id=${encodeURIComponent(patternId)}`,
        {},
        {
          onDone: (data) => {
            addNodes(data.nodes)
          },
        }
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to expand node. Please try again.'
      toast.error(message)
    } finally {
      setExpandingNode(null)
    }
  }

  const handleExpandUser = async (description: string) => {
    if (!selectedNodeId) return
    setExpandingNode(selectedNodeId)
    try {
      const newNodes = await expandUserNode(ideaId, selectedNodeId, description)
      addNodes(newNodes)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add node. Please try again.'
      toast.error(message)
    } finally {
      setExpandingNode(null)
    }
  }

  const handleConfirmPath = async () => {
    if (!selectedNodeId) return
    const path = await confirmPath(ideaId, selectedPathChain)
    setConfirmedPath(path)
    setSessionConfirmed(true)

    // Sync DAG confirmation into the decision context so stage guards
    // (canRunFeasibility) see confirmed_dag_path_id immediately.
    const pathCtx = buildConfirmedPathContext(path)
    const store = useDecisionStore.getState()
    useDecisionStore.setState({
      context: {
        ...store.context,
        confirmed_dag_path_id: path.id,
        confirmed_dag_node_id: pathCtx?.confirmed_node_id,
        confirmed_dag_node_content: pathCtx?.confirmed_node_content,
        confirmed_dag_path_summary: pathCtx?.confirmed_path_summary ?? undefined,
      },
    })

    router.push(`/ideas/${ideaId}/feasibility`)
  }

  const handleDeleteNode = async (nodeId: string) => {
    try {
      await deleteNode(ideaId, nodeId)
      removeNode(nodeId)
      toast.success('Node deleted')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete node'
      toast.error(message)
    }
  }

  const selectedNode = dagNodes.find((n) => n.id === selectedNodeId) ?? null

  return (
    <div className="flex h-full w-full bg-[#0F172A]">
      <div className="relative flex-1">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          panOnDrag
          zoomOnScroll
          zoomOnPinch
          className="bg-[#0F172A]"
        >
          <Background color="#1E293B" gap={24} />
          <Controls className="!border-[#334155] !bg-[#1E293B]" />
        </ReactFlow>

        {/* Mobile landscape hint banner */}
        {isMobile && !landscapeDismissed && (
          <div className="absolute top-2 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-[#1e1e1e]/80 px-4 py-2 text-xs text-white backdrop-blur-sm">
            <span>Rotate for best experience</span>
            <button
              type="button"
              onClick={() => setLandscapeDismissed(true)}
              className="text-white/60 hover:text-white"
              aria-label="Dismiss hint"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Desktop side panel */}
      <div className="hidden w-72 flex-shrink-0 border-l border-[#1E293B] bg-[#0A0F1A] md:block">
        <NodeDetailPanel
          node={selectedNode}
          pathChain={selectedPathChain}
          onExpandAI={handleExpandAI}
          onExpandUser={handleExpandUser}
          onConfirmPath={handleConfirmPath}
          onDeleteNode={handleDeleteNode}
          isConfirmed={sessionConfirmed}
          loading={expandingNodeId !== null}
        />
      </div>

      {/* Mobile bottom sheet */}
      {selectedNode && (
        <div className="fixed right-0 bottom-0 left-0 z-30 max-h-[70vh] overflow-y-auto rounded-t-2xl bg-[#1E293B] shadow-2xl md:hidden">
          <div className="relative flex items-center justify-center px-4 pt-2 pb-3">
            <div className="h-1 w-10 rounded-full bg-white/20" />
            <button
              type="button"
              onClick={() => selectNode(null)}
              className="absolute top-1 right-4 flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white/60 transition hover:bg-white/20"
              aria-label="Close panel"
            >
              ✕
            </button>
          </div>
          <NodeDetailPanel
            node={selectedNode}
            pathChain={selectedPathChain}
            onExpandAI={handleExpandAI}
            onExpandUser={handleExpandUser}
            onConfirmPath={handleConfirmPath}
            onDeleteNode={handleDeleteNode}
            isConfirmed={sessionConfirmed}
            loading={expandingNodeId !== null}
          />
        </div>
      )}
    </div>
  )
}
