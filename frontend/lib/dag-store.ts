import { create } from 'zustand'

import type { IdeaNode, IdeaPath } from './dag-api'

interface DAGState {
  nodes: IdeaNode[]
  selectedNodeId: string | null
  confirmedPath: IdeaPath | null
  expandingNodeId: string | null
  setNodes: (nodes: IdeaNode[]) => void
  addNodes: (nodes: IdeaNode[]) => void
  removeNode: (nodeId: string) => void
  selectNode: (id: string | null) => void
  setConfirmedPath: (path: IdeaPath) => void
  setExpandingNode: (id: string | null) => void
  reset: () => void
}

function collectDescendants(nodes: IdeaNode[], nodeId: string): Set<string> {
  const ids = new Set<string>([nodeId])
  const queue = [nodeId]
  while (queue.length) {
    const parentId = queue.shift()!
    for (const n of nodes) {
      if (n.parent_id === parentId && !ids.has(n.id)) {
        ids.add(n.id)
        queue.push(n.id)
      }
    }
  }
  return ids
}

export const useDAGStore = create<DAGState>((set) => ({
  nodes: [],
  selectedNodeId: null,
  confirmedPath: null,
  expandingNodeId: null,
  setNodes: (nodes) => set({ nodes }),
  addNodes: (nodes) => set((s) => ({ nodes: [...s.nodes, ...nodes] })),
  removeNode: (nodeId) =>
    set((s) => {
      const toRemove = collectDescendants(s.nodes, nodeId)
      return {
        nodes: s.nodes.filter((n) => !toRemove.has(n.id)),
        selectedNodeId: toRemove.has(s.selectedNodeId ?? '') ? null : s.selectedNodeId,
      }
    }),
  selectNode: (id) => set({ selectedNodeId: id }),
  setConfirmedPath: (path) => set({ confirmedPath: path }),
  setExpandingNode: (id) => set({ expandingNodeId: id }),
  reset: () => set({ nodes: [], selectedNodeId: null, confirmedPath: null, expandingNodeId: null }),
}))
