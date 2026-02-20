import { buildApiUrl } from './api'

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

export const EXPANSION_PATTERNS = [
  { id: 'narrow_users', label: '缩小用户群体', description: '针对更精准的细分用户群重新定义问题' },
  { id: 'expand_features', label: '功能边界扩展', description: '在核心功能基础上延伸出相邻能力' },
  { id: 'shift_scenario', label: '场景迁移', description: '将此 idea 迁移至不同使用场景' },
  { id: 'monetize', label: '商业模式变体', description: '探索不同的商业化路径' },
  { id: 'simplify', label: '极简核心', description: '只保留最小可行内核，砍掉所有附加物' },
] as const

export async function listNodes(ideaId: string): Promise<IdeaNode[]> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes`))
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function createRootNode(ideaId: string, content: string): Promise<IdeaNode> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function expandUserNode(
  ideaId: string,
  nodeId: string,
  description: string
): Promise<IdeaNode[]> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/nodes/${nodeId}/expand/user`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function confirmPath(ideaId: string, nodeChain: string[]): Promise<IdeaPath> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/paths`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_chain: nodeChain }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getLatestPath(ideaId: string): Promise<IdeaPath | null> {
  const r = await fetch(buildApiUrl(`/ideas/${ideaId}/paths/latest`))
  if (r.status === 404) return null
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
