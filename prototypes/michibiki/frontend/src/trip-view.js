import { avatarFor } from './avatar-fallback'

const photos = [
  '/images/guide-station-entry.png', '/images/guide-gyoko-route.png',
  '/images/guide-nakadori-crowd.png', '/images/guide-parklet-cafe.png',
  '/images/guide-kitte-rest.png', '/images/guide-forum.png',
  '/images/guide-hibiya-park.png', '/images/guide-artizon.png',
  '/images/guide-yaesu-rain.png', '/images/guide-midtown-return.png',
]
const positions = [[18,32],[35,63],[55,28],[72,48],[44,82],[82,75],[63,67],[27,45],[19,74],[87,24]]

export function mapFor(result, width = 1200, height = 760) {
  const used = new Set((result?.twins || []).map(t => t.assessments[0]?.place_id).filter(Boolean))
  const project = location => {
    const lat = Math.max(-85, Math.min(85, location.latitude)) * Math.PI / 180
    return { x: (location.longitude + 180) / 360, y: (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 }
  }
  const points = (result?.places || []).filter(p => used.has(p.place_id) && Number.isFinite(p.location?.latitude) && Number.isFinite(p.location?.longitude)).map(p => ({ ...project(p.location), id: p.place_id }))
  if (!points.length) return null
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2
  const zoom = Math.max(2, Math.min(17, Math.floor(Math.log2(Math.min(width * .65 / (256 * Math.max(...xs) - 256 * Math.min(...xs) || 1), height * .6 / (256 * Math.max(...ys) - 256 * Math.min(...ys) || 1))))))
  const scale = 256 * 2 ** zoom
  const latitude = Math.atan(Math.sinh(Math.PI * (1 - 2 * cy))) * 180 / Math.PI
  return { query: `${latitude},${cx * 360 - 180}`, zoom, positions: new Map(points.map(p => [p.id, { x: 50 + (p.x - cx) * scale / width * 100, y: 50 + (p.y - cy) * scale / height * 100 }])) }
}

// Adapt API data to the approved map/report presentation, not vice versa.
export function travelersFor(result, count, avatars = []) {
  const places = new Map((result?.places || []).map(p => [p.place_id, p]))
  return Array.from({ length: result?.twins?.length || count }, (_, i) => {
    const twin = result?.twins?.[i]
    const assessments = twin?.assessments || []
    const first = assessments[0]
    const place = first && places.get(first.place_id)
    const done = twin?.status === 'completed'
    const failed = twin?.status === 'failed'
    const notAccessible = first?.status === 'not_accessible'
    const note = notAccessible
      ? `ここは見送って、もっと楽しめる場所へ。${first.fit_reason || first.experience}`
      : first?.experience || (failed ? 'この担当の分析結果を取得できませんでした。' : 'あなたの希望と条件をもとに、旅先を調べています。')
    const generatedImage = twin?.experience_image?.place_id === first?.place_id ? twin?.experience_image?.url : null
    return {
      id: twin?.id || i, name: `わたし ${i + 1}`, ordinal: i + 1,
      role: twin?.assignment?.role || '旅先を調査中',
      place: place?.name || (result ? '候補地点' : '候補を探しています'),
      status: done ? 'done' : failed ? 'failed' : 'exploring',
      x: positions[i][0], y: positions[i][1], avatar: avatarFor(i, avatars[i]),
      note, thought: note, tag: failed ? '結果なし' : notAccessible ? '別の候補へ' : done ? 'レポート到着' : '調査中',
      detail: {
        image: generatedImage || photos[i],
        imagePlaceId: generatedImage ? first.place_id : null,
        imageSceneKind: twin?.experience_image?.scene_kind,
        result: note,
        facts: [['分析状況', done ? '完了' : failed ? '失敗' : '調査中'], ['候補', `${assessments.length}地点`], ['条件', first?.status === 'accessible' ? '候補として検討' : '要確認']],
        timeline: first ? [...first.facts, ...first.unknowns.map(s => `未確認：${s}`)] : [note],
        reports: assessments.map(a => ({ ...a, place: places.get(a.place_id) })),
        research: result?.research,
      },
    }
  })
}

export function itineraryCards(result, travelers) {
  const places = new Map((result.places || []).map(p => [p.place_id, p]))
  return result.itinerary.stops.map((stop, i) => {
    const traveler = travelers.find(t => t.detail.reports.some(a => a.place_id === stop.place_id)) || travelers[0]
    return { ...traveler, id: `stop-${i}`, place: places.get(stop.place_id)?.name || '候補地点', stop,
      detail: { ...traveler.detail,
        image: traveler.detail.imagePlaceId && traveler.detail.imagePlaceId !== stop.place_id ? photos[i % photos.length] : traveler.detail.image,
        imagePlaceId: traveler.detail.imagePlaceId === stop.place_id ? stop.place_id : null,
        result: stop.activity, facts: [['滞在目安', `${stop.duration_minutes}分`]] },
      tag: stop.rest_after ? 'このあと休憩' : '旅程の候補', mapsUrl: places.get(stop.place_id)?.maps_url,
    }
  })
}

export function restSummary(result) {
  const places = new Map((result.places || []).map(p => [p.place_id, p]))
  const rests = result.itinerary.stops.filter(stop => /休憩|ひと休み|一休み/.test(stop.activity))
  if (!rests.length) return '休憩できる場所はまだ確認できていません。座席や利用時間を確認してから出発しましょう。'
  return rests.slice(0, 2).map(stop => `${places.get(stop.place_id)?.name || '休憩候補'}：${stop.activity}`).join('。')
}
