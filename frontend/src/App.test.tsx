import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'
import { createRecommendationClient } from './api/client'

describe('App', () => {
  it('loads mock recommendations and exposes the assessment without color alone', async () => {
    render(
      <App client={createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })} />,
    )

    expect((await screen.findAllByText('天神みんなのテーブル')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('利用しやすい').length).toBeGreaterThan(0)
    expect(screen.getAllByText('要確認').length).toBeGreaterThan(0)
    expect(screen.getAllByText('利用が難しい').length).toBeGreaterThan(0)
    expect(screen.queryByText('今日、安心して入れるお店を。')).not.toBeInTheDocument()
    expect(screen.getByLabelText('料理ジャンル')).toHaveAttribute('list', 'cuisine-options')
  })

  it('shows field-level errors using the API validation shape', async () => {
    render(
      <App client={createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })} />,
    )
    await screen.findAllByText('天神みんなのテーブル')

    fireEvent.change(screen.getByLabelText(/行きたいエリア/), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: '行けるお店を探す' }))

    await waitFor(() => {
      expect(screen.getByText('未入力')).toBeInTheDocument()
    })
  })
})
