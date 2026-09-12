import type {
  AccessibilityStatus,
  AssessmentResult,
  Confidence,
} from '../api/types'

export const statusMeta: Record<
  AccessibilityStatus,
  { symbol: string; label: string; shortLabel: string }
> = {
  accessible: { symbol: '○', label: '利用しやすい見込み', shortLabel: '利用しやすい' },
  uncertain: { symbol: '△', label: '事前確認がおすすめ', shortLabel: '要確認' },
  not_accessible: { symbol: '×', label: '利用が難しい見込み', shortLabel: '利用が難しい' },
}

export const confidenceLabel: Record<Confidence, string> = {
  high: '根拠が多い',
  medium: '根拠は一部',
  low: '情報が少ない',
}

export const conditionLabel: Record<string, string> = {
  entrance: '入口',
  aisle: '通路',
  restroom: 'トイレ',
  seating: '座席',
  parking: '駐車場',
}

export const resultSymbol: Record<AssessmentResult, string> = {
  supported: '✓',
  unsupported: '×',
  unknown: '?',
}
