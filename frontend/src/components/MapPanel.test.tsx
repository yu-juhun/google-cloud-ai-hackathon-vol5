import type { PropsWithChildren, ReactNode } from 'react'
import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockRecommendations } from '../api/mockData'
import { MapPanel } from './MapPanel'

const mapMock = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  panTo: vi.fn(),
  setCenter: vi.fn(),
  setZoom: vi.fn(),
}))

vi.mock('@vis.gl/react-google-maps', () => ({
  APIProvider: ({
    children,
    onError,
  }: PropsWithChildren<{ onError?: (error: unknown) => void }>) => (
    <div data-testid="maps-api-provider">
      <button type="button" onClick={() => onError?.(new Error('load failed'))}>
        Google Mapsの読込失敗を発生
      </button>
      {children}
    </div>
  ),
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
  InfoWindow: ({
    children,
    onCloseClick,
  }: PropsWithChildren<{ onCloseClick: () => void }>) => (
    <div data-testid="info-window">
      <button type="button" onClick={onCloseClick}>
        店舗情報を閉じる
      </button>
      {children}
    </div>
  ),
  useAdvancedMarkerRef: () => [vi.fn(), {}],
  useMap: () => mapMock,
  useMapsLibrary: () => null,
}))

function MapHarness() {
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(
    mockRecommendations[0].place_id,
  )

  return (
    <MapPanel
      recommendations={mockRecommendations}
      selectedPlaceId={selectedPlaceId}
      onSelect={setSelectedPlaceId}
      apiKey="test-api-key"
      mapId="test-map-id"
    />
  )
}

function ResultsHarness() {
  const [recommendations, setRecommendations] = useState(mockRecommendations)

  return (
    <>
      <button
        type="button"
        onClick={() => setRecommendations(mockRecommendations.slice(1))}
      >
        検索結果を更新
      </button>
      <MapPanel
        recommendations={recommendations}
        selectedPlaceId={null}
        onSelect={vi.fn()}
        apiKey="test-api-key"
        mapId="test-map-id"
      />
    </>
  )
}

describe('MapPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    { apiKey: '', mapId: 'DEMO_MAP_ID' },
    { apiKey: 'test-api-key', mapId: '' },
  ])('shows an unavailable state when the Google Maps configuration is missing', ({
    apiKey,
    mapId,
  }) => {
    render(
      <MapPanel
        recommendations={mockRecommendations}
        selectedPlaceId={null}
        onSelect={vi.fn()}
        apiKey={apiKey}
        mapId={mapId}
      />,
    )

    expect(screen.getByText('地図を読み込めません')).toBeInTheDocument()
    expect(screen.queryByTestId('google-map')).not.toBeInTheDocument()
  })

  it('renders recommendation markers and keeps marker and info-window selection in sync', async () => {
    render(<MapHarness />)

    expect(screen.getByTestId('google-map')).toBeInTheDocument()
    for (const recommendation of mockRecommendations) {
      expect(
        screen.getByRole('button', { name: new RegExp(recommendation.name) }),
      ).toBeInTheDocument()
    }

    expect(screen.getByLabelText('リタの農園の情報')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /パックスロマーナ/ }))
    expect(screen.getByLabelText('パックスロマーナの情報')).toBeInTheDocument()
    expect(screen.queryByLabelText('リタの農園の情報')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '店舗情報を閉じる' }))
    expect(screen.queryByTestId('info-window')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(mapMock.fitBounds).toHaveBeenCalledWith(
        {
          north: 33.6033538,
          south: 33.5901856,
          east: 130.3993869,
          west: 130.3929018,
        },
        56,
      )
      expect(mapMock.panTo).toHaveBeenCalledWith({ lat: 33.5936495, lng: 130.3957651 })
    })
  })

  it('uses a close zoom for one recommendation', async () => {
    const recommendation = mockRecommendations[0]
    render(
      <MapPanel
        recommendations={[recommendation]}
        selectedPlaceId={recommendation.place_id}
        onSelect={vi.fn()}
        apiKey="test-api-key"
        mapId="test-map-id"
      />,
    )

    await waitFor(() => {
      expect(mapMock.setCenter).toHaveBeenCalledWith({ lat: 33.6033538, lng: 130.3993869 })
      expect(mapMock.setZoom).toHaveBeenCalledWith(16)
    })
  })

  it('fits the map to new recommendation results', async () => {
    render(<ResultsHarness />)
    fireEvent.click(screen.getByRole('button', { name: '検索結果を更新' }))

    await waitFor(() => {
      expect(mapMock.fitBounds).toHaveBeenLastCalledWith(
        {
          north: 33.5936495,
          south: 33.5901856,
          east: 130.3957651,
          west: 130.3929018,
        },
        56,
      )
    })
  })

  it('falls back when the Maps JavaScript API fails to load', () => {
    render(<MapHarness />)

    fireEvent.click(
      screen.getByRole('button', { name: 'Google Mapsの読込失敗を発生' }),
    )
    expect(screen.getByRole('alert')).toHaveTextContent('地図を読み込めません')
    expect(screen.queryByTestId('google-map')).not.toBeInTheDocument()
  })
})
