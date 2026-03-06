'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { UserPatternCard } from '../insights/UserPatternCard'
import { getAiSettings, patchAiSettings, testAiProvider } from '../../lib/api'
import type { AIProviderConfig, AIProviderKind } from '../../lib/schemas'

const DEFAULT_PROVIDER: AIProviderConfig = {
  id: '',
  name: '',
  kind: 'generic_json',
  base_url: '',
  api_key: '',
  model: '',
  enabled: false,
  timeout_seconds: 20,
  temperature: 0.2,
}

export function AISettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [providers, setProviders] = useState<AIProviderConfig[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, string>>({})
  const [testingIds, setTestingIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const run = async () => {
      try {
        const settings = await getAiSettings()
        setProviders(
          settings.providers.map((provider) => ({
            ...provider,
            api_key: provider.api_key ?? '',
            model: provider.model ?? '',
          }))
        )
        setUpdatedAt(settings.updated_at)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load AI settings.'
        toast.error(message)
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [])

  const updateProvider = (index: number, patch: Partial<AIProviderConfig>) => {
    setProviders((prev) =>
      prev.map((provider, providerIndex) =>
        providerIndex === index ? { ...provider, ...patch } : provider
      )
    )
  }

  // Radio-button semantics: enabling one disables all others
  const setEnabledProvider = (index: number) => {
    setProviders((prev) =>
      prev.map((provider, providerIndex) => ({
        ...provider,
        enabled: providerIndex === index,
      }))
    )
  }

  const addProvider = () => {
    const suffix = providers.length + 1
    setProviders((prev) => [
      ...prev,
      {
        ...DEFAULT_PROVIDER,
        id: `provider_${suffix}`,
        name: `Provider ${suffix}`,
      },
    ])
  }

  const removeProvider = (index: number) => {
    setProviders((prev) => prev.filter((_, providerIndex) => providerIndex !== index))
  }

  const onSave = async () => {
    const cleanedProviders = providers.map((provider) => ({
      ...provider,
      id: provider.id.trim(),
      name: provider.name.trim(),
      base_url: provider.base_url.trim(),
      api_key: provider.api_key?.trim() || undefined,
      model: provider.model?.trim() || undefined,
    }))

    const hasEmptyRequired = cleanedProviders.some(
      (provider) => !provider.id || !provider.name || !provider.base_url
    )
    if (hasEmptyRequired) {
      toast.error('Each provider must include id, name, and base URL.')
      return
    }
    const cleanedProviderIdSet = new Set(cleanedProviders.map((provider) => provider.id))
    if (cleanedProviderIdSet.size !== cleanedProviders.length) {
      toast.error('Provider IDs must be unique.')
      return
    }

    setSaving(true)
    try {
      const saved = await patchAiSettings({ providers: cleanedProviders })
      setUpdatedAt(saved.updated_at)
      toast.success('AI settings saved.')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save AI settings.'
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const onTestProvider = async (provider: AIProviderConfig) => {
    const providerId = provider.id.trim() || '(temporary-provider)'
    setTestingIds((prev) => ({ ...prev, [providerId]: true }))
    setTestResults((prev) => ({ ...prev, [providerId]: '' }))

    try {
      const result = await testAiProvider({
        provider: {
          ...provider,
          id: provider.id.trim(),
          name: provider.name.trim(),
          base_url: provider.base_url.trim(),
          api_key: provider.api_key?.trim() || undefined,
          model: provider.model?.trim() || undefined,
        },
      })
      const statusLabel = result.ok ? 'OK' : 'FAILED'
      setTestResults((prev) => ({
        ...prev,
        [providerId]: `${statusLabel} · ${result.latency_ms}ms · ${result.message}`,
      }))
      if (result.ok) {
        toast.success(`Provider ${providerId} is reachable.`)
      } else {
        toast.error(`Provider ${providerId} test failed.`)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Provider test failed.'
      setTestResults((prev) => ({ ...prev, [providerId]: `FAILED · ${message}` }))
      toast.error(message)
    } finally {
      setTestingIds((prev) => ({ ...prev, [providerId]: false }))
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <section className="rounded-2xl border border-[#1e1e1e]/10 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-[#1e1e1e]">AI Settings</h1>
            <p className="mt-1 text-sm text-[#1e1e1e]/50">
              Configure your AI provider. Exactly one provider can be active at a time.
            </p>
          </div>
          <div className="text-xs text-[#1e1e1e]/35">
            {updatedAt ? `Updated: ${updatedAt}` : 'Not saved yet'}
          </div>
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-[#1e1e1e]/40">Loading AI settings...</p>
        ) : (
          <>
            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-[0.15em] text-[#1e1e1e]/50 uppercase">
                  Providers
                </h2>
                <button
                  type="button"
                  onClick={addProvider}
                  className="rounded-xl border border-[#1e1e1e]/15 bg-white px-3 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
                >
                  Add Provider
                </button>
              </div>

              {providers.length === 0 ? (
                <p className="rounded-xl border border-dashed border-[#1e1e1e]/15 p-4 text-sm text-[#1e1e1e]/40">
                  No providers configured. Add one to enable AI generation.
                </p>
              ) : null}

              <div className="space-y-3">
                {providers.map((provider, index) => {
                  const isActive = provider.enabled
                  const providerKey = `${provider.id}-${index}`
                  const testKey = provider.id.trim() || '(temporary-provider)'
                  return (
                    <article
                      key={providerKey}
                      className="rounded-xl border-2 p-4 transition-colors"
                      style={{
                        borderColor: isActive ? '#b9eb10' : '#1e1e1e1a',
                        background: isActive ? '#1e1e1e' : '#ffffff',
                      }}
                    >
                      <div className="mb-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className="rounded-full px-2.5 py-0.5 text-xs font-bold"
                            style={{
                              background: isActive ? '#b9eb10' : '#1e1e1e0f',
                              color: isActive ? '#1e1e1e' : '#1e1e1e66',
                            }}
                          >
                            {isActive ? 'Active' : 'Inactive'}
                          </span>
                          <span
                            className="text-sm font-medium"
                            style={{ color: isActive ? '#ffffff' : '#1e1e1e' }}
                          >
                            {provider.name || '(unnamed)'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {!isActive && (
                            <button
                              type="button"
                              onClick={() => setEnabledProvider(index)}
                              className="rounded-lg border border-[#b9eb10] bg-[#b9eb10]/10 px-3 py-1.5 text-xs font-medium text-[#4a7300] transition hover:bg-[#b9eb10]/20"
                            >
                              Set Active
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => void onTestProvider(provider)}
                            disabled={Boolean(testingIds[testKey])}
                            className="rounded-lg border border-[#1e1e1e]/15 px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-60"
                            style={{
                              background: isActive ? '#ffffff15' : '#f5f5f5',
                              color: isActive ? '#ffffff' : '#1e1e1e99',
                            }}
                          >
                            {testingIds[testKey] ? 'Testing...' : 'Test'}
                          </button>
                          <button
                            type="button"
                            onClick={() => removeProvider(index)}
                            className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-100"
                          >
                            Remove
                          </button>
                        </div>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        {[
                          { label: 'Provider ID', key: 'id', type: 'text', value: provider.id },
                          {
                            label: 'Display Name',
                            key: 'name',
                            type: 'text',
                            value: provider.name,
                          },
                          {
                            label: 'Base URL',
                            key: 'base_url',
                            type: 'text',
                            value: provider.base_url,
                            placeholder: 'https://api.openai.com/v1',
                          },
                          {
                            label: 'API Key (optional)',
                            key: 'api_key',
                            type: 'password',
                            value: provider.api_key ?? '',
                          },
                          {
                            label: 'Model (optional)',
                            key: 'model',
                            type: 'text',
                            value: provider.model ?? '',
                          },
                          {
                            label: 'Timeout Seconds',
                            key: 'timeout_seconds',
                            type: 'number',
                            value: provider.timeout_seconds,
                          },
                          {
                            label: 'Temperature',
                            key: 'temperature',
                            type: 'number',
                            value: provider.temperature,
                          },
                        ].map(({ label, key, type, value, placeholder }) =>
                          key === 'kind' ? null : (
                            <label key={key} className="text-sm">
                              <span
                                className="mb-1 block"
                                style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
                              >
                                {label}
                              </span>
                              <input
                                type={type}
                                min={
                                  key === 'timeout_seconds'
                                    ? 1
                                    : key === 'temperature'
                                      ? 0
                                      : undefined
                                }
                                max={
                                  key === 'timeout_seconds'
                                    ? 120
                                    : key === 'temperature'
                                      ? 2
                                      : undefined
                                }
                                step={
                                  key === 'temperature'
                                    ? 0.1
                                    : key === 'timeout_seconds'
                                      ? 1
                                      : undefined
                                }
                                value={value}
                                placeholder={placeholder}
                                onChange={(event) =>
                                  updateProvider(index, {
                                    [key]:
                                      type === 'number'
                                        ? Number(event.currentTarget.value) ||
                                          (key === 'temperature' ? 0.2 : 20)
                                        : event.currentTarget.value,
                                  })
                                }
                                className="w-full rounded-xl border px-3 py-2 text-sm transition outline-none focus:ring-2"
                                style={{
                                  background: isActive ? '#ffffff0f' : '#f5f5f5',
                                  borderColor: isActive ? '#ffffff22' : '#1e1e1e18',
                                  color: isActive ? '#ffffff' : '#1e1e1e',
                                }}
                              />
                            </label>
                          )
                        )}
                        <label className="text-sm">
                          <span
                            className="mb-1 block"
                            style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
                          >
                            Provider Kind
                          </span>
                          <select
                            value={provider.kind}
                            onChange={(event) =>
                              updateProvider(index, {
                                kind: event.currentTarget.value as AIProviderKind,
                              })
                            }
                            className="w-full rounded-xl border px-3 py-2 text-sm transition outline-none"
                            style={{
                              background: isActive ? '#ffffff0f' : '#f5f5f5',
                              borderColor: isActive ? '#ffffff22' : '#1e1e1e18',
                              color: isActive ? '#ffffff' : '#1e1e1e',
                            }}
                          >
                            <option value="generic_json">generic_json</option>
                            <option value="openai_compatible">openai_compatible</option>
                          </select>
                        </label>
                      </div>

                      {testResults[testKey] ? (
                        <p
                          className="mt-3 text-xs"
                          style={{ color: isActive ? '#ffffff88' : '#1e1e1e66' }}
                        >
                          {testResults[testKey]}
                        </p>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => void onSave()}
                disabled={saving}
                className="rounded-xl bg-[#1e1e1e] px-5 py-2.5 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? 'Saving...' : 'Save AI Settings'}
              </button>
            </div>
          </>
        )}
      </section>

      <section className="mt-6">
        <UserPatternCard />
      </section>
    </main>
  )
}
