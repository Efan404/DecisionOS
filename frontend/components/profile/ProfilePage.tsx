'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { ApiError, getProfile, patchProfile, type UserProfile } from '../../lib/api'

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  news_match: 'News matches',
  cross_idea_insight: 'Cross-idea insights',
  pattern_learned: 'Pattern updates',
}

const ALL_NOTIFY_TYPES = ['news_match', 'cross_idea_insight', 'pattern_learned']

export function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Account section state
  const [email, setEmail] = useState('')
  const [accountSaving, setAccountSaving] = useState(false)
  const [accountError, setAccountError] = useState<string | null>(null)

  // Notifications section state
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
      <main>
        <section className="mx-auto mt-8 max-w-2xl px-6">
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm text-red-700">{loadError}</p>
          </div>
        </section>
      </main>
    )
  }

  return (
    <main>
      <section className="mx-auto mt-8 w-full max-w-2xl space-y-6 px-6 pb-16">
        <h1 className="text-lg font-bold tracking-tight text-[#1e1e1e]">Profile</h1>

        {/* Account section */}
        <div className="rounded-xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-[#1e1e1e]">Account</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-[#1e1e1e]/50">Username</label>
              <input
                type="text"
                value={profile?.username ?? ''}
                disabled
                className="w-full rounded-xl border border-[#1e1e1e]/10 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e]/40"
              />
            </div>
            <div>
              <label htmlFor="email" className="mb-1 block text-xs font-medium text-[#1e1e1e]/50">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/20"
              />
            </div>
            {accountError ? <p className="text-xs text-red-600">{accountError}</p> : null}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveAccount}
                disabled={accountSaving}
                className="flex items-center gap-2 rounded-xl bg-[#1e1e1e] px-4 py-2 text-xs font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {accountSaving ? (
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#b9eb10]/40 border-t-[#b9eb10]" />
                ) : null}
                {accountSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>

        {/* Notifications section */}
        <div className="rounded-xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-[#1e1e1e]">Notifications</h2>
          <div className="space-y-4">
            {/* Master toggle */}
            <label className="flex cursor-pointer items-center justify-between">
              <span className="text-sm text-[#1e1e1e]/70">Enable email notifications</span>
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
            </label>

            {/* Per-type checkboxes */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-[#1e1e1e]/40">Notify me about:</p>
              {ALL_NOTIFY_TYPES.map((type) => (
                <label
                  key={type}
                  className={`flex cursor-pointer items-center gap-3 transition-opacity ${!notifyEnabled ? 'opacity-40' : ''}`}
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
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveNotifications}
                disabled={notifSaving}
                className="flex items-center gap-2 rounded-xl bg-[#1e1e1e] px-4 py-2 text-xs font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {notifSaving ? (
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#b9eb10]/40 border-t-[#b9eb10]" />
                ) : null}
                {notifSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
