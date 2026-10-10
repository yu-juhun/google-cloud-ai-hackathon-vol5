import { useEffect, useState } from 'react'
import { api } from './api'
import './history.css'

export default function History({ onOpen, onPlan }) {
  const [missions, setMissions] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/missions').then(data => setMissions(data.missions)).catch(err => setError(err.message))
  }, [])

  return <section className="history-page" id="content">
    <header><p className="eyebrow">YOUR TRIPS</p><h1>これまでの旅</h1></header>
    {error && <p className="history-warning" role="alert">{error}</p>}
    {!error && missions === null && <p aria-live="polite">読み込み中です。</p>}
    {!error && missions?.length === 0 && <p>まだ旅の記録がありません。<button className="nav-button" onClick={onPlan}>旅をつくる <span>→</span></button></p>}
    {missions?.length > 0 && <ul className="history-list">
      {missions.map(mission => <li key={mission.id}>
        <button onClick={() => onOpen(mission.id)}>
          <span className="history-destination">{mission.destination}</span>
          <span className="history-date">{mission.date}</span>
          <span className={`history-status history-status-${mission.status}`}>{mission.status}</span>
        </button>
      </li>)}
    </ul>}
  </section>
}
