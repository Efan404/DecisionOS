import { ApiError, jsonDelete, jsonGet, jsonPost } from './api'
import type { ConfirmedPathContext, ConfirmedPathNode } from './schemas'

export interface IdeaNode {
  id: string
  idea_id: string
  parent_id: string | null
  content: string
  expansion_pattern: string | null
  edge_label: string | null
  depth: number
  status: string
  created_at: string
}

export interface IdeaPath {
  id: string
  idea_id: string
  node_chain: string[]
  path_md: string
  path_json: string
  created_at: string
}

export interface IdeaPathJson {
  idea_id?: string
  confirmed_at?: string
  node_chain: ConfirmedPathNode[]
  summary?: string
}

export const EXPANSION_PATTERNS = [
  {
    id: 'narrow_users',
    label: 'Narrow the Audience',
    description: 'Redefine the problem for a more precise user segment',
  },
  {
    id: 'expand_features',
    label: 'Expand Feature Scope',
    description: 'Extend adjacent capabilities beyond the core feature',
  },
  {
    id: 'shift_scenario',
    label: 'Shift the Scenario',
    description: 'Apply this idea to a different usage context',
  },
  {
    id: 'monetize',
    label: 'Monetization Variants',
    description: 'Explore alternative business model paths',
  },
  {
    id: 'simplify',
    label: 'Simplify to Core',
    description: 'Strip everything away — keep only the minimal viable kernel',
  },
] as const

export async function listNodes(ideaId: string): Promise<IdeaNode[]> {
  return await jsonGet<IdeaNode[]>(`/ideas/${ideaId}/nodes`)
}

export async function createRootNode(ideaId: string, content: string): Promise<IdeaNode> {
  return await jsonPost<{ content: string }, IdeaNode>(`/ideas/${ideaId}/nodes`, {
    content,
  })
}

export async function expandUserNode(
  ideaId: string,
  nodeId: string,
  description: string
): Promise<IdeaNode[]> {
  return await jsonPost<{ description: string }, IdeaNode[]>(
    `/ideas/${ideaId}/nodes/${nodeId}/expand/user`,
    { description }
  )
}

export async function deleteNode(ideaId: string, nodeId: string): Promise<void> {
  await jsonDelete(`/ideas/${ideaId}/nodes/${nodeId}`)
}

export async function confirmPath(ideaId: string, nodeChain: string[]): Promise<IdeaPath> {
  return await jsonPost<{ node_chain: string[] }, IdeaPath>(`/ideas/${ideaId}/paths`, {
    node_chain: nodeChain,
  })
}

export async function getLatestPath(ideaId: string): Promise<IdeaPath | null> {
  try {
    return await jsonGet<IdeaPath>(`/ideas/${ideaId}/paths/latest`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null
    }
    throw error
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null
}

const parsePathNode = (value: unknown): ConfirmedPathNode | null => {
  if (!isRecord(value)) return null
  if (typeof value.id !== 'string' || !value.id.trim()) return null
  if (typeof value.content !== 'string' || !value.content.trim()) return null

  const rawDepth = value.depth
  const depth =
    typeof rawDepth === 'number' && Number.isFinite(rawDepth) && rawDepth >= 0
      ? Math.floor(rawDepth)
      : undefined

  return {
    id: value.id,
    content: value.content,
    expansion_pattern:
      typeof value.expansion_pattern === 'string' ? value.expansion_pattern : undefined,
    edge_label: typeof value.edge_label === 'string' ? value.edge_label : undefined,
    depth,
  }
}

export function parseIdeaPathJson(pathJson: string): IdeaPathJson | null {
  try {
    const parsed: unknown = JSON.parse(pathJson)
    if (!isRecord(parsed) || !Array.isArray(parsed.node_chain)) {
      return null
    }

    const nodeChain = parsed.node_chain
      .map((node) => parsePathNode(node))
      .filter((node): node is ConfirmedPathNode => node !== null)

    if (!nodeChain.length) {
      return null
    }

    return {
      idea_id: typeof parsed.idea_id === 'string' ? parsed.idea_id : undefined,
      confirmed_at: typeof parsed.confirmed_at === 'string' ? parsed.confirmed_at : undefined,
      node_chain: nodeChain,
      summary: typeof parsed.summary === 'string' ? parsed.summary : undefined,
    }
  } catch {
    return null
  }
}

export function buildConfirmedPathContext(path: IdeaPath): ConfirmedPathContext | null {
  const parsed = parseIdeaPathJson(path.path_json)
  if (!parsed) {
    return null
  }

  const confirmedNode = parsed.node_chain[parsed.node_chain.length - 1]
  if (!confirmedNode || !confirmedNode.content.trim()) {
    return null
  }

  return {
    confirmed_path_id: path.id,
    confirmed_node_id: confirmedNode.id,
    confirmed_node_content: confirmedNode.content,
    confirmed_path_summary: parsed.summary,
  }
}
