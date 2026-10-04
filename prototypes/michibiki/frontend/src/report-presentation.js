export const cleanReportText = text => (text || '').replace(/\(?source-\d+(?:\s*[,、]\s*source-\d+)*\)?/g, '').trim()

export function equipmentSummary(result) {
  const places = new Map((result.places || []).map(place => [place.place_id, place]))
  const selected = [...new Set(result.itinerary.stops.map(stop => stop.place_id))].map(id => places.get(id)).filter(Boolean)
  const positive = selected.map(place => {
    const options = place.accessibility_options || {}
    const labels = [['wheelchairAccessibleEntrance', '車いす対応入口'], ['wheelchairAccessibleRestroom', '車いす対応トイレ'], ['wheelchairAccessibleSeating', '車いす対応座席']].filter(([key]) => options[key] === true).map(([, label]) => label)
    return labels.length ? `${place.name}：${labels.join('・')}の対応情報あり` : null
  }).filter(Boolean)
  if (positive.length) return positive.slice(0, 2).join('。')
  const negative = selected.find(place => place.accessibility_options?.wheelchairAccessibleEntrance === false)
  if (negative) return `${negative.name}は車いす対応入口なしの情報があります。別の候補を選ぶ際の判断材料にしてください。`
  return '各候補の対応設備を、下の場所別レポートで見比べられます。'
}

export function featuredCautions(report) {
  // Keep exhaustive unknowns in the expandable evidence, not repeated cards.
  const specific = report.precautions.filter(text => !/入口.*幅|幅.*入口|段差.*(不明|未確認)|不明です|情報がありません/.test(text))
  return [...new Set(specific)].slice(0, 2).map(cleanReportText)
}
