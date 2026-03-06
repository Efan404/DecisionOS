'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { dismissNotification, getNotifications, type Notification } from '../../lib/api'

const POLL_INTERVAL_MS = 30_000

export function NotificationBell() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)
  // Per-notification dismissing state instead of shared global loading
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())
  const panelRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(true)
  const unreadCount = notifications.filter((n) => !n.read_at).length

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await getNotifications(true)
      // Guard against setting state after unmount
      if (mountedRef.current) {
        setNotifications(data)
      }
    } catch {
      // silent — bell stays at previous state
    }
  }, [])

  // Initial fetch + polling
  useEffect(() => {
    void fetchNotifications()
    const interval = setInterval(() => void fetchNotifications(), POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleOpen = () => {
    setOpen((v) => !v)
    if (!open) void fetchNotifications()
  }

  const handleDismiss = async (id: string) => {
    if (dismissingIds.has(id)) return
    setDismissingIds((prev) => new Set(prev).add(id))
    try {
      await dismissNotification(id)
      if (mountedRef.current) {
        setNotifications((prev) => prev.filter((n) => n.id !== id))
      }
    } catch {
      // silent — item stays visible
    } finally {
      if (mountedRef.current) {
        setDismissingIds((prev) => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
      }
    }
  }

  // Sequential dismiss-all to avoid N concurrent requests
  const handleDismissAll = async () => {
    for (const n of notifications) {
      if (!mountedRef.current) break
      await handleDismiss(n.id)
    }
  }

  const anyDismissing = dismissingIds.size > 0

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={handleOpen}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-[#1e1e1e]/12 bg-white transition hover:bg-[#f5f5f5]"
      >
        <svg
          viewBox="0 0 16 16"
          fill="none"
          className="h-4 w-4 text-[#1e1e1e]/60"
          aria-hidden="true"
        >
          <path
            d="M8 1a5 5 0 0 0-5 5v2.5L2 10h12l-1-1.5V6a5 5 0 0 0-5-5ZM6.5 13a1.5 1.5 0 0 0 3 0"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#b9eb10] text-[9px] font-bold text-[#1e1e1e]"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-10 right-0 z-50 w-80 rounded-xl border border-[#1e1e1e]/10 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-[#1e1e1e]/8 px-4 py-2.5">
            <span className="text-xs font-semibold text-[#1e1e1e]">Notifications</span>
            {notifications.length > 0 && (
              <button
                type="button"
                onClick={() => void handleDismissAll()}
                disabled={anyDismissing}
                className="text-[11px] text-[#1e1e1e]/40 transition hover:text-[#1e1e1e]/70 disabled:opacity-50"
              >
                Dismiss all
              </button>
            )}
          </div>

          <ul className="max-h-72 divide-y divide-[#1e1e1e]/6 overflow-y-auto">
            {notifications.length === 0 ? (
              <li className="px-4 py-6 text-center text-xs text-[#1e1e1e]/40">
                No new notifications
              </li>
            ) : (
              notifications.map((n) => {
                const isDismissing = dismissingIds.has(n.id)
                return (
                  <li
                    key={n.id}
                    className={`flex items-start gap-3 px-4 py-3 transition-opacity ${isDismissing ? 'opacity-50' : ''}`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs leading-snug font-medium text-[#1e1e1e]">{n.title}</p>
                      <p className="mt-0.5 text-[11px] leading-snug text-[#1e1e1e]/50">{n.body}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDismiss(n.id)}
                      disabled={isDismissing}
                      aria-label="Dismiss notification"
                      className="mt-0.5 shrink-0 text-[#1e1e1e]/30 transition hover:text-[#1e1e1e]/60 disabled:opacity-40"
                    >
                      <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
                        <path
                          d="M2 2l8 8M10 2L2 10"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
