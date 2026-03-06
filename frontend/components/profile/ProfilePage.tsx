'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Bell, Ghost, Loader2, Sparkles, User } from 'lucide-react'

import { ApiError, getProfile, patchProfile, type UserProfile } from '../../lib/api'
import { HoverCard } from '../common/HoverCard'
import { UserPatternCard } from '../insights/UserPatternCard'

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  news_match: 'News matches',
  cross_idea_insight: 'Cross-idea insights',
  pattern_learned: 'Pattern updates',
}

const ALL_NOTIFY_TYPES = ['news_match', 'cross_idea_insight', 'pattern_learned']

type Section = 'account' | 'notifications' | 'patterns'

const NAV_ITEMS: { id: Section; label: string; icon: React.ReactNode; description: string }[] = [
  { id: 'account', label: 'Account', icon: <User size={14} />, description: 'Username & email' },
  {
    id: 'notifications',
    label: 'Notifications',
    icon: <Bell size={14} />,
    description: 'Email preferences',
  },
  {
    id: 'patterns',
    label: 'Decision Patterns',
    icon: <Sparkles size={14} />,
    description: 'Learned from your choices',
  },
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
      <div className="px-6 py-8">
        <div className="max-w-sm rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{loadError}</p>
        </div>
      </div>
    )
  }

  const activeNav = NAV_ITEMS.find((n) => n.id === activeSection)!

  return (
    <div className="flex min-h-[520px]">
      {/* ── Left sidebar ─────────────────────────────────────────────────── */}
      <aside className="flex w-14 shrink-0 flex-col border-r border-[#1e1e1e]/8 sm:w-52">
        {/* Identity card — same height as right header bar */}
        <div className="flex h-[56px] items-center border-b border-[#1e1e1e]/8 px-3 sm:px-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1e1e1e] text-[#b9eb10]">
              <Ghost size={15} />
            </div>
            <div className="hidden min-w-0 sm:block">
              <HoverCard align="left" trigger={
                <p className="truncate text-[13px] leading-snug font-semibold text-[#1e1e1e] cursor-default">
                  {profile?.username ?? '…'}
                </p>
              }>
                <span className="break-all text-[12px] font-semibold text-slate-800">{profile?.username ?? '…'}</span>
              </HoverCard>
              <HoverCard align="left" trigger={
                <p className="mt-0.5 truncate text-[11px] leading-snug text-[#1e1e1e]/40 cursor-default">
                  {profile?.email ?? 'No email set'}
                </p>
              }>
                <span className="break-all text-[11px] text-slate-600">{profile?.email ?? 'No email set'}</span>
              </HoverCard>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-1">
          {NAV_ITEMS.map((item) => {
            const isActive = activeSection === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveSection(item.id)}
                className={`group relative flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 text-left transition-colors duration-150 sm:px-4 ${
                  isActive
                    ? 'bg-[#f5f5f5] text-[#1e1e1e]'
                    : 'text-[#1e1e1e]/45 hover:bg-[#fafafa] hover:text-[#1e1e1e]/70'
                }`}
              >
                {/* Active indicator bar */}
                <span
                  className={`absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-r-full bg-[#b9eb10] transition-opacity duration-150 ${
                    isActive ? 'opacity-100' : 'opacity-0'
                  }`}
                />
                <span className="shrink-0">{item.icon}</span>
                <span
                  className={`hidden text-[13px] sm:block ${isActive ? 'font-medium text-[#1e1e1e]' : ''}`}
                >
                  {item.label}
                </span>
              </button>
            )
          })}
        </nav>
      </aside>

      {/* ── Right content ────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Section header bar — same height as sidebar identity card */}
        <div className="flex h-[56px] items-center gap-3 border-b border-[#1e1e1e]/8 px-6 sm:px-8">
          <span className="text-[#1e1e1e]/35">{activeNav.icon}</span>
          <div className="min-w-0 flex-1">
            <h1 className="text-[13px] leading-tight font-semibold text-[#1e1e1e]">
              {activeNav.label}
            </h1>
            <p className="text-[11px] leading-tight text-[#1e1e1e]/35">{activeNav.description}</p>
          </div>
        </div>

        {/* Section body */}
        <div className="flex-1 px-6 py-6 sm:px-8">
          {/* ── Account ── */}
          {activeSection === 'account' && (
            <div className="max-w-md space-y-5">
              {/* Username (read-only) */}
              <div className="space-y-1.5">
                <label className="block text-[11px] font-semibold tracking-wider text-[#1e1e1e]/35 uppercase">
                  Username
                </label>
                <input
                  type="text"
                  value={profile?.username ?? ''}
                  disabled
                  className="w-full rounded-lg border border-[#1e1e1e]/8 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e]/30 select-none"
                />
                <p className="text-[11px] text-[#1e1e1e]/25">Cannot be changed.</p>
              </div>

              {/* Email */}
              <div className="space-y-1.5">
                <label
                  htmlFor="profile-email"
                  className="block text-[11px] font-semibold tracking-wider text-[#1e1e1e]/35 uppercase"
                >
                  Email
                </label>
                <input
                  id="profile-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded-lg border border-[#1e1e1e]/12 bg-white px-3 py-2 text-sm text-[#1e1e1e] transition-colors duration-150 outline-none placeholder:text-[#1e1e1e]/20 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/20"
                />
                <p className="text-[11px] text-[#1e1e1e]/25">Used for email notifications.</p>
              </div>

              {accountError ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                  {accountError}
                </p>
              ) : null}

              <button
                type="button"
                onClick={() => void handleSaveAccount()}
                disabled={accountSaving}
                className="flex cursor-pointer items-center gap-2 rounded-lg bg-[#1e1e1e] px-4 py-2 text-xs font-semibold text-[#b9eb10] transition-colors duration-150 hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {accountSaving ? <Loader2 size={12} className="animate-spin" /> : null}
                {accountSaving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          )}

          {/* ── Notifications ── */}
          {activeSection === 'notifications' && (
            <div className="max-w-md space-y-5">
              {/* Master toggle */}
              <div className="flex items-center justify-between rounded-lg border border-[#1e1e1e]/8 bg-[#f9f9f9] px-4 py-3">
                <div>
                  <p className="text-[13px] font-medium text-[#1e1e1e]">Email notifications</p>
                  <p className="text-[11px] text-[#1e1e1e]/40">Receive updates via email</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={notifyEnabled}
                  onClick={() => setNotifyEnabled((v) => !v)}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#b9eb10] ${
                    notifyEnabled ? 'bg-[#1e1e1e]' : 'bg-[#d0d0d0]'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      notifyEnabled ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {/* Per-type checkboxes */}
              <div
                className={`space-y-0.5 transition-opacity duration-200 ${!notifyEnabled ? 'pointer-events-none opacity-30' : ''}`}
              >
                <p className="mb-2 text-[11px] font-semibold tracking-wider text-[#1e1e1e]/35 uppercase">
                  Notify me about
                </p>
                {ALL_NOTIFY_TYPES.map((type) => (
                  <label
                    key={type}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 transition-colors duration-150 hover:bg-[#f5f5f5]"
                  >
                    <input
                      type="checkbox"
                      checked={notifyTypes.includes(type)}
                      onChange={() => toggleNotifyType(type)}
                      disabled={!notifyEnabled}
                      className="h-4 w-4 cursor-pointer rounded border-[#1e1e1e]/20 accent-[#1e1e1e]"
                    />
                    <span className="text-[13px] text-[#1e1e1e]/65">
                      {NOTIFY_TYPE_LABELS[type]}
                    </span>
                  </label>
                ))}
              </div>

              {notifError ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                  {notifError}
                </p>
              ) : null}

              <button
                type="button"
                onClick={() => void handleSaveNotifications()}
                disabled={notifSaving}
                className="flex cursor-pointer items-center gap-2 rounded-lg bg-[#1e1e1e] px-4 py-2 text-xs font-semibold text-[#b9eb10] transition-colors duration-150 hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {notifSaving ? <Loader2 size={12} className="animate-spin" /> : null}
                {notifSaving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          )}

          {/* ── Decision Patterns ── */}
          {activeSection === 'patterns' && (
            <div className="w-full">
              <UserPatternCard />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
