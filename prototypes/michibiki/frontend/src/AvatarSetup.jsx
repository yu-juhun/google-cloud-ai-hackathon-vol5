import { useEffect, useState } from 'react'
import { api } from './api'
import './avatar-setup.css'

// Refresh expiring URLs; the database stores object names, never signed URLs.
export function useAvatarSet(profile, setProfile) {
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const id = profile.avatarSetId
  useEffect(() => {
    if (!id) { setStatus(''); return }
    let active = true, timer
    const refresh = async () => {
      try {
        const data = await api(`/api/avatars/${encodeURIComponent(id)}`)
        if (!active) return
        setStatus(data.status); setError('')
        if (data.status === 'ready') {
          setProfile(current => {
            if (current.avatarSetId !== id) return current
            const next = { ...current, avatar: data.images[0], twinAvatars: data.images.slice(1), mouthOpen: data.mouth_open }
            localStorage.setItem('michibiki-profile', JSON.stringify(next))
            return next
          })
          timer = setTimeout(refresh, 50 * 60 * 1000)
        } else if (data.status === 'generating') timer = setTimeout(refresh, 5000)
        else setError('画像生成に失敗しました。写真を選び直してください。')
      } catch (err) {
        if (active) { setError(err.message); timer = setTimeout(refresh, 15000) }
      }
    }
    refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [id, setProfile])
  return { status, error }
}

export default function AvatarSetup({ profile, setProfile, mediaState }) {
  const [catalog, setCatalog] = useState({})
  const [template, setTemplate] = useState('')
  const [photo, setPhoto] = useState(null)
  const [consent, setConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(null)
  useEffect(() => {
    let active = true
    Promise.all([api('/api/avatar-templates'), api('/api/persona/capabilities')]).then(([styles, caps]) => {
      if (active) { setCatalog(styles); setConfigured(caps.avatar_configured) }
    }).catch(err => active && setError(err.message))
    return () => { active = false }
  }, [])
  const generating = submitting || mediaState.status === 'generating'
  const create = async () => {
    if (!photo || !template || !consent || generating) return
    if (photo.size > 6_000_000) { setError('6MB以下のJPEG/PNG写真を選んでください。'); return }
    setSubmitting(true); setError('')
    try {
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(photo)
      })
      const job = await api('/api/avatars', { method: 'POST', body: { photo: encoded, template_id: template, consent } })
      setProfile(current => {
        const next = { ...current, avatarSetId: job.id }
        localStorage.setItem('michibiki-profile', JSON.stringify(next))
        return next
      })
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }
  return <section className="avatar-setup"><h3>ひとりのあなたから、探検隊を。</h3><p>あなたのアイコン1枚と、旅の相棒のアイコン10枚。写真から、旅の相棒を事前に作ります。</p>
    <label>アバターのスタイル<select value={template} onChange={event => setTemplate(event.target.value)} disabled={generating}><option value="">スタイルを選んでください</option>{Object.entries(catalog).flatMap(([gender, categories]) => Object.entries(categories).map(([category, styles]) => <optgroup label={`${gender === 'male' ? '男性的' : gender === 'female' ? '女性的' : gender} / ${category}`} key={`${gender}-${category}`}>{styles.map(style => <option key={style.id} value={style.id}>{style.title}</option>)}</optgroup>))}</select></label>
    <label className="avatar-file"><span>あなたの写真</span><span className="avatar-upload"><span aria-hidden="true">＋</span>{photo ? '写真を選び直す' : '写真を選ぶ'}<input type="file" accept="image/jpeg,image/png" disabled={generating} onChange={event => { setPhoto(event.target.files?.[0] || null); setError('') }} /></span><small>{photo ? photo.name : 'JPEG・PNG / 6MBまで'}</small></label>
    <label className="avatar-consent"><input type="checkbox" checked={consent} disabled={generating} onChange={event => setConsent(event.target.checked)} /><span>この写真をYouCamへ送信してアバターを生成することに同意します。</span></label>
    <button type="button" className="journey-button" disabled={!photo || !template || !consent || generating || configured !== true} onClick={create}>{generating ? '探検隊を準備しています…' : 'あなたの探検隊をつくる →'}</button>
    {configured === false && <div className="avatar-unavailable"><b>画像生成は準備中です</b><p>サービスの接続設定がまだ完了していません。今は表示中のアイコンで旅をつくれます。</p></div>}
    {generating && <p aria-live="polite">生成には数分かかります。生成依頼は保存されるので、再読み込みしても確認できます。</p>}
    {(error || mediaState.error) && <p className="avatar-warning" role="alert">{error || mediaState.error}</p>}
    {profile.twinAvatars?.length === 10 && <div className="avatar-roster"><b>あなたの旅の相棒たち</b><div>{profile.twinAvatars.map((url, i) => <img key={i} src={url} alt={`仮想の自分${i + 1}`} />)}</div></div>}
    <details className="data-handling"><summary>写真とデータの扱い</summary><p>元の写真はアプリに保存せず、生成したアバターだけを非公開で保存します。ブラウザの保存データを消すと再表示できなくなる場合があります。</p></details>
  </section>
}
