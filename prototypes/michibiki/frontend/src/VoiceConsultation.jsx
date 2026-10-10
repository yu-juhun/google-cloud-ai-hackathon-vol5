import { useEffect, useRef, useState } from 'react'
import { apiOrigin, clientToken } from './api'
import { createAudioPlayback } from './persona/audio/audioPlayback'
import { startMicCapture, rmsVolume } from './persona/audio/micCapture'
import './voice-consultation.css'

export default function VoiceConsultation({ trip, profile, onUse, purpose = 'trip_wish' }) {
  const [state, setState] = useState('idle')
  const [voice, setVoice] = useState('Kore')
  const [mouth, setMouth] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const resources = useRef({})
  const cleanup = () => {
    const r = resources.current
    clearTimeout(r.timer); clearTimeout(r.mouthTimer)
    r.mic?.stop(); r.playback?.stop(); r.ws?.close()
    resources.current = {}
  }
  useEffect(() => () => cleanup(), [])
  const start = async () => {
    cleanup(); setError(''); setResult(null); setState('connecting')
    const r = {}; resources.current = r
    try {
      if (!apiOrigin) throw new Error('音声相談は準備中です。文字入力をご利用ください。')
      r.playback = createAudioPlayback()
      await r.playback.resume()
      r.ws = new WebSocket(apiOrigin.replace(/^http/, 'ws') + `/api/persona/converse?voice=${voice}&purpose=${purpose}`)
      await new Promise((resolve, reject) => {
        r.timer = setTimeout(() => reject(new Error('音声相談への接続がタイムアウトしました。')), 30000)
        r.ws.onopen = () => r.ws.send(JSON.stringify({ client_token: clientToken() }))
        r.ws.onerror = () => reject(new Error('音声相談に接続できませんでした。少し待ってからお試しください。'))
        r.ws.onclose = () => {
          if (r.finished || resources.current !== r) return
          r.mic?.stop(); r.playback?.stop()
          reject(new Error('音声相談の接続が終了しました。'))
          setError('接続が終了しました。文字入力でも続けられます。'); setState('idle')
        }
        r.ws.onmessage = event => {
          const message = JSON.parse(event.data)
          if (message.type === 'session_ready') { clearTimeout(r.timer); resolve() }
          if (message.type === 'audio_chunk') {
            const bytes = Uint8Array.from(atob(message.data), c => c.charCodeAt(0)).buffer
            r.playback?.playChunk(bytes)
            setMouth(rmsVolume(bytes) > .02)
            clearTimeout(r.mouthTimer); r.mouthTimer = setTimeout(() => setMouth(false), 250)
          }
          if (message.type === 'persona_result') {
            r.finished = true; setResult(message.data); setState('done'); setMouth(false)
            r.mic?.stop(); r.mic = null; r.playback?.stop(); r.playback = null
          }
          if (message.type === 'start_error' || message.type === 'finish_error') {
            reject(new Error(message.message)); setError(message.message); setState('idle'); cleanup()
          }
        }
      })
      if (resources.current !== r) return
      r.ws.send(JSON.stringify({ type: 'context', data: { destination: trip.destination, wish: trip.wish } }))
      r.mic = await startMicCapture(chunk => {
        if (r.ws.readyState === WebSocket.OPEN) {
          const view = new Uint8Array(chunk)
          r.ws.send(JSON.stringify({ type: 'audio_chunk', data: btoa(String.fromCharCode(...view)) }))
        }
      }, () => {})
      if (resources.current !== r) { r.mic.stop(); return }
      setState('talking')
    } catch (err) { if (resources.current === r) { cleanup(); setError(err.message); setState('idle') } }
  }
  const finish = () => {
    const r = resources.current
    r.mic?.stop(); r.mic = null
    if (r.ws?.readyState === WebSocket.OPEN) { r.ws.send(JSON.stringify({ type: 'finish' })); setState('summarizing') }
  }
  const wish = result?.attributes?.filter(a => a.domain === 'purpose' && a.confidence !== 'low').map(a => a.description).join('。') || result?.raw_summary || ''
  return <section className="voice-consultation" aria-label="声で旅の相談">
    <div className="voice-avatar"><img src={mouth && profile.mouthOpen ? profile.mouthOpen : profile.avatar} alt="あなたの相談アバター" /><span>{state === 'talking' ? '相談中' : '旅の相談室'}</span></div>
    <h3>まだ言葉になっていない旅も、話してみよう。</h3><p>行きたい場所、推しのこと、気がかりなこと。会話から希望を一緒に整理します。</p>
    <fieldset className="voice-choice"><legend>どんな声で相談する？</legend><div>{[['Kore', 'しっかりした声', '頼れる雰囲気'], ['Puck', '明るい声', '軽やかな雰囲気'], ['Charon', '説明向きの声', 'じっくり相談したいときに'], ['Leda', '若々しい声', '親しみやすい雰囲気']].map(([id, title, description]) => <label key={id} className={voice === id ? 'selected' : ''}><input type="radio" name="consultation-voice" value={id} checked={voice === id} disabled={!['idle','done'].includes(state)} onChange={() => setVoice(id)} /><span><b>{title}</b><span>{description}</span></span></label>)}</div></fieldset>
    <div className="voice-actions"><button type="button" onClick={start} disabled={!['idle','done'].includes(state)}>{state === 'connecting' ? 'つないでいます…' : 'マイクで相談をはじめる'}</button>{state === 'talking' && <button type="button" onClick={finish}>話した内容をまとめる</button>}</div>
    {state === 'talking' && <div className="voice-next-step" role="status"><b>希望を話したら、会話はここで終えて大丈夫です。</b><p>①「話した内容をまとめる」を押す<br />② 内容を確認して「希望と条件に反映する」を押す</p></div>}{state === 'summarizing' && <p aria-live="polite">話した内容を整理しています… 終わったら「希望と条件に反映する」を押してください。</p>}
    {error && <p className="voice-error" role="alert">{error}</p>}
    {result && <div className="voice-summary"><h4>こんな旅にしたい、で合っていますか？</h4><p>{result.raw_summary}</p><button type="button" onClick={() => onUse(wish.slice(0, 1000), result)}>希望と条件に反映する →</button><small>反映後も文字で編集できます。数値の移動条件は勝手に変更しません。</small></div>}
    <details className="data-handling"><summary>音声とデータの扱い</summary><p>会話の音声はGoogleの音声AIに送信します。録音はアプリに保存せず、整理した希望だけを保存します。</p></details>
  </section>
}
