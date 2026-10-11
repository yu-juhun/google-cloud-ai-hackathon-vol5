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
        if (data.status === 'ready') timer = setTimeout(refresh, 50 * 60 * 1000)
        else if (data.status === 'generating') timer = setTimeout(refresh, 5000)
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

export function usePool(refreshKey) {
  const [pool, setPool] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api('/api/avatars/pool').then(data => active && setPool(data)).catch(err => active && setError(err.message))
    return () => { active = false }
  }, [refreshKey])
  return { pool, error, reload: () => setPool(null) }
}

export default function AvatarSetup({ profile, setProfile, mediaState, onRefreshAvatar }) {
  const [photo, setPhoto] = useState(null)
  const [consent, setConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(null)
  const [poolVersion, setPoolVersion] = useState(0)
  const [gender, setGender] = useState(null)
  const { pool, reload } = usePool(`${poolVersion}-${mediaState.status}`)
  useEffect(() => {
    let active = true
    api('/api/persona/capabilities').then(caps => active && setConfigured(caps.avatar_configured))
      .catch(err => active && setError(err.message))
    return () => { active = false }
  }, [])
  useEffect(() => {
    let active = true
    api('/api/profile/avatar-gender').then(data => active && setGender(data.gender))
      .catch(err => active && setError(err.message))
    return () => { active = false }
  }, [])
  const selectGender = async value => {
    try {
      await api('/api/profile/avatar-gender', { method: 'PUT', body: { gender: value } })
      setGender(value)
    } catch (err) { setError(err.message) }
  }
  const generating = submitting || mediaState.status === 'generating'
  const create = async () => {
    if (!photo || !consent || generating) return
    if (photo.size > 6_000_000) { setError('6MB以下のJPEG/PNG写真を選んでください。'); return }
    setSubmitting(true); setError('')
    try {
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(photo)
      })
      const job = await api('/api/avatars', { method: 'POST', body: { photo: encoded, consent } })
      setProfile(current => {
        const next = { ...current, avatarSetId: job.id }
        localStorage.setItem('michibiki-profile', JSON.stringify(next))
        return next
      })
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }
  const selectAvatar = async objectName => {
    try {
      await api('/api/profile/avatar', { method: 'PUT', body: { object_name: objectName } })
      setPoolVersion(v => v + 1)
      reload()
      if (onRefreshAvatar) onRefreshAvatar()
    } catch (err) { setError(err.message) }
  }
  return <section className="avatar-setup"><h3>ひとりのあなたから、探検隊を。</h3><p>あなたの写真から、ランダムなスタイルで旅の相棒のアイコンを作ります。生成するたびに新しいスタイルが追加されます。</p>
    <div className="avatar-gender" role="radiogroup" aria-label="アバターのスタイルの性別"><span>スタイルの性別</span>
      <button type="button" role="radio" aria-checked={gender === 'female'} className={gender === 'female' ? 'selected' : ''} disabled={generating} onClick={() => selectGender('female')}>女性的</button>
      <button type="button" role="radio" aria-checked={gender === 'male'} className={gender === 'male' ? 'selected' : ''} disabled={generating} onClick={() => selectGender('male')}>男性的</button>
    </div>
    <label className="avatar-file"><span>あなたの写真</span><span className="avatar-upload"><span aria-hidden="true">＋</span>{photo ? '写真を選び直す' : '写真を選ぶ'}<input type="file" accept="image/jpeg,image/png" disabled={generating} onChange={event => { setPhoto(event.target.files?.[0] || null); setError('') }} /></span><small>{photo ? photo.name : 'JPEG・PNG / 6MBまで'}</small></label>
    <label className="avatar-consent"><input type="checkbox" checked={consent} disabled={generating} onChange={event => setConsent(event.target.checked)} /><span>この写真をYouCamへ送信してアバターを生成することに同意します。</span></label>
    <button type="button" className="journey-button" disabled={!photo || !consent || generating || configured !== true} onClick={create}>{generating ? '探検隊を準備しています…' : 'あなたの探検隊をつくる →'}</button>
    {configured === false && <div className="avatar-unavailable"><b>画像生成は準備中です</b><p>サービスの接続設定がまだ完了していません。今は表示中のアイコンで旅をつくれます。</p></div>}
    {generating && <p aria-live="polite">生成には数分かかります。生成依頼は保存されるので、再読み込みしても確認できます。</p>}
    {(error || mediaState.error) && <p className="avatar-warning" role="alert">{error || mediaState.error}</p>}
    {pool?.avatars?.length > 0 && <div className="avatar-roster"><b>生成済みのアバター(クリックでプロフィールに設定)</b><div>{pool.avatars.map(a => <button key={a.object_name} type="button" className={pool.selected === a.object_name ? 'selected' : ''} onClick={() => selectAvatar(a.object_name)}><img src={a.url} alt="" /></button>)}</div></div>}
    <details className="data-handling"><summary>写真とデータの扱い</summary><p>元の写真はアプリに保存せず、生成したアバターだけを非公開で保存します。ブラウザの保存データを消すと再表示できなくなる場合があります。</p></details>
  </section>
}
