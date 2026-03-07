import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { ScopeFreezePage } from '../ScopeFreezePage'
import { useDecisionStore } from '../../../lib/store'

describe('ScopeFreezePage smoke', () => {
  test('renders guard message when context is not ready', () => {
    useDecisionStore.setState({
      context: {
        session_id: 'session-test',
        created_at: new Date().toISOString(),
      },
    })

    render(<ScopeFreezePage />)
    expect(screen.getByText('scope.guardTitle')).toBeInTheDocument()
  })
})
