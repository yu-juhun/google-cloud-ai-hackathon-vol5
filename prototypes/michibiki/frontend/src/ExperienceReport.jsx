const safeUrl = value => /^https?:\/\//.test(value || '') ? value : null

export default function ExperienceReport({ agent }) {
  const report = agent.detail.reports[0]
  if (!report) return <div><p>{agent.detail.result}</p></div>
  const options = report.place?.accessibility_options || {}
  const facilities = [['入口', 'wheelchairAccessibleEntrance'], ['トイレ', 'wheelchairAccessibleRestroom'], ['座席', 'wheelchairAccessibleSeating'], ['駐車場', 'wheelchairAccessibleParking']]
  const sources = (agent.detail.research?.sources || []).filter(source => report.source_ids?.includes(source.id) && safeUrl(source.url))
  const keyFacts = report.facts.filter(text => !/^(名称|住所|所在地)(は|：|:)/.test(text))
  return <div className="readable-report">
    <p className="report-caption">{agent.name} の体験談 / {agent.place}</p>
    <h3>{report.experience.split(/(?<=。)/)[0]}</h3>
    <p className="report-fit">{(report.fit_reason || report.experience).split(/(?<=。)/).slice(0, 2).join('')}</p>
    <div className="facility-grid" aria-label="Google Mapsの車いす対応情報">{facilities.map(([label, key]) => <span key={key} className={options[key] === true ? 'available' : ''}><small>{label}</small><b>{options[key] === true ? '対応情報あり' : options[key] === false ? '対応なしの情報' : '情報なし'}</b></span>)}</div>
    <div className="report-highlights">
      <section><h4>✓ 公開情報で分かったこと</h4><ul>{keyFacts.slice(0, 3).map((text, i) => <li key={i}>{text}</li>)}</ul>{!keyFacts.length && <p>具体的な設備の情報は、まだ確認できていません。</p>}</section>
      <section className="report-cautions"><h4>! 出発前に確かめたいこと</h4><ul>{[...report.unknowns, ...report.precautions].slice(0, 3).map((text, i) => <li key={i}>{text}</li>)}</ul></section>
    </div>
    {!!sources.length && <p className="report-sources">このレポートの出典：{sources.map(source => <a key={source.id} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</p>}
    <details className="report-full"><summary>根拠と確認事項をすべて読む</summary><p>{report.experience}</p><ul>{[...report.facts, ...report.unknowns, ...report.precautions].map((text, i) => <li key={i}>{text}</li>)}</ul>{safeUrl(report.place?.maps_url) && <a href={report.place.maps_url} target="_blank" rel="noreferrer">Google Mapsの施設情報を見る ↗</a>}</details>
    {agent.detail.reports.length > 1 && <details className="report-full"><summary>ほかの{agent.detail.reports.length - 1}候補のレポート</summary>{agent.detail.reports.slice(1).map(item => <section key={item.place_id}><h4>{item.place?.name || '候補地点'}</h4><p>{item.experience}</p><ul>{item.unknowns.map((text, i) => <li key={i}>{text}</li>)}</ul></section>)}</details>}
  </div>
}

export function SearchEvidence({ research }) {
  if (!research) return null
  return <section className="search-evidence" aria-label="追加調査の情報源"><h3>旅先について、参照した公開情報</h3><p>{research.status === 'available' ? '施設の設備情報に、Web検索で確認できた内容を合わせて検討しています。' : 'Web検索では十分な根拠を取得できませんでした。施設情報だけでは不明な点は、要確認として残しています。'}</p>{research.search_suggestions && <iframe title="Google検索の関連情報" srcDoc={research.search_suggestions} sandbox="allow-popups allow-popups-to-escape-sandbox" />}<details><summary>検索の出典を見る</summary>{research.sources.map(source => safeUrl(source.url) && <a key={source.id} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</details></section>
}
