import { jsonGet } from './api'

// ---- Types ----

export interface CompetitorCard {
  id: string
  name: string
  canonical_url: string | null
  category: string | null
  status: 'candidate' | 'tracked' | 'archived'
  latest_snapshot: CompetitorSnapshot | null
  evidence_count: number
}

export interface CompetitorSnapshot {
  id: string
  snapshot_version: number
  summary: Record<string, unknown>
  quality_score: number | null
  traction_score: number | null
  relevance_score: number | null
  underrated_score: number | null
  confidence: number | null
  created_at: string
}

export interface MarketSignal {
  id: string
  signal_type: 'competitor_update' | 'market_news' | 'community_buzz' | 'pricing_change'
  title: string
  summary: string
  severity: 'low' | 'medium' | 'high'
  detected_at: string
  evidence_source_id: string | null
}

// ---- Backend response shapes ----

interface CompetitorWithSnapshotResponse {
  competitor: {
    id: string
    name: string
    canonical_url: string | null
    category: string | null
    status: string
    [key: string]: unknown
  }
  latest_snapshot: {
    id: string
    snapshot_version: number
    summary_json: Record<string, unknown>
    quality_score: number | null
    traction_score: number | null
    relevance_score: number | null
    underrated_score: number | null
    confidence: number | null
    created_at: string
    [key: string]: unknown
  } | null
  link: { [key: string]: unknown }
}

interface CompetitorListResponse {
  idea_id: string
  data: CompetitorWithSnapshotResponse[]
}

interface SignalListResponse {
  idea_id: string
  data: MarketSignal[]
}

// ---- API functions ----

export async function fetchCompetitorsForIdea(ideaId: string): Promise<CompetitorCard[]> {
  try {
    const response = await jsonGet<CompetitorListResponse>(
      `/ideas/${ideaId}/evidence/competitors`
    )
    return (response.data || []).map((item) => ({
      id: item.competitor.id,
      name: item.competitor.name,
      canonical_url: item.competitor.canonical_url,
      category: item.competitor.category,
      status: (item.competitor.status as CompetitorCard['status']) || 'candidate',
      latest_snapshot: item.latest_snapshot
        ? {
            id: item.latest_snapshot.id,
            snapshot_version: item.latest_snapshot.snapshot_version,
            summary: item.latest_snapshot.summary_json,
            quality_score: item.latest_snapshot.quality_score,
            traction_score: item.latest_snapshot.traction_score,
            relevance_score: item.latest_snapshot.relevance_score,
            underrated_score: item.latest_snapshot.underrated_score,
            confidence: item.latest_snapshot.confidence,
            created_at: item.latest_snapshot.created_at,
          }
        : null,
      evidence_count: 0,
    }))
  } catch {
    return []
  }
}

export async function fetchSignalsForIdea(ideaId: string): Promise<MarketSignal[]> {
  try {
    const response = await jsonGet<SignalListResponse>(
      `/ideas/${ideaId}/evidence/signals`
    )
    return response.data || []
  } catch {
    return []
  }
}

// ---- Mock data (kept for tests) ----

export const MOCK_COMPETITORS: CompetitorCard[] = [
  {
    id: 'comp-1',
    name: 'Competitor Alpha',
    canonical_url: 'https://alpha.example.com',
    category: 'Project Management',
    status: 'tracked',
    latest_snapshot: {
      id: 'snap-1',
      snapshot_version: 1,
      summary: { positioning: 'AI-first project management' },
      quality_score: 7.5,
      traction_score: 6.0,
      relevance_score: 8.2,
      underrated_score: 3.5,
      confidence: 0.75,
      created_at: '2026-03-07T00:00:00.000Z',
    },
    evidence_count: 4,
  },
  {
    id: 'comp-2',
    name: 'Competitor Beta',
    canonical_url: 'https://beta.example.com',
    category: 'Dev Tools',
    status: 'candidate',
    latest_snapshot: null,
    evidence_count: 1,
  },
]

export const MOCK_SIGNALS: MarketSignal[] = [
  {
    id: 'sig-1',
    signal_type: 'market_news',
    title: 'Alpha raises Series B',
    summary: 'Competitor Alpha announced $30M Series B, plans to expand AI capabilities.',
    severity: 'high',
    detected_at: '2026-03-06T12:00:00.000Z',
    evidence_source_id: 'es-1',
  },
  {
    id: 'sig-2',
    signal_type: 'community_buzz',
    title: 'Growing discussion on solo dev tools',
    summary: 'HN thread with 200+ comments about solo developer workflow tools.',
    severity: 'medium',
    detected_at: '2026-03-05T08:00:00.000Z',
    evidence_source_id: null,
  },
]
