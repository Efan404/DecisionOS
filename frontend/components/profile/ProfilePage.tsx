'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Bell, Ghost, Sparkles, User } from 'lucide-react'

import { ApiError, getProfile, patchProfile, type UserProfile } from '../../lib/api'
import { UserPatternCard } from '../insights/UserPatternCard'

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  news_match: 'News matches',
  cross_idea_insight: 'Cross-idea insights',
  pattern_learned: 'Pattern updates',
}

const ALL_NOTIFY_TYPES = ['news_match', 'cross_idea_insight', 'pattern_learned']

type Section = 'account' | 'notifications' | 'patterns'

const NAV_ITEMS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'account', label: 'Account', icon: <User size={15} /> },
  { id: 'notifications', label: 'Notifications', icon: <Bell size={15} /> },
  { id: 'patterns', label: 'Decision Patterns', icon: <Sparkles size={15} /> },
]

export function ProfilePage() {
  const [activeSection, setActiveSection] = useState<Section>('account')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [email, setEmail] = useState('')
  const [accountSaving, setAccountSaving] = useState(false)
  const [accountError, setAccountError] = useState<string | null>(null)

  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyTypes, setNotifyTypes] = useState<string[]>(ALL_NOTIFY_TYPES)
  const [notifSaving, setNotifSaving] = useState(false)
  const [notifError, setNotifError] = useState<string | null>(null)

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p)
        setEmail(p.email ?? '')
        setNotifyEnabled(p.notify_enabled)
        setNotifyTypes(p.notify_types)
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Failed to load profile'
        setLoadError(msg)
      })
  }, [])

  const handleSaveAccount = async () => {
    setAccountSaving(true)
    setAccountError(null)
    try {
      const updated = await patchProfile({ email: email.trim() || null })
      setProfile(updated)
      toast.success('Email saved')
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Save failed'
      setAccountError(msg)
      toast.error(msg)
    } finally {
      setAccountSaving(false)
    }
  }

  const handleSaveNotifications = async () => {
    setNotifSaving(true)
    setNotifError(null)
    try {
      const updated = await patchProfile({
        notify_enabled: notifyEnabled,
        notify_types: notifyTypes,
      })
      setProfile(updated)
      toast.success('Notification preferences saved')
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Save failed'
      setNotifError(msg)
      toast.error(msg)
    } finally {
      setNotifSaving(false)
    }
  }

  const toggleNotifyType = (type: string) => {
    setNotifyTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  if (loadError) {
    return (
      <main className="px-4 py-8 sm:px-6">
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{loadError}</p>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-[600px] px-0">
      <div className="flex min-h-[600px] divide-x divide-[#1e1e1e]/8">
        {/* ── Left sidebar ─────────────────────────────────────────────── */}
        <aside className="w-16 shrink-0 sm:w-56">
          {/* User identity header */}
          <div className="flex flex-col items-center gap-2 border-b border-[#1e1e1e]/8 px-3 py-5 sm:flex-row sm:gap-3 sm:px-5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#1e1e1e] text-[#b9eb10]">
              <Ghost size={18} />
            </div>
            <div className="hidden min-w-0 sm:block">
              <p className="truncate text-sm font-semibold text-[#1e1e1e]">
                {profile?.username ?? '…'}
              </p>
              <p className="truncate text-xs text-[#1e1e1e]/40">
                {profile?.email ?? 'No email set'}
              </p>
            </div>
          </div>

          {/* Nav items */}
          <nav className="py-2">
            {NAV_ITEMS.map((item) => {
              const isActive = activeSection === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveSection(item.id)}
                  className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition sm:px-5 ${
                    isActive
                      ? 'bg-[#1e1e1e] font-semibold text-[#b9eb10]'
                      : 'text-[#1e1e1e]/60 hover:bg-[#f5f5f5] hover:text-[#1e1e1e]'
                  }`}
                >
                  <span className="shrink-0">{item.icon}</span>
                  <span className="hidden sm:block">{item.label}</span>
                </button>
              )
            })}
          </nav>
        </aside>

        {/* ── Right content ─────────────────────────────────────────────── */}
        <div className="min-w-0 flex-1 px-5 py-6 sm:px-8">
          {activeSection === 'account' && (
            <section className="max-w-lg space-y-5">
              <h2 className="text-base font-semibold text-[#1e1e1e]">Account</h2>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-[#1e1e1e]/50">Username</label>
                <input
                  type="text"
                  value={profile?.username ?? ''}
                  disabled
                  className="w-full rounded-lg border border-[#1e1e1e]/10 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e]/40"
                />
                <p className="text-xs text-[#1e1e1e]/30">Username cannot be changed.</p>
              </div>

              <div className="space-y-1">
                <label htmlFor="email" className="block text-xs font-medium text-[#1e1e1e]/50">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded-lg border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/20"
                />
                <p className="text-xs text-[#1e1e1e]/30">Used for notification emails.</p>
              </div>

              {accountError ? <p className="text-xs text-red-600">{accountError}</p> : null}

              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => void handleSaveAccount()}
                  disabled={accountSaving}
                  className="flex items-center gap-2 rounded-lg bg-[#1e1e1e] px-4 py-2 text-xs font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {accountSaving ? (
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#b9eb10]/40 border-t-[#b9eb10]" />
                  ) : null}
                  {accountSaving ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </section>
          )}

          {activeSection === 'notifications' && (
            <section className="max-w-lg space-y-5">
              <h2 className="text-base font-semibold text-[#1e1e1e]">Notifications</h2>

              <div className="flex items-center justify-between rounded-lg border border-[#1e1e1e]/10 bg-[#f5f5f5] px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-[#1e1e1e]">Email notifications</p>
                  <p className="text-xs text-[#1e1e1e]/40">Receive updates via email</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={notifyEnabled}
                  onClick={() => setNotifyEnabled((v) => !v)}
                  className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#b9eb10] ${
                    notifyEnabled ? 'bg-[#1e1e1e]' : 'bg-[#d0d0d0]'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                      notifyEnabled ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              <div
                className={`space-y-1 transition-opacity ${!notifyEnabled ? 'pointer-events-none opacity-40' : ''}`}
              >
                <p className="mb-2 text-xs font-medium text-[#1e1e1e]/50">Notify me about</p>
                {ALL_NOTIFY_TYPES.map((type) => (
                  <label
                    key={type}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition hover:bg-[#f5f5f5]"
                  >
                    <input
                      type="checkbox"
                      checked={notifyTypes.includes(type)}
                      onChange={() => toggleNotifyType(type)}
                      disabled={!notifyEnabled}
                      className="h-4 w-4 rounded border-[#1e1e1e]/20 accent-[#1e1e1e]"
                    />
                    <span className="text-sm text-[#1e1e1e]/70">{NOTIFY_TYPE_LABELS[type]}</span>
                  </label>
                ))}
              </div>

              {notifError ? <p className="text-xs text-red-600">{notifError}</p> : null}

              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => void handleSaveNotifications()}
                  disabled={notifSaving}
                  className="flex items-center gap-2 rounded-lg bg-[#1e1e1e] px-4 py-2 text-xs font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {notifSaving ? (
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#b9eb10]/40 border-t-[#b9eb10]" />
                  ) : null}
                  {notifSaving ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </section>
          )}

          {activeSection === 'patterns' && (
            <section className="max-w-lg space-y-4">
              <h2 className="text-base font-semibold text-[#1e1e1e]">Decision Patterns</h2>
              <UserPatternCard />
            </section>
          )}
        </div>
      </div>
    </main>
  )
}
