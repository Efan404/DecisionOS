import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { NotificationBell } from '../NotificationBell'

// Mock the api module
vi.mock('../../../lib/api', () => ({
  getNotifications: vi.fn().mockResolvedValue([
    {
      id: 'n1',
      type: 'market_insight',
      title: 'Market insight ready',
      body: 'Analysis complete',
      read_at: null,
      created_at: '2026-01-01T00:00:00Z',
      metadata: { action_url: '/insights?idea_id=abc' },
    },
    {
      id: 'n2',
      type: 'news_match',
      title: 'Plain notification',
      body: 'No link',
      read_at: null,
      created_at: '2026-01-01T00:00:00Z',
      metadata: {},
    },
  ]),
  dismissNotification: vi.fn().mockResolvedValue(undefined),
}))

describe('NotificationBell', () => {
  it('renders notification with action_url as a clickable link', async () => {
    render(<NotificationBell />)
    // Open the bell
    const bell = screen.getByRole('button', { name: /notifications/i })
    fireEvent.click(bell)

    // Wait for notifications to load
    const link = await screen.findByRole('link', { name: /market insight ready/i })
    expect(link).toHaveAttribute('href', '/insights?idea_id=abc')
  })

  it('renders notification without action_url as plain text', async () => {
    render(<NotificationBell />)
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }))

    const plainTitle = await screen.findByText('Plain notification')
    // Should be a <p> not an <a>
    expect(plainTitle.tagName).toBe('P')
  })
})
