'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { login } from '../../lib/api'
import { clearAuthSession, getAuthSession, setAuthSession } from '../../lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('test')
  const [password, setPassword] = useState('test')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (getAuthSession()) {
      router.replace('/ideas')
    }
  }, [router])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) {
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const response = await login({ username, password })
      setAuthSession({
        accessToken: response.access_token,
        username: response.user.username,
        role: response.user.role,
        expiresAt: Date.now() + response.expires_in * 1000,
      })
      router.replace('/ideas')
    } catch (submitError) {
      clearAuthSession()
      setError(submitError instanceof Error ? submitError.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-xl items-center px-6 py-12">
      <div className="w-full rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase">
          DecisionOS
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">Hackathon Login</h1>
        <p className="mt-2 text-sm text-slate-600">Use seeded account to access the workspace.</p>
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
          Test account pre-filled — username{' '}
          <span className="font-mono font-medium text-slate-700">test</span>, password{' '}
          <span className="font-mono font-medium text-slate-700">test</span>. Just click Sign in.
        </div>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-700">Username</span>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-slate-700">Password</span>
            <input
              type="password"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <p className="text-sm text-rose-600">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-500"
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
