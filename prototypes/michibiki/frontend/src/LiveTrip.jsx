import { avatarFor } from './avatar-fallback'
import { useEffect, useState } from 'react'
import { api } from './api'
import './live-trip.css'

const illustrations = ['/images/guide-gyoko-route.png', '/images/guide-station-entry.png', '/images/guide-parklet-cafe.png']
const statusText = { uncertain: '要確認', accessible: '候補として検討', not_accessible: '条件に合わない' }
const seconds = value => `${((value || 0) / 1000).toFixed(1)}秒`

function TextList({ title, items }) {
  return items?.length ? <div className="live-notes"><h4>{title}</h4><ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null
}

export default function LiveTrip({ page, trip, profile, avatars = [], result, loading, error, started, onResults, onMap, onNewTrip, onRestore }) {
  const [elapsed, setElapsed] = useState(0)
  const [selected, setSelected] = useState(0)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(result?.saved || false)
  const [saveError, setSaveError] = useState('')
  useEffect(() => { setSelected(0); setSaved(result?.saved || false) }, [result])
  useEffect(() => {
    if (!loading) return
    const tick = () => setElapsed(Math.floor((Date.now() - started) / 1000))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [loading, started])
  const places = new Map((result?.places || []).map(place => [place.place_id, place]))
  const twins = result?.twins || []
  const current = twins[selected]
  const displayedPlace = current?.assessments?.[0] && places.get(current.assessments[0].place_id)
  const mapQuery = displayedPlace?.location?.latitude != null
    ? `${displayedPlace.location.latitude},${displayedPlace.location.longitude}` : trip.destination
  const save = async () => {
    if (saving || saved) return
    setSaving(true); setSaveError('')
    try { await api(`/api/missions/${result.mission_id}/save`, { method: 'POST' }); setSaved(true) }
    catch (err) { setSaveError(err.message) }
    finally { setSaving(false) }
  }
  return <section className="live-trip" id="content">
    <header className="live-heading"><p className="eyebrow">YOUR TRIP / 仮想の自分の旅レポート</p>
      <h1>{loading ? <>あなたの希望を、<em>{trip.twin_count || 3}人で調べています。</em></> : page === 'results' && result ? <>{result.itinerary.title}</> : <>{trip.destination}を、<em>あなたの条件で。</em></>}</h1>
      <p>{trip.wish}</p><small>車いす幅 {profile.width}cm / 段差 {profile.step}cmまで / 連続移動 {profile.stamina}分</small>
    </header>
    <div className="live-demo-note">仮想の自分は公開情報をもとに旅を想像します。実際の現地訪問や測定ではありません。</div>
    {loading && <section className="live-wait" aria-busy="true"><div className="live-portraits">{Array.from({ length: trip.twin_count || 3 }, (_, i) => i).map(i => <img key={i} src={avatarFor(i, avatars[i])} alt="" />)}</div><p className="live-working" role="status"><span aria-hidden="true" />旅の相棒たちが調査中です</p><h2>希望の整理 → 地点検索・条件分析 → 旅程作成</h2><p className="live-estimate">所要時間の目安：約90秒（1〜2分）<small>これまでの実行例に基づく目安です。人数や混雑により、最大約4分かかる場合があります。</small></p><div className="live-progress" role="progressbar" aria-label="分析中。完了までの進捗率は未取得"><span /></div><b>経過 {elapsed}秒</b><p role="status">{elapsed >= 90 ? '目安より時間がかかっています。引き続き結果を待っています。' : '結果を待っています。完了すると自動でレポートを表示します。'}</p><small>バーは処理待ちの表示で、実際の進捗率ではありません。この画面を開いたままお待ちください。</small></section>}
    {!loading && error && <section className="live-error" role="alert"><h2>結果を取得できませんでした</h2><p>{error}</p><div className="live-actions"><button className="journey-button" onClick={onNewTrip}>条件を見直す →</button><button className="button-text" onClick={onRestore}>保存済み結果を確認</button></div></section>}
    {!loading && !result && !error && <section className="live-wait"><h2>まだ旅の分析結果がありません</h2><button className="journey-button" onClick={onNewTrip}>旅の条件を入力する →</button></section>}
    {!loading && result && <>
      <div className="live-metrics"><span>{result.status === 'partial' ? '一部の仮想の自分のみ完了' : `${twins.length}人の分析完了`}</span><span>分析時間 {seconds(result.timings.request_ms || result.timings.agents_total_ms)}</span>{result.timings.browser_ms && <span>画面での待機 {seconds(result.timings.browser_ms)}</span>}<span>{result.persisted ? '✓ レポート・旅程を保存済み' : '未保存'}</span></div>
      {result.clarification && <div className="live-clarification"><b>旅を決める前に確認したいこと</b><p>{result.clarification}</p></div>}
      {page === 'map' ? <>
        <div className="live-map-layout"><div className="live-map"><iframe title={`${trip.destination}の候補地点`} src={`https://www.google.com/maps?q=${encodeURIComponent(mapQuery)}&z=15&output=embed`} /><div className="live-map-caption">{displayedPlace?.name || trip.destination}<small>選択した仮想の自分の最初の候補地点。現在位置や実際の移動を示すものではありません。</small></div></div>
          <aside className="live-guide-picker"><h2>仮想のあなた</h2><p>希望に合わせて役割を分けました。</p>{twins.map((twin, i) => <button key={twin.id} className={selected === i ? 'selected' : ''} onClick={() => setSelected(i)}><img src={avatarFor(i, avatars[i])} alt="" /><span><b>仮想の自分 {twin.ordinal} / {twin.assignment.role}</b><small>{twin.assignment.goal}</small><i>{twin.status === 'completed' ? '分析完了' : '分析できませんでした'} · {seconds(twin.elapsed_ms)}</i></span></button>)}<button className="journey-button" onClick={onResults}>この旅の予定を見る →</button></aside></div>
        {current && <section className="live-reports"><h2>仮想の自分 {current.ordinal} のレポート <span>{current.assignment.role}</span></h2>
          {current.status !== 'completed' && <div className="live-error">この仮想の自分は検索・分析に失敗しました。旅程は他の仮想の自分の結果から作っています。</div>}
          {current.assessments.map((assessment, i) => { const place = places.get(assessment.place_id); return <article className="live-report-card" key={`${assessment.place_id}-${i}`}><figure><img src={illustrations[selected % illustrations.length]} alt="体験を想像するための参考イメージ" /><figcaption>参考イメージ / この場所の実際の写真ではありません</figcaption></figure><div><p className="eyebrow">{statusText[assessment.status]}</p><h3>{place?.name || '候補地点'}</h3><p>{assessment.experience}</p><p className="live-fit">あなたに合いそうな理由：{assessment.fit_reason}</p><TextList title="公開情報から確認できたこと" items={assessment.facts} /><TextList title="まだ分からないこと" items={assessment.unknowns} /><TextList title="行く前に確認すること" items={assessment.precautions} />{place?.maps_url && <a href={place.maps_url} target="_blank" rel="noreferrer">Google Mapsで場所を確認 ↗</a>}</div></article> })}
          <p className="live-attribution">地点情報：Google Maps / 仮想の自分の文章：AIによる分析。幅・段差・混雑など不明な情報は施設への確認が必要です。</p></section>}
        <div className="live-actions"><button className="journey-button" onClick={onResults}>レポートをもとにした旅程を見る →</button><button className="button-text" onClick={onNewTrip}>希望を変えて調べ直す</button></div>
      </> : <section className="live-itinerary"><p className="live-summary">{result.itinerary.summary}</p><ol>{result.itinerary.stops.map((stop, i) => { const place = places.get(stop.place_id); return <li key={`${stop.place_id}-${i}`}><span className="live-stop-number">{String(i + 1).padStart(2, '0')}</span><div><small>滞在目安 {stop.duration_minutes}分{stop.rest_after ? ' / このあと休憩を挟む' : ''}</small><h2>{place?.name || '候補地点'}</h2><b>{stop.activity}</b><p>{stop.reasoning}</p>{place?.maps_url && <a href={place.maps_url} target="_blank" rel="noreferrer">Google Mapsで確認 ↗</a>}</div></li> })}</ol><TextList title="この旅程の前提（時間配分は案です）" items={result.itinerary.assumptions} /><TextList title="旅を決める前の確認事項" items={result.itinerary.unknowns} /><TextList title="別の選択肢" items={result.itinerary.alternatives} /><section className="live-video"><h2>この旅の動画</h2><p>旅の動画は準備中です。</p></section><div className="live-actions"><button className="journey-button" disabled={saving || saved} onClick={save}>{saved ? '✓ この旅を保存しました' : saving ? '保存中…' : 'この旅を保存する →'}</button><button className="button-text" onClick={onMap}>仮想の自分レポートに戻る</button><button className="button-text" onClick={onNewTrip}>新しい旅を相談する</button></div>{saveError && <p className="live-error" role="alert">{saveError}</p>}<small className="live-record">保存レコード：{result.mission_id} / プロンプト：{result.prompt_version}</small></section>}
    </>}
  </section>
}
