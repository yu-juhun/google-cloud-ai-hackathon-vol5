import type { RestaurantRecommendation } from '../api/types'
import {
  conditionLabel,
  confidenceLabel,
  resultSymbol,
  statusMeta,
} from '../ui/accessibility'

interface RecommendationCardProps {
  recommendation: RestaurantRecommendation
  isSelected: boolean
  onSelect: () => void
}

export function RecommendationCard({
  recommendation,
  isSelected,
  onSelect,
}: RecommendationCardProps) {
  const { accessibility } = recommendation
  const status = statusMeta[accessibility.status]

  return (
    <article
      className={`recommendation-card status-${accessibility.status}${isSelected ? ' is-selected' : ''}`}
    >
      <button
        className="card-select"
        type="button"
        onClick={onSelect}
        aria-label={`${recommendation.name}を地図で選択`}
        aria-pressed={isSelected}
      >
        <span className="rank">おすすめ {recommendation.rank}</span>
        <span className="card-title-row">
          <span>
            <strong>{recommendation.name}</strong>
            <small>{recommendation.address}</small>
          </span>
          <span className="status-pill">
            <b aria-hidden="true">{status.symbol}</b>
            {status.shortLabel}
          </span>
        </span>
      </button>

      <div className="card-body">
        <p className="recommendation-reason">{recommendation.recommendation_reason}</p>

        <div className="confidence-row">
          <span>AIの判定根拠</span>
          <span className={`confidence confidence-${accessibility.confidence}`}>
            {confidenceLabel[accessibility.confidence]}
          </span>
        </div>

        <ul className="evidence-list">
          {accessibility.reasons.map((reason, index) => (
            <li key={`${reason.condition}-${index}`} className={`result-${reason.result}`}>
              <span className="evidence-symbol" aria-hidden="true">
                {resultSymbol[reason.result]}
              </span>
              <span>
                <b>{conditionLabel[reason.condition] ?? reason.condition}</b>
                <small>{reason.evidence}</small>
              </span>
            </li>
          ))}
        </ul>

        <a href={recommendation.maps_url} target="_blank" rel="noreferrer">
          Google マップで確認
          <span aria-hidden="true"> ↗</span>
        </a>
      </div>
    </article>
  )
}
