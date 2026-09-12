import type { PropsWithChildren, ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { createRecommendationClient } from './api/client'

vi.mock('@vis.gl/react-google-maps', () => ({
  APIProvider: ({ children }: PropsWithChildren) => <>{children}</>,
  Map: ({ children }: PropsWithChildren) => <div data-testid="google-map">{children}</div>,
  AdvancedMarker: ({
    children,
    title,
    onClick,
  }: {
    children: ReactNode
    title: string
    onClick: () => void
  }) => (
    <button type="button" aria-label={title} onClick={onClick}>
      {children}
    </button>
  ),
  InfoWindow: ({ children }: PropsWithChildren) => (
    <div data-testid="info-window">{children}</div>
  ),
  useAdvancedMarkerRef: () => [vi.fn(), {}],
  useMap: () => null,
  useMapsLibrary: () => null,
}))

describe('App', () => {
  it('loads mock recommendations and exposes the assessment without color alone', async () => {
    render(
      <App client={createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })} />,
    )

    expect((await screen.findAllByText('リタの農園')).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { level: 1, name: 'wishlan' })).toBeInTheDocument()
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
    await screen.findAllByText('リタの農園')

    fireEvent.change(screen.getByLabelText(/行きたいエリア/), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: '行けるお店を探す' }))

    await waitFor(() => {
      expect(screen.getByText('未入力')).toBeInTheDocument()
    })
  })

  it('opens the matching map info window when a recommendation card is selected', async () => {
    render(
      <App
        client={createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })}
        mapsApiKey="test-api-key"
        mapsMapId="test-map-id"
      />,
    )

    await screen.findAllByText('リタの農園')
    const restaurantCard = screen.getByRole('button', {
      name: 'パックスロマーナを地図で選択',
    })
    fireEvent.click(restaurantCard)

    expect(restaurantCard).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('パックスロマーナの情報')).toBeInTheDocument()
    expect(screen.queryByLabelText('リタの農園の情報')).not.toBeInTheDocument()
  })
})
