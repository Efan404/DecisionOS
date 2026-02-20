import { create } from 'zustand'

import type { IdeaNode, IdeaPath } from './dag-api'

interface DAGState {
  nodes: IdeaNode[]
  selectedNodeId: string | null
  confirmedPath: IdeaPath | null
  expandingNodeId: string | null
  setNodes: (nodes: IdeaNode[]) => void
  addNodes: (nodes: IdeaNode[]) => void
  selectNode: (id: string | null) => void
  setConfirmedPath: (path: IdeaPath) => void
  setExpandingNode: (id: string | null) => void
  reset: () => void
}

export const useDAGStore = create<DAGState>((set) => ({
  nodes: [],
  selectedNodeId: null,
  confirmedPath: null,
  expandingNodeId: null,
  setNodes: (nodes) => set({ nodes }),
  addNodes: (nodes) => set((s) => ({ nodes: [...s.nodes, ...nodes] })),
  selectNode: (id) => set({ selectedNodeId: id }),
  setConfirmedPath: (path) => set({ confirmedPath: path }),
  setExpandingNode: (id) => set({ expandingNodeId: id }),
  reset: () => set({ nodes: [], selectedNodeId: null, confirmedPath: null, expandingNodeId: null }),
}))
