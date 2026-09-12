import { useEffect, useState } from 'react'
import {
  AdvancedMarker,
  APIProvider,
  InfoWindow,
  Map,
  useAdvancedMarkerRef,
  useMap,
} from '@vis.gl/react-google-maps'
import type { RestaurantRecommendation } from '../api/types'
import { statusMeta } from '../ui/accessibility'
import { PlaceDetailsPanel } from './PlaceDetailsPanel'

interface MapPanelProps {
  recommendations: RestaurantRecommendation[]
  selectedPlaceId: string | null
  onSelect: (placeId: string | null) => void
  apiKey?: string
  mapId?: string
}

const FUKUOKA_CENTER = { lat: 33.5902, lng: 130.4017 }

function toLatLng(recommendation: RestaurantRecommendation) {
  return {
    lat: recommendation.location.latitude,
    lng: recommendation.location.longitude,
  }
}

function MapViewport({
  recommendations,
  selectedPlaceId,
}: Pick<MapPanelProps, 'recommendations' | 'selectedPlaceId'>) {
  const map = useMap()

  useEffect(() => {
    if (!map || recommendations.length === 0) return

    if (recommendations.length === 1) {
      map.setCenter(toLatLng(recommendations[0]))
      map.setZoom(16)
      return
    }

    const bounds = recommendations.reduce(
      (current, recommendation) => ({
        north: Math.max(current.north, recommendation.location.latitude),
        south: Math.min(current.south, recommendation.location.latitude),
        east: Math.max(current.east, recommendation.location.longitude),
        west: Math.min(current.west, recommendation.location.longitude),
      }),
      {
        north: -90,
        south: 90,
        east: -180,
        west: 180,
      },
    )
    map.fitBounds(bounds, 56)
  }, [map, recommendations])

  useEffect(() => {
    if (!map || !selectedPlaceId) return

    const selected = recommendations.find(
      (recommendation) => recommendation.place_id === selectedPlaceId,
    )
    if (selected) map.panTo(toLatLng(selected))
  }, [map, recommendations, selectedPlaceId])

  return null
}

interface RestaurantMarkerProps {
  recommendation: RestaurantRecommendation
  isSelected: boolean
  onSelect: MapPanelProps['onSelect']
}

function RestaurantMarker({
  recommendation,
  isSelected,
  onSelect,
}: RestaurantMarkerProps) {
  const [markerRef, marker] = useAdvancedMarkerRef()
  const status = statusMeta[recommendation.accessibility.status]

  return (
    <>
      <AdvancedMarker
        ref={markerRef}
        position={toLatLng(recommendation)}
        title={`${recommendation.name}、${status.label}${isSelected ? '、選択中' : ''}`}
        zIndex={isSelected ? 10 : recommendation.rank}
        onClick={() => onSelect(recommendation.place_id)}
      >
        <span
          className={`google-map-marker status-${recommendation.accessibility.status}${isSelected ? ' is-selected' : ''}`}
          aria-hidden="true"
        >
          {status.symbol}
        </span>
      </AdvancedMarker>

      {isSelected && marker && (
        <InfoWindow anchor={marker} onCloseClick={() => onSelect(null)}>
          <article className="map-info-window" aria-label={`${recommendation.name}の情報`}>
            <span className={`map-info-status status-${recommendation.accessibility.status}`}>
              <b aria-hidden="true">{status.symbol}</b>
              {status.label}
            </span>
            <h3>{recommendation.name}</h3>
            <p className="map-info-address">{recommendation.address}</p>
            <p>{recommendation.recommendation_reason}</p>
            <a href={recommendation.maps_url} target="_blank" rel="noreferrer">
              Google マップで確認
              <span aria-hidden="true"> ↗</span>
            </a>
          </article>
        </InfoWindow>
      )}
    </>
  )
}

function MapUnavailable({ reason }: { reason: 'configuration' | 'load-error' }) {
  return (
    <div className="map-unavailable" role={reason === 'load-error' ? 'alert' : 'status'}>
      <span aria-hidden="true">!</span>
      <div>
        <strong>地図を読み込めません</strong>
        <p>
          {reason === 'configuration'
            ? 'Google Mapsの設定がありません。店舗情報は候補一覧から確認できます。'
            : 'Google Mapsの読み込みに失敗しました。店舗情報は候補一覧から確認できます。'}
        </p>
      </div>
    </div>
  )
}

export function MapPanel({
  recommendations,
  selectedPlaceId,
  onSelect,
  apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY,
  mapId = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID,
}: MapPanelProps) {
  const [hasLoadError, setHasLoadError] = useState(false)
  const hasConfiguration = Boolean(apiKey?.trim() && mapId?.trim())
  const initialCenter = recommendations[0]
    ? toLatLng(recommendations[0])
    : FUKUOKA_CENTER
  const selected = recommendations.find(
    (recommendation) => recommendation.place_id === selectedPlaceId,
  )

  return (
    <section className="map-panel" aria-label="推薦店舗の地図">
      <div className="map-toolbar">
        <div>
          <strong>福岡市中心部</strong>
        </div>
        <div className="legend" aria-label="入店可否の凡例">
          {Object.entries(statusMeta).map(([key, value]) => (
            <span key={key} className={`legend-${key}`}>
              <b aria-hidden="true">{value.symbol}</b>{value.shortLabel}
            </span>
          ))}
        </div>
      </div>

      {!hasConfiguration ? (
        <div className="map-canvas">
          <MapUnavailable reason="configuration" />
        </div>
      ) : hasLoadError ? (
        <div className="map-canvas">
          <MapUnavailable reason="load-error" />
        </div>
      ) : (
        <APIProvider
          apiKey={apiKey!}
          language="ja"
          region="JP"
          onError={() => setHasLoadError(true)}
        >
          <div className="map-canvas">
            <Map
              mapId={mapId}
              defaultCenter={initialCenter}
              defaultZoom={13}
              maxZoom={18}
              style={{ width: '100%', height: '100%' }}
              gestureHandling="cooperative"
              mapTypeControl={false}
              streetViewControl={false}
              reuseMaps
            >
              <MapViewport
                recommendations={recommendations}
                selectedPlaceId={selectedPlaceId}
              />
              {recommendations.map((recommendation) => (
                <RestaurantMarker
                  key={recommendation.place_id}
                  recommendation={recommendation}
                  isSelected={recommendation.place_id === selectedPlaceId}
                  onSelect={onSelect}
                />
              ))}
            </Map>
          </div>
          {selected && (
            <PlaceDetailsPanel
              key={selected.place_id}
              recommendation={selected}
            />
          )}
        </APIProvider>
      )}
    </section>
  )
}
