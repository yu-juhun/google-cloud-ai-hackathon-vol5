import { useEffect, useState } from 'react'
import { api, clientToken } from './api'
import VoiceConsultation from './VoiceConsultation'
import './video-request.css'

const STYLES = [['cinematic', 'シネマティック'], ['long_take', 'ロングテイク'], ['narrated', 'ナレーション付き']]
const TONES = [['calm', '穏やかな'], ['dramatic', 'ドラマチックな'], ['relaxed', '落ち着いた']]

export default function VideoRequest({ reportId, missionId, place, reportText, profile }) {
  const [feedback, setFeedback] = useState('')
  const [inputMethod, setInputMethod] = useState('text')
  const [style, setStyle] = useState('cinematic')
  const [tone, setTone] = useState('calm')
  const [consent, setConsent] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState(null)
  const statusPath = missionId ? `/api/journey-videos/by-mission/${missionId}` : `/api/videos/by-report/${reportId}`

  const useConsultation = wish => { setFeedback(wish.slice(0, 500)); setInputMethod('text') }

  useEffect(() => {
    let active = true, timer
    setJobId(null); setStatus(''); setVideoUrl(null); setError(''); setProgress(null)
    const refresh = () => {
    api(statusPath).then(found => {
      if (!active) return
      setStatus(found.status)
      setProgress(found)
      if (found.status === 'ready') { setVideoUrl(found.video_url); setError(''); return }
      if (found.status === 'failed') { setError(found.error === 'submission_outcome_unknown'
        ? '生成依頼の受付を確認できませんでした。重複生成を避けて停止しています。'
        : '動画を完成できませんでした。保存済みの旅程はそのまま使えます。'); return }
      if (found.job_id) { setJobId(found.job_id); setStatus(found.status) }
      timer = setTimeout(refresh, 10000)
    }).catch(() => { if (active) timer = setTimeout(refresh, 10000) })
    }
    refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [statusPath])

  const submit = async () => {
    if (!consent || submitting || (jobId && !['failed', 'ready'].includes(status))) return
    setSubmitting(true); setError('')
    try {
      const job = await api(missionId ? '/api/journey-videos' : '/api/videos', { method: 'POST', body: missionId
        ? { mission_id: missionId, feedback, consent }
        : { report_id: reportId, feedback, style, tone, consent } })
      setJobId(job.id); setStatus(job.status)
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }

  useEffect(() => {
    if (missionId || !jobId || videoUrl) return
    const origin = (import.meta.env.VITE_API_URL || window.MICHIBIKI_API_URL || '').replace(/\/$/, '')
    const wsUrl = origin.replace(/^http/, 'ws') + `/api/video-jobs/${jobId}/progress`
    const socket = new WebSocket(wsUrl)
    socket.onopen = () => socket.send(JSON.stringify({ type: 'hello', client_token: clientToken() }))
    socket.onmessage = event => {
      const message = JSON.parse(event.data)
      if (message.type === 'status') {
        setStatus(message.status)
        if (message.status === 'ready') setVideoUrl(message.video_url)
        if (message.status === 'failed') setError(message.message)
      }
    }
    socket.onerror = () => {} // HTTP refresh above recovers interrupted streams.
    return () => socket.close()
  }, [jobId, videoUrl, missionId])

  return <section className="video-request">
    {missionId && <header><h3>この一日を、一本の旅のお便りに。</h3><p>おすすめの旅程から最大4場面。4場面なら約24秒の動画になります。生成には数分かかります。</p></header>}
    {(!jobId || status === 'failed') && <>
      <div className="input-method" role="group" aria-label="フィードバックの入力方法">
        <button type="button" aria-pressed={inputMethod === 'text'} onClick={() => setInputMethod('text')}>文字で伝える</button>
        <button type="button" aria-pressed={inputMethod === 'voice'} onClick={() => setInputMethod('voice')}>声で相談する</button>
      </div>
      {inputMethod === 'voice' && <VoiceConsultation trip={{ destination: place, wish: reportText }} profile={profile} onUse={useConsultation} purpose="video_feedback" />}
      <label>動画に込めたいこと（任意）<textarea placeholder="例：景色を見つけた瞬間と、ほっとひと休みする表情を見たい" maxLength={500} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={submitting} />
        <small>{feedback.length}/500</small></label>
      {!missionId && <><label>動画スタイル<select value={style} onChange={e => setStyle(e.target.value)} disabled={submitting}>
        {STYLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>動画の雰囲気<select value={tone} onChange={e => setTone(e.target.value)} disabled={submitting}>
        {TONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label></>}
      <label className="video-consent"><input type="checkbox" checked={consent} disabled={submitting}
        onChange={e => setConsent(e.target.checked)} />
        <span>{missionId ? '保存済みアバター（なければデモ人物）、旅程・調査結果・参照画像を動画生成に使うことに同意します。' : '体験画像（なければアバター）とレポートを動画生成に使うことに同意します。'}</span></label>
      <button type="button" className="journey-button" disabled={!consent || submitting} onClick={submit}>
        {submitting ? '参照画像を準備しています…' : missionId ? 'この旅の動画を作る →' : '動画を作る →'}</button>
    </>}
    {jobId && !videoUrl && !error &&
      <div aria-live="polite"><p>{status === 'rendering' ? '場面をつなぎ、音を整えています。' : '旅のお便りを映像にしています。'} 数分かかる場合があります。再読み込みしても同じ依頼を確認できます。</p>
        {missionId && <><progress max={progress?.scene_count || 4} value={progress?.completed_scenes || 0} />
          <p>{progress?.completed_scenes || 0} / {progress?.scene_count || 4} 場面が完成</p>
          <ol>{progress?.scenes?.map((scene, index) => <li key={index}>{scene.name}：{scene.status === 'ready' ? '完成' : ['generating', 'submitting'].includes(scene.status) ? '映像を作成中' : 'これから'}</li>)}</ol>
          <p>画面を閉じると次の場面の開始は一時停止し、この旅を再び開くと続きから進みます。</p></>}
      </div>}
    {videoUrl && <><video controls playsInline src={videoUrl} /><small>公開情報と生成画像から作った仮想体験です。現地訪問や通行の証拠ではありません。</small></>}
    {videoUrl && !!progress?.credits?.length && <details><summary>参考写真の出典</summary><ul>{progress.credits.map((credit, index) => <li key={index}><a href={credit.source} target="_blank" rel="noreferrer">{credit.author} / {credit.license}</a></li>)}</ul></details>}
    {error && <p className="video-warning" role="alert">{error}</p>}
  </section>
}
