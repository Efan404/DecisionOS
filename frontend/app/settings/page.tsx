'use client'

import { useState } from 'react'
import { AISettingsPage } from '../../components/settings/AISettingsPage'
import { SearchSettingsSection } from '../../components/settings/SearchSettingsSection'

type Tab = 'ai' | 'search'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('ai')

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <div className="mb-6 flex gap-6 border-b border-[#1e1e1e]/10">
        <button
          type="button"
          onClick={() => setActiveTab('ai')}
          className={[
            'pb-3 text-sm font-medium transition',
            activeTab === 'ai'
              ? 'border-b-2 border-[#b9eb10] text-[#1e1e1e]'
              : 'text-[#1e1e1e]/50 hover:text-[#1e1e1e]/70',
          ].join(' ')}
        >
          AI Provider
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('search')}
          className={[
            'pb-3 text-sm font-medium transition',
            activeTab === 'search'
              ? 'border-b-2 border-[#b9eb10] text-[#1e1e1e]'
              : 'text-[#1e1e1e]/50 hover:text-[#1e1e1e]/70',
          ].join(' ')}
        >
          Search Provider
        </button>
      </div>

      {activeTab === 'ai' && <AISettingsPage />}
      {activeTab === 'search' && (
        <main>
          <SearchSettingsSection />
        </main>
      )}
    </div>
  )
}
