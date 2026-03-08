/**
 * SSE proxy route handler — streams backend SSE events to the browser
 * without buffering, bypassing the Next.js rewrite proxy limitation.
 *
 * Usage: POST /api/sse-proxy?path=/ideas/{id}/agents/feasibility/stream
 *        Body + headers forwarded to backend as-is.
 */
import { NextRequest } from 'next/server'

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'

export const runtime = 'nodejs'
// Disable body size limit for streaming responses
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  const backendPath = request.nextUrl.searchParams.get('path')
  if (!backendPath) {
    return new Response(JSON.stringify({ error: 'Missing path parameter' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const backendUrl = `${API_INTERNAL_URL}${backendPath}`
  const body = await request.text()

  // Forward relevant headers
  const headers: Record<string, string> = {
    'Content-Type': request.headers.get('content-type') || 'application/json',
    Accept: 'text/event-stream',
  }
  const auth = request.headers.get('authorization')
  if (auth) {
    headers['Authorization'] = auth
  }

  try {
    const backendResponse = await fetch(backendUrl, {
      method: 'POST',
      headers,
      body,
      // @ts-expect-error — Node.js fetch supports signal for timeout
      signal: AbortSignal.timeout(300_000), // 5 minute timeout
    })

    if (!backendResponse.ok || !backendResponse.body) {
      const text = await backendResponse.text().catch(() => '')
      return new Response(text || 'Backend error', {
        status: backendResponse.status,
        headers: { 'Content-Type': backendResponse.headers.get('content-type') || 'text/plain' },
      })
    }

    // Stream the SSE response through without buffering
    return new Response(backendResponse.body, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-store',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no', // Disable nginx buffering if present
      },
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'SSE proxy error'
    return new Response(JSON.stringify({ error: message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
