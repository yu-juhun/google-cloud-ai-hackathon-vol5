import { useEffect, useState } from 'react'
import { api, clientToken } from './api'
import VoiceConsultation from './VoiceConsultation'
import './video-request.css'

const STYLES = [['cinematic', 'シネマティック'], ['long_take', 'ロングテイク'], ['narrated', 'ナレーション付き']]
const TONES = [['calm', '穏やかな'], ['dramatic', 'ドラマチックな'], ['relaxed', '落ち着いた']]

export default function VideoRequest({ reportId, place, reportText, profile }) {
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

  const useConsultation = wish => { setFeedback(wish.slice(0, 500)); setInputMethod('text') }

  useEffect(() => {
    let active = true, timer
    setJobId(null); setStatus(''); setVideoUrl(null); setError('')
    const refresh = () => {
    api(`/api/videos/by-report/${reportId}`).then(found => {
      if (!active) return
      setStatus(found.status)
      if (found.status === 'ready') { setVideoUrl(found.video_url); setError(''); return }
      if (found.status === 'failed') { setError('動画を作れませんでした。もう一度試せます。'); return }
      if (found.job_id) { setJobId(found.job_id); setStatus(found.status) }
      timer = setTimeout(refresh, 10000)
    }).catch(() => { if (active) timer = setTimeout(refresh, 10000) })
    }
    refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [reportId])

  const submit = async () => {
    if (!consent || submitting || (jobId && !['failed', 'ready'].includes(status))) return
    setSubmitting(true); setError('')
    try {
      const job = await api('/api/videos', { method: 'POST', body: { report_id: reportId, feedback, style, tone, consent } })
      setJobId(job.id); setStatus(job.status)
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }

  useEffect(() => {
    if (!jobId || videoUrl) return
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
  }, [jobId, videoUrl])

  return <section className="video-request">
    {(!jobId || status === 'failed') && <>
      <div className="input-method" role="group" aria-label="フィードバックの入力方法">
        <button type="button" aria-pressed={inputMethod === 'text'} onClick={() => setInputMethod('text')}>文字で伝える</button>
        <button type="button" aria-pressed={inputMethod === 'voice'} onClick={() => setInputMethod('voice')}>声で相談する</button>
      </div>
      {inputMethod === 'voice' && <VoiceConsultation trip={{ destination: place, wish: reportText }} profile={profile} onUse={useConsultation} purpose="video_feedback" />}
      <label>動画に込めたいこと（任意）<textarea placeholder="例：景色を見つけた瞬間と、ほっとひと休みする表情を見たい" maxLength={500} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={submitting} />
        <small>{feedback.length}/500</small></label>
      <label>動画スタイル<select value={style} onChange={e => setStyle(e.target.value)} disabled={submitting}>
        {STYLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>動画の雰囲気<select value={tone} onChange={e => setTone(e.target.value)} disabled={submitting}>
        {TONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="video-consent"><input type="checkbox" checked={consent} disabled={submitting}
        onChange={e => setConsent(e.target.checked)} />
        <span>体験画像（なければアバター）とレポートを動画生成に使うことに同意します。</span></label>
      <button type="button" className="journey-button" disabled={!consent || submitting} onClick={submit}>
        {submitting ? '依頼を送信中…' : '動画を作る →'}</button>
    </>}
    {jobId && !videoUrl && !error &&
      <p aria-live="polite">旅のお便りを映像にしています。数分かかる場合があります。再読み込みしても同じ依頼の結果を確認できます。</p>}
    {videoUrl && <><video controls playsInline src={videoUrl} /><small>公開情報と生成画像から作った仮想体験です。現地訪問や通行の証拠ではありません。</small></>}
    {error && <p className="video-warning" role="alert">{error}</p>}
  </section>
}
