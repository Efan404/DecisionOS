'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import { login } from '../../lib/api'
import { clearAuthSession, getAuthSession, setAuthSession } from '../../lib/auth'

// Floating ambient dots (fixed random positions, animated via CSS)
const AMBIENT_DOTS = [
  { cx: '18%', cy: '22%', r: 3, delay: '0s', dur: '6s' },
  { cx: '72%', cy: '15%', r: 1.5, delay: '1.2s', dur: '8s' },
  { cx: '85%', cy: '55%', r: 2.5, delay: '0.4s', dur: '7s' },
  { cx: '30%', cy: '70%', r: 2, delay: '2s', dur: '9s' },
  { cx: '60%', cy: '80%', r: 1.5, delay: '0.8s', dur: '5s' },
  { cx: '10%', cy: '88%', r: 3, delay: '1.6s', dur: '10s' },
  { cx: '50%', cy: '40%', r: 1, delay: '3s', dur: '7s' },
  { cx: '90%', cy: '30%', r: 2, delay: '0.2s', dur: '6s' },
]

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('test')
  const [password, setPassword] = useState('test')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mouse-follow cursor dot
  const panelRef = useRef<HTMLDivElement>(null)
  const [mouse, setMouse] = useState({ x: 50, y: 50 }) // percentage
  const [trailDots, setTrailDots] = useState<{ id: number; x: number; y: number }[]>([])
  const trailIdRef = useRef(0)

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    setMouse({ x, y })

    // Spawn a trail dot
    const id = ++trailIdRef.current
    setTrailDots((prev) => [...prev.slice(-18), { id, x, y }])
    setTimeout(() => setTrailDots((prev) => prev.filter((d) => d.id !== id)), 700)
  }, [])

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
    <div className="flex min-h-screen w-full">
      {/* ── Left panel: form ── */}
      <div className="flex w-full flex-col justify-center bg-white px-8 py-12 sm:px-14 lg:w-1/2 lg:px-20">
        <div className="mx-auto w-full max-w-sm">
          <p className="text-xs font-bold tracking-[0.25em] text-[#1e1e1e]/40 uppercase">
            DecisionOS
          </p>
          <h1 className="mt-8 text-3xl leading-tight font-bold text-[#1e1e1e]">Welcome back</h1>
          <p className="mt-2 text-sm text-[#1e1e1e]/50">Sign in to your workspace to continue.</p>
          <div className="mt-4 rounded-lg border border-[#b9eb10]/40 bg-[#b9eb10]/10 px-3 py-2 text-xs text-[#1e1e1e]/60">
            Test account pre-filled — username{' '}
            <span className="font-mono font-medium text-[#1e1e1e]/80">test</span>, password{' '}
            <span className="font-mono font-medium text-[#1e1e1e]/80">test</span>. Just click Sign
            in.
          </div>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium text-[#1e1e1e]/70">Username</span>
              <input
                className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-4 py-3 text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/25"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                placeholder="mock"
                required
              />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium text-[#1e1e1e]/70">Password</span>
              <input
                type="password"
                className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-4 py-3 text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/25"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                required
              />
            </label>

            {error ? (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-[#1e1e1e] px-4 py-3 text-sm font-bold text-white transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Signing in...' : 'Sign in →'}
            </button>
          </form>
        </div>
      </div>

      {/* ── Right panel: brand / slogan ── */}
      <div
        ref={panelRef}
        onMouseMove={handleMouseMove}
        className="relative hidden overflow-hidden rounded-l-[2.5rem] bg-[#1e1e1e] lg:flex lg:w-1/2 lg:flex-col lg:justify-between lg:p-14"
      >
        {/* Static decorative glows */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-40 -right-40 h-[560px] w-[560px] rounded-full"
          style={{
            background:
              'radial-gradient(circle at 60% 40%, rgba(185,235,16,0.12) 0%, transparent 65%)',
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -left-28 h-[380px] w-[380px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(185,235,16,0.07) 0%, transparent 70%)',
          }}
        />

        {/* Mouse-follow glow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-full transition-[left,top] duration-75 ease-out"
          style={{
            width: 320,
            height: 320,
            left: `calc(${mouse.x}% - 160px)`,
            top: `calc(${mouse.y}% - 160px)`,
            background: 'radial-gradient(circle, rgba(185,235,16,0.18) 0%, transparent 70%)',
          }}
        />

        {/* Cursor dot */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-full transition-[left,top] duration-75 ease-out"
          style={{
            width: 8,
            height: 8,
            left: `calc(${mouse.x}% - 4px)`,
            top: `calc(${mouse.y}% - 4px)`,
            background: '#b9eb10',
            boxShadow: '0 0 10px 3px #b9eb1099',
          }}
        />

        {/* Trail dots */}
        {trailDots.map((dot, i) => (
          <div
            key={dot.id}
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full"
            style={{
              width: Math.max(2, 5 - (trailDots.length - 1 - i) * 0.3),
              height: Math.max(2, 5 - (trailDots.length - 1 - i) * 0.3),
              left: `calc(${dot.x}% - 3px)`,
              top: `calc(${dot.y}% - 3px)`,
              background: '#b9eb10',
              opacity: ((i + 1) / trailDots.length) * 0.6,
              transition: 'opacity 0.7s ease-out',
            }}
          />
        ))}

        {/* Ambient floating dots (SVG, pure CSS animation) */}
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 h-full w-full"
          xmlns="http://www.w3.org/2000/svg"
        >
          <style>{`
            @keyframes floatDot {
              0%, 100% { transform: translateY(0px) scale(1); opacity: 0.35; }
              50%       { transform: translateY(-14px) scale(1.3); opacity: 0.7; }
            }
          `}</style>
          {AMBIENT_DOTS.map((d, i) => (
            <circle
              key={i}
              cx={d.cx}
              cy={d.cy}
              r={d.r}
              fill="#b9eb10"
              style={{
                animation: `floatDot ${d.dur} ${d.delay} ease-in-out infinite`,
                transformOrigin: `${d.cx} ${d.cy}`,
              }}
            />
          ))}
        </svg>

        {/* Top logo mark */}
        <div className="relative z-10">
          <svg
            viewBox="0 0 1717.66 458.02"
            className="h-12 w-auto"
            xmlns="http://www.w3.org/2000/svg"
          >
            <g>
              <path
                fill="#b9eb10"
                d="M82.93,415.8l106.08-145.1h42.32l-78.04,109.92,155.58.05c27.9-1.23,49.37-6.83,68.12-28.61l83.67-115.4-.11-2.18-88.49-120.45c-10.46-10.85-34.94-23.6-50.05-23.6h-187.42l81.34,112.12h-45.07L65.35,55.26l255.62-.06c37.22,2.67,65.16,18.55,87.76,47.44,33.02,42.2,61.95,88.11,95.06,130.33l1.02,2.94-103.08,142c-15.02,17.1-50.07,37.89-73.13,37.89H82.93Z"
              />
              <path
                fill="#b9eb10"
                d="M202.75,353.14l70.35-98.93h-137.95c-17.17,31.92-67.37,23.28-69.85-13.69-2.77-41.34,48.51-55.59,69.85-21.48h136.85l-31.87-31.34c-.38-2.33.37-1.29,1.51-1.74,4.94-1.94,9.12-3.05,13.78-6.03,4.95-3.16,7.76-7.34,12.58-10.27l74.27,68.47c-13.01,14.06-30.97,25.87-43.35,40.26-10.28,11.95-18.73,27.47-29.12,39.59h51.11c1.34,0,6.92-3.7,8.23-4.96l55.56-76.37c.61-1.39-2.12-4.55-2.98-5.85-13.04-19.85-36.02-53.53-51.5-70.51-3.93-4.32-6.45-6.65-12.55-7.24-20.06-1.93-43.18,1.57-63.58.04-20.18,30.31-67.82,8.65-55.78-26.95,8.66-25.61,39.74-26.54,56.68-8.23,34.58,3.03,76.94-10.5,102.73,19.28l70.94,97.32v3.18s-71.45,96.8-71.45,96.8c-6.77,8.06-23.56,18.67-34.09,18.67h-120.36ZM224.41,124.73c-12.61,2.86-10.79,23.75,4.12,22.9,17.16-.98,11.91-26.53-4.12-22.9ZM99.14,222.56c-14.83,2.85-15.39,26.59-.3,28.37,25.14,2.97,20.54-32.26.3-28.37Z"
              />
            </g>
            <g>
              <path
                fill="white"
                d="M550.84,328.26v-142.61c19.8-.37,39.74-2.6,59.6-1.53,51.29,2.77,83.4,28.69,78.65,83.18-2.63,30.21-33.13,60.96-64.01,60.96h-74.25ZM577.3,304.74h44.84c1.42,0,13.06-4.27,15.27-5.31,33.43-15.83,33.45-70.23-.29-86.12-3.45-1.63-13.28-5.6-16.45-5.6h-43.37v97.03Z"
              />
              <path
                fill="white"
                d="M1470.88,183.14c108.79-10.71,115.98,156.08-1.96,146.64-85.56-6.85-90.47-137.54,1.96-146.64ZM1475.33,206.62c-59.13,3.47-59.41,94.23-1.93,99.57,71.4,6.63,71.28-103.64,1.93-99.57Z"
              />
              <path
                fill="white"
                d="M1673.97,194.59l-7.26,21.93c-9.96-2.16-18.62-8.5-29.03-9.91-13.35-1.81-41.08-1.88-41.65,16.52-.24,7.82,2.49,11.08,9.1,14.56,25.68,13.54,75.06,7.51,74.91,50.13-.16,47.51-67.13,48.78-99.11,34.34-3.27-1.48-15.64-7.91-15.03-11.62l8.22-19.05c19.57,10.69,41.85,21.3,64.66,13.96,15.11-4.86,19.8-19.76,5.44-28.94-24.13-15.42-77.69-7.98-76.09-51.92,1.76-48.5,74.47-48.81,105.85-30.01Z"
              />
              <path
                fill="white"
                d="M812.53,281.21h-83.07l-1.63,3.04c8.43,27.07,44.99,30.48,63.37,11.72,2.73,3.78,14.96,12.13,13.81,16.55-29.57,31.24-91.08,19.81-102.03-23.95-21.81-87.16,119.32-98.19,109.54-7.36ZM787.54,265.04c-3.73-35.34-56.21-35.81-60.28,0h60.28Z"
              />
              <path
                fill="white"
                d="M1190.05,218.41c42.22-5.39,75.55,21.8,68.76,65.82-8.07,52.3-84.26,61.98-108.78,17.48-18.71-33.96.82-78.29,40.02-83.3ZM1192.91,240.38c-32.5,6.6-31.09,64.68,5.77,67.2,47.69,3.27,45.57-77.63-5.77-67.2Z"
              />
              <path
                fill="white"
                d="M1384.44,328.26h-24.99v-61.01c0-.62-1.79-9.88-2.15-11.08-6.26-20.81-39.33-20.34-49.09-3.41-.9,1.57-4.63,11.98-4.63,13.01v62.48h-26.46v-108.79h24.99v11.75s17.1-10.09,17.1-10.09c21.33-7.42,49.95-3.9,60.64,18.37.76,1.59,4.59,10.96,4.59,11.58v77.19Z"
              />
              <path
                fill="white"
                d="M1025.39,218.41c17.09-2.04,38.63-.69,53.14,9.3l-9.43,19.66c-9.9-5.94-22.22-9.6-33.88-8.83-19,1.24-30.12,15.56-7.51,22.31,21.09,6.3,56.09,3.32,55.39,35.74-.89,41.09-71.7,39.61-95.49,20.42l9.41-19.47c13.96,8.49,31.89,12.5,48.19,9.79,10.9-1.81,16.72-12.52,6.03-18.55-14.97-8.45-50.66-2.6-59.03-24.77-9.3-24.64,9.92-42.82,33.18-45.59Z"
              />
              <path
                fill="white"
                d="M928.62,244.39l-19.69,10.46c-13.37-23.14-50.04-19.11-57.75,6.94-7.84,26.47,13.15,52.73,41.06,44,8.59-2.68,10.74-8.74,18.02-12.78l19.2,10.24c-17.3,34.3-70.31,34.9-93.37,6.6-24.07-29.54-13.49-75.76,23.09-88.59,23.16-8.12,61-3.32,69.44,23.12Z"
              />
              <rect fill="white" x="944.85" y="219.47" width="26.46" height="108.79" />
              <polygon
                fill="white"
                points="1125.69 219.47 1125.69 326.06 1123.48 328.26 1099.22 328.26 1099.22 219.47 1125.69 219.47"
              />
              <path
                fill="white"
                d="M1099.72,198.38c-15.75-15.43,10.03-37.5,24.53-22.32,15.21,15.92-10.01,36.55-24.53,22.32Z"
              />
              <path
                fill="white"
                d="M956.31,171.26c22.39-1.92,25,30.88,2.28,31.53-21.57.62-22.58-29.79-2.28-31.53Z"
              />
            </g>
          </svg>
        </div>

        {/* Main slogan */}
        <div className="relative z-10">
          <p
            className="leading-[1.0] font-extrabold tracking-tight text-white"
            style={{ fontSize: 'clamp(4.5rem, 8vw, 9rem)' }}
          >
            Make a<br />
            <span className="text-[#b9eb10]">Decision.</span>
          </p>
          <div className="mt-12 border-l-2 border-[#b9eb10]/40 pl-5">
            <p className="text-base leading-7 text-white/55">
              A single-user, single-workspace decision management system for product ideas.
            </p>
            <p className="mt-5 text-xs font-semibold tracking-[0.2em] text-[#b9eb10]/60 uppercase">
              DecisionOS · 2026
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
