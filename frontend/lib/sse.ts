import { stream, type ServerSentEventMessage } from 'fetch-event-stream'

import { buildApiUrl, withAuthHeaders } from './api'
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
    const eventStream = await stream(buildApiUrl(path), {
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
