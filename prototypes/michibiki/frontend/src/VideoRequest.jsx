import { useEffect, useState } from 'react'
import { api, clientToken } from './api'
import './video-request.css'

const STYLES = [['cinematic', 'シネマティック'], ['long_take', 'ロングテイク'], ['narrated', 'ナレーション付き']]
const TONES = [['calm', '穏やかな'], ['dramatic', 'ドラマチックな'], ['relaxed', '落ち着いた']]

export default function VideoRequest({ reportId }) {
  const [feedback, setFeedback] = useState('')
  const [style, setStyle] = useState('cinematic')
  const [tone, setTone] = useState('calm')
  const [consent, setConsent] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!consent || submitting) return
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
    socket.onerror = () => setError('動画の進行状況を取得できませんでした。')
    return () => socket.close()
  }, [jobId, videoUrl])

  return <section className="video-request">
    {!jobId && <>
      <label>フィードバック<textarea maxLength={500} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={submitting} />
        <small>{feedback.length}/500</small></label>
      <label>動画スタイル<select value={style} onChange={e => setStyle(e.target.value)} disabled={submitting}>
        {STYLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>感情トーン<select value={tone} onChange={e => setTone(e.target.value)} disabled={submitting}>
        {TONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="video-consent"><input type="checkbox" checked={consent} disabled={submitting}
        onChange={e => setConsent(e.target.checked)} />
        <span>あなたのアバター画像とこの体験談をもとに、Veoへ送信して動画を生成することに同意します。</span></label>
      <button type="button" className="journey-button" disabled={!consent || submitting} onClick={submit}>
        {submitting ? '依頼を送信中…' : '動画を作る →'}</button>
    </>}
    {jobId && !videoUrl && !error &&
      <p aria-live="polite">動画生成には数分かかります。生成依頼は保存されるので、ページを再読み込みしても続きから確認できます。(現在: {status})</p>}
    {videoUrl && <video controls src={videoUrl} />}
    {error && <p className="video-warning" role="alert">{error}</p>}
  </section>
}
