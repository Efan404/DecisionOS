import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SearchSettingsSection } from '../SearchSettingsSection'

// Mock the api module
vi.mock('../../../lib/api', () => ({
  getSearchSettings: vi.fn().mockResolvedValue({
    id: 'default',
    provider: 'hn_algolia',
    api_key_masked: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  patchSearchSettings: vi.fn().mockResolvedValue({
    id: 'default',
    provider: 'exa',
    api_key_masked: 'sk-••••key',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  testSearchProvider: vi.fn().mockResolvedValue({
    ok: true,
    result_count: 3,
    sample_titles: ['a', 'b', 'c'],
    error: null,
  }),
}))

describe('SearchSettingsSection', () => {
  it('renders provider dropdown and loads current settings', async () => {
    render(<SearchSettingsSection />)
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())
  })

  it('shows Test Connection button', async () => {
    render(<SearchSettingsSection />)
    await waitFor(() => expect(screen.getByText('settings.testConnection')).toBeInTheDocument())
  })

  it('shows success message after test connection', async () => {
    render(<SearchSettingsSection />)
    await waitFor(() => screen.getByText('settings.testConnection'))
    fireEvent.click(screen.getByText('settings.testConnection'))
    await waitFor(() => expect(screen.getByText(/3 results/)).toBeInTheDocument())
  })
})
