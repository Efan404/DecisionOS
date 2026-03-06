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
          <p className="text-sm text-red-600">{loadError}</p>
        </section>
      </main>
    )
  }

  return (
    <main>
      <section className="mx-auto mt-8 w-full max-w-2xl space-y-6 px-6 pb-16">
        <h1 className="text-lg font-bold tracking-tight text-slate-900">Profile</h1>

        {/* Account section */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Account</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Username</label>
              <input
                type="text"
                value={profile?.username ?? ''}
                disabled
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-400"
              />
            </div>
            <div>
              <label htmlFor="email" className="mb-1 block text-xs font-medium text-slate-600">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-slate-400 focus:outline-none"
              />
            </div>
            {accountError ? <p className="text-xs text-red-600">{accountError}</p> : null}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveAccount}
                disabled={accountSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {accountSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>

        {/* Notifications section */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Notifications</h2>
          <div className="space-y-4">
            {/* Master toggle */}
            <label className="flex cursor-pointer items-center justify-between">
              <span className="text-sm text-slate-700">Enable email notifications</span>
              <button
                type="button"
                role="switch"
                aria-checked={notifyEnabled}
                onClick={() => setNotifyEnabled((v) => !v)}
                className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
                  notifyEnabled ? 'bg-slate-900' : 'bg-slate-200'
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
              <p className="text-xs font-medium text-slate-500">Notify me about:</p>
              {ALL_NOTIFY_TYPES.map((type) => (
                <label
                  key={type}
                  className={`flex cursor-pointer items-center gap-3 ${!notifyEnabled ? 'opacity-40' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={notifyTypes.includes(type)}
                    onChange={() => toggleNotifyType(type)}
                    disabled={!notifyEnabled}
                    className="h-4 w-4 rounded border-slate-300 accent-slate-900"
                  />
                  <span className="text-sm text-slate-700">{NOTIFY_TYPE_LABELS[type]}</span>
                </label>
              ))}
            </div>

            {notifError ? <p className="text-xs text-red-600">{notifError}</p> : null}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSaveNotifications}
                disabled={notifSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {notifSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
