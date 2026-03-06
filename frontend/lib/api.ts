import type {
  AISettings,
  AgentEnvelope,
  AuthLoginRequest,
  AuthLoginResponse,
  AuthUser,
  CreateIdeaRequest,
  IdeaDetail,
  IdeaStatus,
  IdeaSummary,
  PatchAISettingsRequest,
  PatchIdeaContextRequest,
  PatchIdeaRequest,
  ScopeBaselineOut,
  ScopeBaselineResponse,
  ScopeDraftResponse,
  ScopeDraftUpdateRequest,
  ScopeVersionedRequest,
  PrdFeedbackLatest,
  PrdFeedbackRequest,
  TestAIProviderRequest,
  TestAIProviderResponse,
} from './schemas'
import { clearAuthSession, getAccessToken } from './auth'

const resolveRuntimeApiBaseUrl = (): string => {
  // Browser: always use the Next.js rewrite proxy to avoid CORS.
  // NEXT_PUBLIC_API_BASE_URL is intentionally NOT used in the browser;
  // all browser traffic routes through /api-proxy → Next.js server → backend.
  if (typeof window !== 'undefined') {
    return '/api-proxy'
  }

  // SSR / server actions: call the backend directly (server-to-server, no CORS).
  // API_INTERNAL_URL is set to http://api:8000 inside Docker, falls back to local default.
  return process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'
}

export const getApiBaseUrl = (): string => resolveRuntimeApiBaseUrl()

/** @deprecated use getApiBaseUrl() for browser-safe lazy evaluation */
export const apiBaseUrl = resolveRuntimeApiBaseUrl()

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const buildApiError = async (response: Response): Promise<ApiError> => {
  const reason = await response.text().catch(() => '')
  let code: string | undefined
  let messageBody = reason

  if (reason) {
    try {
      const parsed = JSON.parse(reason) as
        | { detail?: string | { code?: string; message?: string } }
        | undefined
      if (parsed?.detail) {
        if (typeof parsed.detail === 'string') {
          messageBody = parsed.detail
        } else {
          code = parsed.detail.code
          messageBody = parsed.detail.message ?? reason
        }
      }
    } catch {
      // Keep raw text when payload is not JSON.
    }
  }

  if (response.status === 401) {
    clearAuthSession()
  }

  return new ApiError(
    `Request failed with ${response.status}${messageBody ? `: ${messageBody}` : ''}`,
    response.status,
    code
  )
}

export const buildApiUrl = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }

  return `${getApiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`
}

export const withAuthHeaders = (headers?: HeadersInit): Headers => {
  const nextHeaders = new Headers(headers ?? {})
  const token = getAccessToken()
  if (token && !nextHeaders.has('Authorization')) {
    nextHeaders.set('Authorization', `Bearer ${token}`)
  }
  return nextHeaders
}

export const jsonPost = async <TRequest, TResponse>(
  path: string,
  payload: TRequest,
  init?: RequestInit
): Promise<TResponse> => {
  const response = await fetch(buildApiUrl(path), {
    method: 'POST',
    ...init,
    headers: withAuthHeaders({
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }

  return (await response.json()) as TResponse
}

export const jsonGet = async <TResponse>(path: string, init?: RequestInit): Promise<TResponse> => {
  const response = await fetch(buildApiUrl(path), {
    method: 'GET',
    ...init,
    headers: withAuthHeaders(init?.headers),
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }

  return (await response.json()) as TResponse
}

export const jsonPatch = async <TRequest, TResponse>(
  path: string,
  payload: TRequest,
  init?: RequestInit
): Promise<TResponse> => {
  const response = await fetch(buildApiUrl(path), {
    method: 'PATCH',
    ...init,
    headers: withAuthHeaders({
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }

  return (await response.json()) as TResponse
}

export const jsonDelete = async (path: string, init?: RequestInit): Promise<void> => {
  const response = await fetch(buildApiUrl(path), {
    method: 'DELETE',
    ...init,
    headers: withAuthHeaders(init?.headers),
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }
}

const buildIdeasQuery = (status?: IdeaStatus[]): string => {
  if (!status || !status.length) {
    return '/ideas'
  }

  const params = new URLSearchParams({ status: status.join(',') })
  return `/ideas?${params.toString()}`
}

export const getDefaultWorkspace = async (): Promise<{ id: string; name: string }> => {
  return await jsonGet('/workspaces/default')
}

export const login = async (payload: AuthLoginRequest): Promise<AuthLoginResponse> => {
  return await jsonPost<AuthLoginRequest, AuthLoginResponse>('/auth/login', payload)
}

export const getMe = async (): Promise<AuthUser> => {
  return await jsonGet<AuthUser>('/auth/me')
}

export const logout = async (): Promise<void> => {
  const response = await fetch(buildApiUrl('/auth/logout'), {
    method: 'POST',
    headers: withAuthHeaders({
      'Content-Type': 'application/json',
    }),
    body: '{}',
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }
}

export const listIdeas = async (status?: IdeaStatus[]): Promise<IdeaSummary[]> => {
  const response = await jsonGet<{ items: IdeaSummary[] }>(buildIdeasQuery(status))
  return response.items
}

export const createIdea = async (payload: CreateIdeaRequest): Promise<IdeaDetail> => {
  return await jsonPost<CreateIdeaRequest, IdeaDetail>('/ideas', payload)
}

export const getIdea = async (ideaId: string): Promise<IdeaDetail> => {
  return await jsonGet<IdeaDetail>(`/ideas/${ideaId}`)
}

export const patchIdea = async (ideaId: string, payload: PatchIdeaRequest): Promise<IdeaDetail> => {
  return await jsonPatch<PatchIdeaRequest, IdeaDetail>(`/ideas/${ideaId}`, payload)
}

export const patchIdeaContext = async (
  ideaId: string,
  payload: PatchIdeaContextRequest
): Promise<IdeaDetail> => {
  return await jsonPatch<PatchIdeaContextRequest, IdeaDetail>(`/ideas/${ideaId}/context`, payload)
}

const toScopeBaselineResponse = (payload: ScopeBaselineOut): ScopeBaselineResponse => ({
  baseline: {
    id: payload.id,
    idea_id: payload.idea_id,
    version: payload.version,
    status: payload.status,
    source_baseline_id: payload.source_baseline_id,
    created_at: payload.created_at,
    frozen_at: payload.frozen_at,
  },
  items: payload.items,
})

const toScopeDraftResponse = (payload: ScopeBaselineOut): ScopeDraftResponse => ({
  ...toScopeBaselineResponse(payload),
  readonly: payload.status !== 'draft',
})

export const getScopeDraft = async (ideaId: string): Promise<ScopeDraftResponse> => {
  const payload = await jsonGet<ScopeBaselineOut>(`/ideas/${ideaId}/scope/draft`)
  return toScopeDraftResponse(payload)
}

export const bootstrapScopeDraft = async (
  ideaId: string,
  payload: ScopeVersionedRequest
): Promise<AgentEnvelope & { data: ScopeDraftResponse }> => {
  const envelope = await jsonPost<
    ScopeVersionedRequest,
    AgentEnvelope & { data: ScopeBaselineOut }
  >(`/ideas/${ideaId}/scope/draft/bootstrap`, payload)
  return {
    ...envelope,
    data: toScopeDraftResponse(envelope.data),
  }
}

export const patchScopeDraft = async (
  ideaId: string,
  payload: ScopeDraftUpdateRequest
): Promise<AgentEnvelope & { data: ScopeDraftResponse }> => {
  const envelope = await jsonPatch<
    ScopeDraftUpdateRequest,
    AgentEnvelope & { data: ScopeBaselineOut }
  >(`/ideas/${ideaId}/scope/draft`, payload)
  return {
    ...envelope,
    data: toScopeDraftResponse(envelope.data),
  }
}

export const freezeScope = async (
  ideaId: string,
  payload: ScopeVersionedRequest
): Promise<AgentEnvelope & { data: ScopeDraftResponse }> => {
  const envelope = await jsonPost<
    ScopeVersionedRequest,
    AgentEnvelope & { data: ScopeBaselineOut }
  >(`/ideas/${ideaId}/scope/freeze`, payload)
  return {
    ...envelope,
    data: toScopeDraftResponse(envelope.data),
  }
}

export const createScopeNewVersion = async (
  ideaId: string,
  payload: ScopeVersionedRequest
): Promise<AgentEnvelope & { data: ScopeDraftResponse }> => {
  const envelope = await jsonPost<
    ScopeVersionedRequest,
    AgentEnvelope & { data: ScopeBaselineOut }
  >(`/ideas/${ideaId}/scope/new-version`, payload)
  return {
    ...envelope,
    data: toScopeDraftResponse(envelope.data),
  }
}

export const getScopeBaseline = async (
  ideaId: string,
  baselineId: string
): Promise<ScopeBaselineResponse> => {
  const payload = await jsonGet<ScopeBaselineOut>(`/ideas/${ideaId}/scope/baselines/${baselineId}`)
  return toScopeBaselineResponse(payload)
}

export const deleteIdea = async (ideaId: string): Promise<void> => {
  await jsonDelete(`/ideas/${ideaId}`)
}

export const getAiSettings = async (): Promise<AISettings> => {
  return await jsonGet<AISettings>('/settings/ai')
}

export const patchAiSettings = async (payload: PatchAISettingsRequest): Promise<AISettings> => {
  return await jsonPatch<PatchAISettingsRequest, AISettings>('/settings/ai', payload)
}

export const testAiProvider = async (
  payload: TestAIProviderRequest
): Promise<TestAIProviderResponse> => {
  return await jsonPost<TestAIProviderRequest, TestAIProviderResponse>('/settings/ai/test', payload)
}

export const postIdeaScopedAgent = async <TRequest, TData>(
  ideaId: string,
  route: 'opportunity' | 'feasibility' | 'scope' | 'prd',
  payload: TRequest
): Promise<AgentEnvelope & { data: TData }> => {
  return await jsonPost<TRequest, AgentEnvelope & { data: TData }>(
    `/ideas/${ideaId}/agents/${route}`,
    payload
  )
}

export const postPrdFeedback = async (
  ideaId: string,
  payload: PrdFeedbackRequest
): Promise<AgentEnvelope & { data: PrdFeedbackLatest }> => {
  return await jsonPost<PrdFeedbackRequest, AgentEnvelope & { data: PrdFeedbackLatest }>(
    `/ideas/${ideaId}/prd/feedback`,
    payload
  )
}

// ── Profile ──────────────────────────────────────────────────────────────────

export type UserProfile = {
  username: string
  email: string | null
  notify_enabled: boolean
  notify_types: string[]
}

export type PatchProfileRequest = {
  email?: string | null
  notify_enabled?: boolean
  notify_types?: string[]
}

export const getProfile = async (): Promise<UserProfile> => {
  return await jsonGet<UserProfile>('/profile')
}

export const patchProfile = async (payload: PatchProfileRequest): Promise<UserProfile> => {
  return await jsonPatch<PatchProfileRequest, UserProfile>('/profile', payload)
}

// ── Notifications ─────────────────────────────────────────────────────────────

export type Notification = {
  id: string
  type: string
  title: string
  body: string
  metadata: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export const getNotifications = async (unreadOnly = false): Promise<Notification[]> => {
  const data = await jsonGet<{ notifications: Notification[] }>(
    `/notifications${unreadOnly ? '?unread_only=true' : ''}`
  )
  return data.notifications
}

export const dismissNotification = async (id: string): Promise<boolean> => {
  const data = await jsonPost<Record<string, never>, { dismissed: boolean }>(
    `/notifications/${id}/dismiss`,
    {}
  )
  return data.dismissed
}

// ── Insights ──────────────────────────────────────────────────────────────────

export type CrossIdeaInsight = {
  idea_a_id?: string
  idea_b_id?: string
  idea_a_title?: string
  idea_b_title?: string
  analysis?: string
  [key: string]: unknown
}

export type CrossIdeaAnalysisResult = {
  insights: CrossIdeaInsight[]
  agent_thoughts: { agent: string; thought: string }[]
}

export const getCrossIdeaInsights = async (): Promise<CrossIdeaAnalysisResult> => {
  return await jsonGet<CrossIdeaAnalysisResult>('/insights/cross-idea')
}

export const triggerCrossIdeaAnalysis = async (): Promise<CrossIdeaAnalysisResult> => {
  return await jsonPost<Record<string, never>, CrossIdeaAnalysisResult>(
    '/insights/cross-idea-analysis',
    {}
  )
}

export type UserPatternsResult = {
  preferences: Record<string, string>
}

export const getUserPatterns = async (): Promise<UserPatternsResult> => {
  return await jsonGet<UserPatternsResult>('/insights/user-patterns')
}

// ── PRD Backlog Export ────────────────────────────────────────────────────────

export const downloadPrdBacklogExport = async (
  ideaId: string,
  format: 'json' | 'csv'
): Promise<void> => {
  const url = buildApiUrl(`/ideas/${ideaId}/prd/export?format=${format}`)
  const response = await fetch(url, {
    method: 'GET',
    headers: withAuthHeaders(),
  })

  if (!response.ok) {
    throw await buildApiError(response)
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = `decisionos-backlog-${ideaId}.${format}`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(objectUrl)
}
