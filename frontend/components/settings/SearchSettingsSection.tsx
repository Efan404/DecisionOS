'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useTranslations } from 'next-intl'

import { getSearchSettings, patchSearchSettings, testSearchProvider } from '../../lib/api'
import type {
  SearchProviderConfig,
  SearchProviderKind,
  SearchSettingsDetail,
  TestSearchProviderResponse,
} from '../../lib/schemas'

const PROVIDER_LABELS: Record<SearchProviderKind, string> = {
  exa: 'Exa',
  tavily: 'Tavily',
  hn_algolia: 'HN Algolia (free, no key needed)',
}

const PROVIDER_DEFAULTS: Record<SearchProviderKind, { id: string; name: string }> = {
  exa: { id: 'exa', name: 'Exa' },
  tavily: { id: 'tavily', name: 'Tavily' },
  hn_algolia: { id: 'hn_algolia', name: 'HN Algolia' },
}

/** Build the full providers array with exactly one provider enabled. */
function buildProvidersPayload(
  settings: SearchSettingsDetail,
  activeKind: SearchProviderKind,
  newApiKey: string
): SearchProviderConfig[] {
  const existingByKind = new Map(settings.providers.map((p) => [p.kind, p]))
  const defaults = PROVIDER_DEFAULTS[activeKind]
  const activeConfig: SearchProviderConfig = {
    ...(existingByKind.get(activeKind) ?? {
      id: defaults.id,
      name: defaults.name,
      kind: activeKind,
      enabled: true,
    }),
    kind: activeKind,
    enabled: true,
    api_key: newApiKey.trim() || (existingByKind.get(activeKind)?.api_key ?? null),
  }
  const others = settings.providers
    .filter((p) => p.kind !== activeKind)
    .map((p) => ({ ...p, enabled: false }))
  return [activeConfig, ...others]
}

export function SearchSettingsSection() {
  const t = useTranslations('settings')
  const tCommon = useTranslations('common')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [settings, setSettings] = useState<SearchSettingsDetail | null>(null)
  const [provider, setProvider] = useState<SearchProviderKind>('hn_algolia')
  const [apiKey, setApiKey] = useState('')
  const [testResult, setTestResult] = useState<TestSearchProviderResponse | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  useEffect(() => {
    const run = async () => {
      try {
        const data = await getSearchSettings()
        setSettings(data)
        // Find the enabled provider; fall back to the first one if none is explicitly enabled.
        const active = data.providers.find((p) => p.enabled) ?? data.providers[0]
        if (active) setProvider(active.kind)
        // api_key is masked on read — don't prefill the input
        setApiKey('')
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load search settings.'
        toast.error(message)
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [])

  const onSave = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const updated = await patchSearchSettings({
        providers: buildProvidersPayload(settings, provider, apiKey),
      })
      setSettings(updated)
      setApiKey('')
      toast.success('Search settings saved.')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save search settings.'
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const onTestConnection = async () => {
    if (!settings) return
    setTesting(true)
    setTestResult(null)
    setTestError(null)
    try {
      const existingConfig = settings.providers.find((p) => p.kind === provider)
      const defaults = PROVIDER_DEFAULTS[provider]
      const providerConfig: SearchProviderConfig = {
        ...(existingConfig ?? {
          id: defaults.id,
          name: defaults.name,
          kind: provider,
          enabled: true,
        }),
        kind: provider,
        enabled: true,
        api_key: apiKey.trim() || (existingConfig?.api_key ?? null),
      }
      const result = await testSearchProvider({ provider: providerConfig })
      setTestResult(result)
      if (result.ok) {
        toast.success(
          `Connection OK — ${result.sample_results.length} results found (${result.latency_ms}ms).`
        )
      } else {
        toast.error(result.message ?? 'Connection test failed.')
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection test failed.'
      setTestError(message)
      toast.error(message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <section className="rounded-xl border border-[#1e1e1e]/8 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-[#1e1e1e]">{t('searchProvider')}</h2>
      <p className="mt-1 text-sm text-[#1e1e1e]/50">
        Configure the search provider used for market intelligence.
        {settings ? (
          <span className="ml-2 text-xs text-[#1e1e1e]/35">Updated: {settings.updated_at}</span>
        ) : null}
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-[#1e1e1e]/40">Loading search settings...</p>
      ) : (
        <div className="mt-5 space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block text-[#1e1e1e]/60">Provider</span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.currentTarget.value as SearchProviderKind)
                setApiKey('')
                setTestResult(null)
                setTestError(null)
              }}
              className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e] transition outline-none focus:ring-2 focus:ring-[#b9eb10]"
            >
              {(Object.keys(PROVIDER_LABELS) as SearchProviderKind[]).map((kind) => (
                <option key={kind} value={kind}>
                  {PROVIDER_LABELS[kind]}
                </option>
              ))}
            </select>
          </label>

          {provider !== 'hn_algolia' && (
            <label className="block text-sm">
              <span className="mb-1 block text-[#1e1e1e]/60">
                API Key
                {settings?.providers.find((p) => p.kind === provider)?.api_key ? (
                  <span className="ml-2 text-[#1e1e1e]/35">
                    (current: {settings.providers.find((p) => p.kind === provider)?.api_key})
                  </span>
                ) : null}
              </span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.currentTarget.value)}
                placeholder="sk-..."
                className="w-full rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e] transition outline-none focus:ring-2 focus:ring-[#b9eb10]"
              />
            </label>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving || !settings}
              className="rounded-xl bg-[#1e1e1e] px-4 py-2 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? tCommon('saving') : tCommon('save')}
            </button>
            <button
              type="button"
              onClick={() => void onTestConnection()}
              disabled={testing || !settings}
              className="rounded-xl border border-[#1e1e1e]/15 bg-[#f5f5f5] px-4 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#ebebeb] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {testing ? t('testing') : t('testConnection')}
            </button>
          </div>

          {testResult !== null && testResult.ok && (
            <p className="text-sm text-green-700">
              Connection OK &mdash; {testResult.sample_results.length} results found (
              {testResult.latency_ms}ms)
            </p>
          )}
          {testResult !== null && !testResult.ok && (
            <p className="text-sm text-red-600">
              Error: {testResult.message ?? 'Connection test failed.'}
            </p>
          )}
          {testError !== null && <p className="text-sm text-red-600">Error: {testError}</p>}
        </div>
      )}
    </section>
  )
}
