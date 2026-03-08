/**
 * Long-running request proxy — forwards POST requests to the backend with a
 * 5-minute timeout, bypassing the ~30s Next.js rewrite proxy limit.
 *
 * Usage: POST /api/long-proxy?path=/ideas/{id}/agents/prd/ppt
 */
import { NextRequest } from 'next/server'

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'

export const runtime = 'nodejs'
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

  const headers: Record<string, string> = {
    'Content-Type': request.headers.get('content-type') || 'application/json',
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

    const responseBody = await backendResponse.text()
    return new Response(responseBody, {
      status: backendResponse.status,
      headers: {
        'Content-Type': backendResponse.headers.get('content-type') || 'application/json',
      },
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Proxy error'
    return new Response(JSON.stringify({ error: message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
