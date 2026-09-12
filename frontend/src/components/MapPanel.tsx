import type { RestaurantRecommendation } from '../api/types'
import { statusMeta } from '../ui/accessibility'

interface MapPanelProps {
  recommendations: RestaurantRecommendation[]
  selectedPlaceId: string | null
  onSelect: (placeId: string) => void
}

const LATITUDE_RANGE = { min: 33.58, max: 33.596 }
const LONGITUDE_RANGE = { min: 130.388, max: 130.426 }

function markerPosition(recommendation: RestaurantRecommendation) {
  const x =
    ((recommendation.location.longitude - LONGITUDE_RANGE.min) /
      (LONGITUDE_RANGE.max - LONGITUDE_RANGE.min)) *
    100
  const y =
    (1 -
      (recommendation.location.latitude - LATITUDE_RANGE.min) /
        (LATITUDE_RANGE.max - LATITUDE_RANGE.min)) *
    100

  return {
    left: `${Math.min(92, Math.max(8, x))}%`,
    top: `${Math.min(86, Math.max(12, y))}%`,
  }
}

export function MapPanel({
  recommendations,
  selectedPlaceId,
  onSelect,
}: MapPanelProps) {
  const selected = recommendations.find(
    (recommendation) => recommendation.place_id === selectedPlaceId,
  )

  return (
    <section className="map-panel" aria-label="推薦店舗のデモ地図">
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

      <div className="map-canvas">
        <span className="river river-one" />
        <span className="river river-two" />
        <span className="road road-one" />
        <span className="road road-two" />
        <span className="road road-three" />
        <span className="district district-tenjin">天神</span>
        <span className="district district-hakata">博多</span>
        <span className="district district-daimyo">大名</span>

        {recommendations.map((recommendation) => {
          const meta = statusMeta[recommendation.accessibility.status]
          const isSelected = recommendation.place_id === selectedPlaceId
          return (
            <button
              type="button"
              key={recommendation.place_id}
              className={`map-marker status-${recommendation.accessibility.status}${isSelected ? ' is-selected' : ''}`}
              style={markerPosition(recommendation)}
              onClick={() => onSelect(recommendation.place_id)}
              aria-label={`${recommendation.name}、${meta.label}`}
              aria-pressed={isSelected}
            >
              <span aria-hidden="true">{meta.symbol}</span>
            </button>
          )
        })}

        {selected && (
          <div className="map-popover" role="status">
            <span className={`popover-symbol status-${selected.accessibility.status}`}>
              {statusMeta[selected.accessibility.status].symbol}
            </span>
            <span>
              <b>{selected.name}</b>
              <small>{statusMeta[selected.accessibility.status].label}</small>
            </span>
          </div>
        )}

        <span className="mock-map-note">座標確認用の簡易地図</span>
      </div>
    </section>
  )
}
