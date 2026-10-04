import './twin-fleet.css'
import { avatarFor, avatarTone } from './avatar-fallback'

const hints = count => count === 1 ? 'まずは精鋭ひとりで。気になることを、ぎゅっと確認。'
  : count <= 3 ? '小さな探検隊。行きたい・通れる・休めるを分担します。'
  : count <= 6 ? '寄り道の候補まで、手分けして見つけるチーム。'
  : '好奇心をフル派遣。いろんな角度から、旅の可能性を探します。'

export default function TwinFleet({ count = 3, onChange, avatars = [], disabled }) {
  return <fieldset className="twin-fleet" disabled={disabled}>
    <legend>あなた、何人いたらうれしい？</legend>
    <div className="fleet-heading"><p>仮想の自分をひと足先に、旅へ。</p><output aria-live="polite"><b>{count}</b>人の探検隊</output></div>
    <div className="fleet-choices" role="group" aria-label="派遣する仮想の自分の数">
      {Array.from({ length: 10 }, (_, i) => i + 1).map(number => <button type="button" key={number} aria-pressed={count === number} className={number === count ? 'selected' : ''} onClick={() => onChange(number)}>{number}</button>)}
    </div>
    <div className="fleet-preview" aria-hidden="true">{Array.from({ length: count }, (_, i) => <span key={i}><img style={{ borderColor: avatarTone(i) }} src={avatarFor(i, avatars[i])} alt="" /><small>{String(i + 1).padStart(2, '0')}</small></span>)}</div>
    <p className="fleet-hint">{hints(count)}</p><small>人数が多いほど、調べる観点と処理時間・API利用量が増えます。</small>
  </fieldset>
}
