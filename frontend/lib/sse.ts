import { stream, type ServerSentEventMessage } from 'fetch-event-stream'

import { buildApiUrl, withAuthHeaders } from './api'

/**
 * Build the URL for SSE streams.
 *
 * Strategy (browser):
 *  1. NEXT_PUBLIC_API_SSE_URL set → use it (direct backend, best latency)
 *  2. localhost/127.0.0.1 → direct connect to http://127.0.0.1:8000
 *  3. Production → /api/sse-proxy?path=... (Next.js Route Handler that streams
 *     without buffering; the rewrite proxy at /api-proxy buffers SSE and has a
 *     ~30s timeout which breaks long-running agent streams)
 */
const buildSseUrl = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  if (typeof window !== 'undefined') {
    const sseEnv = process.env.NEXT_PUBLIC_API_SSE_URL
    if (sseEnv) {
      return `${sseEnv}${path.startsWith('/') ? path : `/${path}`}`
    }
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return `http://127.0.0.1:8000${path.startsWith('/') ? path : `/${path}`}`
    }
    // Production: use the streaming SSE proxy route handler
    return `/api/sse-proxy?path=${encodeURIComponent(path.startsWith('/') ? path : `/${path}`)}`
  }
  // SSR: call backend directly (server-to-server).
  const base = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}
import { clearAuthSession } from './auth'

type SseEvent<T = unknown> = {
  event: string
  data: T
}

type StreamPostHandlers<TProgress = unknown, TPartial = unknown, TDone = unknown> = {
  headers?: HeadersInit
  onEvent?: (event: SseEvent) => void
  onProgress?: (data: TProgress) => void
  onPartial?: (data: TPartial) => void
  onDone?: (data: TDone) => void
  onError?: (error: unknown) => void
  onAgentThought?: (data: { agent: string; thought: string }) => void
}

type SseErrorData = {
  code?: string
  message?: string
}

export class SseEventError extends Error {
  payload: unknown

  constructor(payload: unknown) {
    const message = getSseErrorMessage(payload)
    super(message)
    this.name = 'SseEventError'
    this.payload = payload
  }
}

export const isSseEventError = (error: unknown): error is SseEventError => {
  return error instanceof SseEventError
}

const getSseErrorMessage = (payload: unknown): string => {
  if (typeof payload === 'object' && payload !== null) {
    const data = payload as SseErrorData
    if (data.code && data.message) {
      return `${data.code}: ${data.message}`
    }
    if (data.message) {
      return data.message
    }
  }

  return 'SSE stream failed.'
}

const parseStreamMessage = (message: ServerSentEventMessage): SseEvent | null => {
  if (!message.data) {
    return null
  }

  let parsed: unknown = message.data
  try {
    parsed = JSON.parse(message.data)
  } catch {
    // Keep raw text when payload is not JSON.
  }

  return {
    event: message.event ?? 'message',
    data: parsed,
  }
}

export const streamPost = async <
  TRequest,
  TProgress = unknown,
  TPartial = unknown,
  TDone = unknown,
>(
  path: string,
  payload: TRequest,
  handlers: StreamPostHandlers<TProgress, TPartial, TDone> = {},
  signal?: AbortSignal
): Promise<void> => {
  try {
    const eventStream = await stream(buildSseUrl(path), {
      method: 'POST',
      headers: withAuthHeaders({
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(handlers.headers ?? {}),
      }),
      body: JSON.stringify(payload),
      signal,
    })

    for await (const message of eventStream) {
      const parsed = parseStreamMessage(message)
      if (!parsed) {
        continue
      }

      handlers.onEvent?.(parsed)

      if (parsed.event === 'progress') {
        handlers.onProgress?.(parsed.data as TProgress)
        continue
      }

      if (parsed.event === 'partial') {
        handlers.onPartial?.(parsed.data as TPartial)
        continue
      }

      if (parsed.event === 'agent_thought') {
        handlers.onAgentThought?.(parsed.data as { agent: string; thought: string })
        continue
      }

      if (parsed.event === 'done') {
        handlers.onDone?.(parsed.data as TDone)
        continue
      }

      if (parsed.event === 'error') {
        throw new SseEventError(parsed.data)
      }
    }
  } catch (error) {
    if (isSseEventError(error)) {
      handlers.onError?.(error)
      throw error
    }

    if (error instanceof Response) {
      if (error.status === 401) {
        clearAuthSession()
      }
      const bodyText = await error.text().catch(() => '')
      const responseError = new Error(
        `SSE request failed with ${error.status}${bodyText ? `: ${bodyText}` : ''}`
      )
      handlers.onError?.(responseError)
      throw responseError
    }

    handlers.onError?.(error)
    throw error
  }
}
