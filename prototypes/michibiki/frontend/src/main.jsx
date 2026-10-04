import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import LiveTrip from './LiveTrip'
import ExperienceReport, { SearchEvidence, conditionSummary } from './ExperienceReport'
import { avatarTone } from './avatar-fallback'
import TwinFleet from './TwinFleet'
import AvatarSetup, { useAvatarSet } from './AvatarSetup'
import VoiceConsultation from './VoiceConsultation'
import { api, serverProfile } from './api'
import { travelersFor, itineraryCards, mapFor, restSummary } from './trip-view'
import './style.css'

const rawAgents = [
  ['ひなた','入口・幅員','東京駅 丸の内南口','done',18,32,'最も狭い箇所でも92cm。70cm幅なら余裕を持って通れました。','通過 OK'],
  ['さくら','桜の散策・段差','皇居外苑・二重橋','done',35,63,'二重橋までの散策路はなだらか。桜を見ながら安心して進めます。','段差 0–2cm'],
  ['あおい','混雑・居心地','丸の内仲通り','exploring',55,28,'平日午前はゆったり。ベンチ周辺の人の流れを確認中です。','体験中'],
  ['はる','カフェ・休憩','丸の内ブリックスクエア','done',72,48,'入口の有効幅は88cm。スタッフに声をかけず入れました。','入店 OK'],
  ['ゆき','眺め・休憩','KITTE丸の内 屋上庭園','exploring',44,82,'多目的トイレまでの導線と、屋上で休める場所を確認中です。','体験中'],
  ['りん','建築・エレベーター','東京国際フォーラム','moving',82,75,'この地点へ向かっています。','移動中'],
  ['みずき','静けさ・休憩','日比谷公園','moving',63,67,'この地点へ向かっています。','移動中'],
  ['なぎ','美術館・案内','アーティゾン美術館','moving',27,45,'この地点へ向かっています。','移動中'],
  ['つむぎ','雨の日導線','東京駅八重洲地下街','moving',19,74,'通れますが、雨の日の通勤時間はすれ違いと方向転換に気を使います。','注意あり'],
  ['こはる','帰り道・休憩','東京ミッドタウン八重洲','moving',87,24,'この地点へ向かっています。','移動中'],
]
const agentThoughts = { ひなた: '入口は広いです。このまま気持ちよく出発できそう。', さくら: '桜の下で止まっても、後ろを気にしなくて大丈夫。', あおい: 'ベンチまわりも、今はゆったりしています。', はる: '気になっていたお店、ひとりで入れました。', ゆき: '休める席までの道を、もう少し見てきます。', りん: '新丸ビルへ向かっています。', みずき: '静かな広場を探しに行きます。', なぎ: '駅の案内を確認しに行きます。', つむぎ: '雨の日は、混む前に通る方が安心かもしれません。', こはる: '帰り道も、先に確かめてきます。' }
const agentDetails = {
  ひなた:{image:'/images/guide-station-entry.png',facts:[['最小幅','92cm'],['段差','0–2cm'],['自動ドア','あり']],timeline:['10:02　丸の内駅舎に到着','10:03　自動ドアの開口を確認','10:04　最狭部を通過して記録'],result:'駅舎を見上げる一日の始まりも、余裕のある入口です。'},
  さくら:{image:'/images/guide-gyoko-route.png',facts:[['歩道幅','1.4m以上'],['傾斜','ゆるやか'],['写真休憩','しやすい']],timeline:['10:12　二重橋の散策路へ','10:13　橋までの傾斜を確認','10:15　立ち止まれる余白を記録'],result:'桜と二重橋を眺めて寄り道しても、後ろを急かされにくい道です。'},
  あおい:{image:'/images/guide-nakadori-crowd.png',facts:[['混雑','少ない'],['ベンチ','3か所'],['通路','すれ違い可']],timeline:['10:23　仲通りの人の流れを観察','10:25　ベンチ横の幅を測定','10:27　写真を撮る場所を確認'],result:'午前なら、桜もお店も自分のペースで楽しめます。'},
  はる:{image:'/images/guide-parklet-cafe.png',facts:[['入口幅','88cm'],['段差','なし'],['車いす席','窓側可']],timeline:['11:02　ブリックスクエアへ到着','11:03　カフェの入口からレジまで移動','11:05　窓側席に横付けして確認'],result:'散策の途中で、気になったカフェへふらっと入りやすい場所です。'},
  ゆき:{image:'/images/guide-kitte-rest.png',facts:[['トイレ','1階'],['扉','自動'],['休憩席','近くにあり']],timeline:['11:18　KITTE屋上庭園へ到着','11:20　多目的トイレまで移動','11:22　眺めと休憩席の導線を記録'],result:'東京駅を眺めた後、休みたくなったときの選択肢が近い場所です。'},
  りん:{image:'/images/guide-forum.png',facts:[['エレベーター','2基'],['待ち時間','約2分'],['出口','案内あり']],timeline:['11:34　国際フォーラムに到着','11:36　ガラス棟のエレベーターへ移動','11:38　待ち時間を記録'],result:'建築を楽しみながら階をまたぐ移動も、落ち着いてできます。'},
  みずき:{image:'/images/guide-hibiya-park.png',facts:[['静かさ','高い'],['日陰','あり'],['休憩','10分向き']],timeline:['11:48　日比谷公園へ到着','11:50　座れる場所を探す','11:52　周囲の音と人通りを記録'],result:'少し疲れたら、予定を止めて呼吸を整えられる公園です。'},
  なぎ:{image:'/images/guide-artizon.png',facts:[['入口','段差なし'],['案内','見つけやすい'],['休憩','館内にあり']],timeline:['12:04　美術館の入口を確認','12:06　案内から展示室まで移動','12:08　休憩できる場所を記録'],result:'行きたかった展覧会へ、入口から館内まで迷わず入りやすい場所です。'},
  つむぎ:{image:'/images/guide-yaesu-rain.png',facts:[['最小幅','78cm'],['すれ違い','混雑時は難しい'],['雨の日','早めの移動推奨']],timeline:['12:18　八重洲地下街入口を確認','12:20　雨の日の人の流れを観察','12:22　狭い分岐で方向転換を試す'],result:'通れますが、通勤時間の地下街はすれ違いが負担に。早めに通るか地上ルートが安心です。'},
  こはる:{image:'/images/guide-midtown-return.png',facts:[['帰路','わかりやすい'],['混雑','夕方は注意'],['休憩','駅前にあり']],timeline:['12:34　東京ミッドタウン八重洲へ','12:36　駅までの帰り道を確認','12:38　夕方に休める場所を記録'],result:'旅の終わりに景色を眺めながら、帰りの体力まで残せる締め方です。'}
}
const agents = rawAgents.map(([name, role, place, status, x, y, note, tag], id) => ({ name, role, place, status, x, y, note, tag, thought: agentThoughts[name], detail: agentDetails[name], id }))
const imageFor = status => status === 'moving' ? '/images/agent-moving.png' : status === 'exploring' ? '/images/agent-exploring.png' : '/images/agent-hinata.png'
const initialTrip = { destination: '', date: '4月6日（日）', time: '10:00–16:00', twin_count: 3, wish: '' }
const defaultAvatar = '/images/agent-hinata.png'
const initialProfile = { chair: '手動車いす', width: '70', step: '2', stamina: '20', companion: 'ひとり', home: '出発地を設定してください', notes: '', priorities: ['広い通路', '休憩できるベンチ', '多目的トイレ'], avatar: defaultAvatar }

function Portrait({ agent, large = false }) {
  return <span className={`portrait ${large ? 'large' : ''}`} style={agent?.ordinal ? { borderColor: avatarTone(agent.ordinal - 1) } : undefined}><img src={agent?.avatar || imageFor(agent?.status ?? 'done')} alt="" /></span>
}

function App() {
  const [page, setPage] = useState(location.hash.slice(1) || 'home')
  const [trip, setTrip] = useState(initialTrip)
  const [profile, setProfile] = useState(() => { try { return { ...initialProfile, ...JSON.parse(localStorage.getItem('michibiki-profile') || '{}') } } catch { return initialProfile } })
  const mediaState = useAvatarSet(profile, setProfile)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [started, setStarted] = useState(0)
  const [liveInput, setLiveInput] = useState(null)
  const [detailAgent, setDetailAgent] = useState(null)
  const [tripSaved, setTripSaved] = useState(false)
  useEffect(() => { setTripSaved(false) }, [result?.mission_id])
  const displayTrip = liveInput?.trip || trip
  const displayProfile = liveInput?.profile || profile
  const travelers = travelersFor(result, displayTrip.twin_count || 3, profile.twinAvatars)
  const saveTrip = async () => {
    if (!result) return
    try { await api(`/api/missions/${result.mission_id}/save`, { method: 'POST' }); setTripSaved(true) }
    catch (err) { setError(err.message) }
  }
  const inFlight = useRef(false)
  const go = next => { location.hash = next === 'home' ? '' : next; setPage(next); window.scrollTo(0, 0) }
  const restore = async () => {
    const id = localStorage.getItem('michibiki-last-mission')
    if (!id) { setError('保存済みの依頼がありません。旅の条件を入力してください。'); return }
    setLoading(true); setStarted(Date.now()); setError('')
    try { const data = await api(`/api/missions/${encodeURIComponent(id)}`); if (!data.itinerary) throw new Error(`前の依頼の状態：${data.status}。条件画面から新しく依頼してください。`); setResult(data); setLiveInput(data.input) }
    catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }
  const dispatch = async () => {
    if (inFlight.current || loading) return
    inFlight.current = true
    const input = { trip: { ...trip }, profile: serverProfile(profile), idempotency_key: crypto.randomUUID() }
    const start = Date.now()
    setLiveInput(input); setResult(null); setError(''); setLoading(true); setStarted(start); go('map')
    try { const data = await api('/api/missions', { method: 'POST', body: input }); data.timings.browser_ms = Date.now() - start; setResult(data); localStorage.setItem('michibiki-last-mission', data.mission_id) }
    catch (err) { setError(err.message); if (err.missionId) localStorage.setItem('michibiki-last-mission', err.missionId) }
    finally { setLoading(false); inFlight.current = false }
  }
  useEffect(() => { if (['map', 'results'].includes(location.hash.slice(1)) && localStorage.getItem('michibiki-last-mission')) restore() }, [])
  useEffect(() => { const sync = () => setPage(location.hash.slice(1) || 'home'); addEventListener('hashchange', sync); return () => removeEventListener('hashchange', sync) }, [])
  useEffect(() => { const observer = new IntersectionObserver(entries => entries.forEach(entry => entry.isIntersecting && entry.target.classList.add('is-visible')), { threshold: .12 }); document.querySelectorAll('.reveal').forEach(node => observer.observe(node)); return () => observer.disconnect() }, [page])

  return <main>
    <a className="skip-link" href="#content">本文へ移動</a>
    <nav aria-label="メインナビゲーション"><button className="brand" onClick={() => go('home')} aria-label="michibiki のホームへ"><svg className="brand-mark" viewBox="0 0 34 34" aria-hidden="true"><rect x="2" y="2" width="30" height="30" rx="10" fill="#e8f7ff"/><path d="M9 10.5c3.8-3.1 10.5-2.9 13.5.7 3 3.7.8 8.1-2.3 9.8-3.2 1.7-6.7.2-7.1 4.4" fill="none" stroke="#4d85b3" strokeWidth="3" strokeLinecap="round"/><circle cx="13" cy="25" r="3.5" fill="#ef8db3"/></svg><span className="brand-word">michibiki</span><span className="brand-dot">•</span></button><div className="nav-actions"><button className="nav-button nav-profile" onClick={() => go('profile')}>あなたの条件 <span>→</span></button><button className="nav-button" onClick={() => go('plan')}>旅をつくる <span>→</span></button><button className="avatar" onClick={() => go('profile')} aria-label="あなたのプロフィール"><img src={profile.avatar} alt="" /></button></div></nav>
    <div className="page-shell" key={page}>
    {page === 'home' && <Landing onStart={() => go('plan')} />}
    {page === 'plan' && <Plan trip={trip} setTrip={setTrip} profile={profile} setProfile={setProfile} onDispatch={dispatch} onProfile={() => go('profile')} busy={loading} />}
    {page === 'profile' && <Profile profile={profile} setProfile={setProfile} mediaState={mediaState} onPlan={() => go('plan')} />}
    {page === 'map' && !result && <LiveTrip page={page} trip={displayTrip} profile={displayProfile} avatars={profile.twinAvatars} result={null} loading={loading} error={error} started={started} onNewTrip={() => go('plan')} onRestore={restore} />}
    {page === 'map' && result && <Explore trip={displayTrip} profile={displayProfile} travelers={travelers} result={result} loading={loading} error={error} started={started} onRestore={restore} onDetail={setDetailAgent} onEdit={() => go('plan')} onResults={() => go('results')} />}
    {page === 'results' && result && <Results trip={displayTrip} profile={displayProfile} travelers={travelers} result={result} saved={tripSaved || result.saved} onSave={saveTrip} onExplore={() => go('map')} onNewTrip={extra => { if (typeof extra === 'string') setTrip({ ...displayTrip, wish: `${displayTrip.wish}\n${extra}`.slice(0, 1000) }); go('plan') }} />}
    {page === 'results' && !result && <LiveTrip page={page} trip={displayTrip} profile={displayProfile} result={result} loading={loading} error={error} started={started} onNewTrip={() => go('plan')} onRestore={restore} />}
    {detailAgent && <Detail agent={detailAgent} onClose={() => setDetailAgent(null)} />}
    </div>
  </main>
}

function LegacyLanding({ onStart }) {
  return <>
    <header className="refined-hero" id="content">
      <div className="hero-photo"><img src="/images/hero-wheelchair-spring.png" alt="春の丸の内で車いすに乗り、桜を眺める旅行者" /><span>東京・丸の内の、春の一日</span></div>
      <div className="hero-message"><p className="eyebrow">A TRIP, MADE FOR YOU</p><h1>その旅を、<br /><em>あきらめる前に。</em></h1><p className="hero-lead">車いすで行けるか。休める場所はあるか。<br />あなたの条件で、仮想の自分がひと足先に体験してきます。</p><div className="hero-actions"><button className="button-primary" onClick={onStart}>旅の相談をはじめる <span>→</span></button><button className="button-text" onClick={() => document.querySelector('#solution').scrollIntoView({ behavior: 'smooth' })}>michibiki について ↓</button></div><div className="hero-proof"><span>✓ あなたの移動条件を反映</span><span>✓ 10人の仮想の自分が現地を分担</span></div></div>
    </header>
    <a className="scroll-cue" href="#why"><span>SCROLL TO DISCOVER</span><i>↓</i></a>
    <section className="intro-statement reveal" id="why"><p className="eyebrow">WHY MICHIBIKI</p><h2><span>「行ける」と書いてある。</span><span>でも、<em>わたしが過ごせるか</em>は</span><span>分からない。</span></h2><p>施設のバリアフリー情報だけでは、実際の旅は決められません。入口の幅、駅からの道、混雑のなかでの心地よさ。michibiki は、あなた自身の条件で確かめた体験を返します。</p></section>
    <section className="story-stack reveal" id="solution"><article className="story-card before"><p>これまでの旅の準備</p><b>情報を読み比べても、<br />最後は行ってみないと分からない。</b><small>「車いす可」という一言だけでは、入口、道のり、休める場所まで含めた一日を想像しにくい。</small></article><span className="story-arrow">↓</span><article className="story-card after"><p>michibiki の旅の準備</p><b>もうひとりのあなたが体験して、<br />安心できる場所を選べる。</b><small>幅・段差・休憩・混雑を、あなたの条件で確認。行き先を決めるための「実感」を届けます。</small></article></section>
    <section className="field-notes"><div className="field-notes-head reveal"><p className="eyebrow">WHAT COMES BACK</p><h2>仮想の自分が持ち帰るのは、<br />検索結果ではない。</h2><p>あなたがその場にいるとき、知りたくなることです。</p></div><div className="note-list"><article className="reveal"><span>01</span><div><b>通れる？</b><p>入口・通路・エレベーターの幅を、あなたの車いす幅で判定。</p></div><i>↗</i></article><article className="reveal"><span>02</span><div><b>過ごせる？</b><p>段差、休憩できる場所、混雑のなかでの動きやすさを記録。</p></div><i>↗</i></article><article className="reveal"><span>03</span><div><b>行きたい？</b><p>写真と短い言葉で、そこに行く自分を想像できるように。</p></div><i>↗</i></article></div></section>
    <section className="journey-steps reveal"><div><p className="eyebrow">HOW IT WORKS</p><h2>あなたの旅が、<br />決まるまで。</h2></div><ol><li><span>1</span><div><b>行きたい時間を、教えてください</b><p>行き先・滞在時間・やってみたいことを、短く入力します。</p></div></li><li><span>2</span><div><b>旅の相棒たちが、それぞれ確かめます</b><p>車いす幅、段差、疲れやすさ。プロフィールの条件を持って、10人が現地へ向かいます。</p></div></li><li><span>3</span><div><b>あなたは、体験を見て選ぶだけ</b><p>写真と短いメモから「今日はここへ行こう」と納得して決められます。</p></div></li></ol><div className="final-cta"><p>準備ができたら、あなたの次の旅を教えてください。</p><button className="button-primary" onClick={onStart}>旅の条件を入力する <span>→</span></button></div></section>
  </>
}

function Landing({ onStart }) {
  return <>
    <header className="journey-hero" id="content">
      <div className="journey-hero-copy"><p>行ってみたい。その気持ちに、もうひとりの自分を。</p><h1><span>わたしを増やして、</span><em>旅に出よう。</em></h1><p className="journey-lead"><span>気になるカフェも、推しのあの場所も。</span><span>仮想の自分に、ひと足先の冒険を。</span><span>届いた体験レポートを開けば、</span><span>「行けるかな」が「行ってみたい」に。</span></p><div className="hero-value-pills"><span>最大10人のわたし</span><span>もうひとりの自分から</span><span>あなたらしい一日</span></div><button className="journey-button" onClick={onStart}><span>旅の相棒たちを、先に送り出す</span><i>→</i></button></div>
      <figure className="journey-hero-photo"><img src="/images/hero-spring-day-trip.png" alt="旅先で過ごす自分を想像するためのイメージ" /><figcaption><b>未来のわたしから、旅のお便り。</b><span>楽しみも、気がかりも。あなたを知る旅の相棒と、次の「行ってみたい」を見つけよう。</span></figcaption></figure>
    </header>
    <section className="question-section reveal"><p>目的地を決める前に、<br />確かめたいことがある。</p><div className="question-cards"><span><i>↔</i><b>入口は通れる？</b><small>幅と段差を確認</small></span><span><i>☕</i><b>途中で休める？</b><small>席と導線を確認</small></span><span><i>◌</i><b>混んでいたら動ける？</b><small>人の流れを確認</small></span></div></section>
    <section className="case-study" id="solution"><div className="case-heading reveal"><p>4月6日、東京・丸の内。</p><h2>mioさんの「桜を見て、<br />気になるお店に寄る」一日。</h2><span>旅の相棒たちは、楽しみにしている時間を3つの場面に分けて先に歩きました。</span></div><div className="case-timeline">
      <article className="case-item reveal"><div className="case-time">10:00</div><div className="case-media"><img src="/images/tokyo-station-access.png" alt="東京駅丸の内口の広い入口を通る車いすユーザー" /></div><div className="case-copy"><p>東京駅 丸の内南口</p><h3>「ここから、ちゃんと始められる？」</h3><b>最狭部 92cm。70cmの車いすで余裕を持って通過。</b><span>ひなたが入口と自動ドアを確認。駅を出た瞬間に困らないルートです。</span></div></article>
      <article className="case-item reverse reveal"><div className="case-time">12:30</div><div className="case-media"><img src="/images/marunouchi-spring.png" alt="桜の下に広がる丸の内の歩道" /></div><div className="case-copy"><p>丸の内仲通り</p><h3>「桜を見ながら、寄り道できる？」</h3><b>平日午前は人の流れがゆるやか。ベンチ横も通りやすい。</b><span>あおいが混雑を確認。写真を撮って、気になるお店の前で立ち止まっても、後ろを気にせず過ごせます。</span></div></article>
      <article className="case-item reveal"><div className="case-time">14:00</div><div className="case-media"><img src="/images/cafe-spring-day-trip.png" alt="旅先のカフェでくつろぐ車いすユーザー" /></div><div className="case-copy"><p>春のカフェ休憩</p><h3><span>「気になるカフェに、</span><span>入れる？」</span></h3><b>入口幅 88cm。窓側の席に車いすを横付けできました。</b><span>はるが入口から席までを確認。旅の途中で見つけたカフェに、そのときの気分でふらっと入れます。</span></div></article>
    </div></section>
    <section className="answer-section reveal"><p>検索結果ではなく、<br />あなたが判断できる<strong>体験</strong>を。</p><div className="answer-cards"><article><i className="answer-icon">↔</i><span>通れる？</span><b>幅と段差を、<br />数字で持ち帰る。</b><small>最小幅 92cm / 段差 0–2cm<br />「ぎりぎり」ではなく「余裕があるか」まで分かります。</small></article><article><i className="answer-icon">☕</i><span>過ごせる？</span><b>混雑と休憩を、<br />時間で持ち帰る。</b><small>12:30 は混雑: 低 / 休憩席あり<br />疲れる前に休める場所と時間を見つけます。</small></article><article><i className="answer-icon">✿</i><span>行きたい？</span><b>写真と気持ちを、<br />旅の記憶にする。</b><small>桜の寄り道 / 入りたかったカフェ<br />条件を満たすだけでなく、行きたい理由が残ります。</small></article></div><div className="answer-action"><div><h2>次の旅で、<br />確かめたいことは何ですか？</h2><p>行き先と、したいことをひとつ書くだけ。<br />旅のガイドたちが、あなたの条件で先に歩きます。</p><div className="wish-chips"><span>桜を見たい</span><span>美術館へ行きたい</span><span>おいしいものを食べたい</span></div></div><button className="journey-button" onClick={onStart}><span>旅のガイドに相談する</span><i>→</i></button></div></section>
  </>
}

function Plan({ trip, setTrip, profile, setProfile, onDispatch, onProfile, busy = false }) {
  const [inputMethod, setInputMethod] = useState('text')
  const useConsultation = (wish, persona) => {
    update('wish', wish)
    const notes = persona.attributes.filter(a => a.domain !== 'purpose' && a.domain !== 'background' && a.confidence !== 'low').map(a => a.description).join('。')
    if (notes) setProfile(current => ({ ...current, notes: [current.notes, notes].filter(Boolean).join('。').slice(0, 500) }))
    setInputMethod('text')
  }
  const update = (key, value) => setTrip({ ...trip, [key]: value })
return <section className="plan-page" id="content"><div className="plan-progress"><span className="active">1　旅のこと</span><i /><span>2　ガイドが体験</span><i /><span>3　体験を受け取る</span></div><div className="plan-layout"><div className="plan-copy"><p className="eyebrow">あなたの次の旅</p><h1>今回の旅を、<br /><em>教えてください。</em></h1><p>行き先と、そこでしてみたいことを教えてください。あなたの移動条件を知っている旅のガイドたちが、どこを確かめるか考えます。</p><div className="profile-applied"><span>✓</span><p><b>あなたの移動条件を受け取っています</b><small>{profile.home}から出発 / 車いす幅 {profile.width}cm / 段差 {profile.step}cmまで</small></p><button type="button" onClick={onProfile}>見直す</button></div><div className="guide-roles"><span>行きたい場所を見る相棒</span><span>移動のしやすさを見る相棒</span><span>休憩場所を見る相棒</span></div></div><form className="trip-form" onSubmit={event => { event.preventDefault(); onDispatch() }}><h2>この旅で、楽しみにしていることは？</h2><label>行き先<input placeholder="例：東京・秋葉原など、行きたいエリア" value={trip.destination} onChange={event => update('destination', event.target.value)} required /></label><div className="form-row"><label>行く日<input value={trip.date} onChange={event => update('date', event.target.value)} required /></label><label>滞在時間<input value={trip.time} onChange={event => update('time', event.target.value)} required /></label></div><div className="input-method" role="group" aria-label="希望の入力方法"><button type="button" aria-pressed={inputMethod === 'text'} onClick={() => setInputMethod('text')}>文字で伝える</button><button type="button" aria-pressed={inputMethod === 'voice'} onClick={() => setInputMethod('voice')}>声で相談する</button></div>{inputMethod === 'voice' && <VoiceConsultation trip={trip} profile={profile} onUse={useConsultation} />}<label>してみたいこと<textarea placeholder="例：乃木坂46のMVに登場した東京のロケ地を巡りたい。近くのカフェでアクスタの写真も撮りたい。" value={trip.wish} onChange={event => update('wish', event.target.value)} required /></label><TwinFleet count={trip.twin_count} onChange={count => update('twin_count', count)} avatars={profile.twinAvatars} disabled={busy} /><p className="form-note">入力後、{profile.home}から旅のガイドたちが出発し、「通れる・過ごせる・行きたい」をそれぞれの場所で確かめます。</p><button className="journey-button dispatch" type="submit"><span>旅のガイドに、この旅を託す</span><i>→</i></button></form></div></section>
}

function Profile({ profile, setProfile, onPlan, mediaState }) {
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const update = (key, value) => { setProfile({ ...profile, [key]: value }); setSaved(false) }
  const toggle = item => { update('priorities', profile.priorities.includes(item) ? profile.priorities.filter(value => value !== item) : [...profile.priorities, item]) }
  const save = async () => { setSaveError(''); try { localStorage.setItem('michibiki-profile', JSON.stringify(profile)); await api('/api/profile', { method: 'PUT', body: serverProfile(profile) }); setSaved(true); window.setTimeout(() => setSaved(false), 2600) } catch (err) { setSaveError(`保存できませんでした：${err.message}`) } }
  return <section className="profile-page" id="content">
    <header className="profile-hero">
      <p className="eyebrow">YOUR MOBILITY PROFILE</p>
      <h1>あなたに近い旅を、<br /><em>つくるための条件。</em></h1>
      <p>ここで伝えたことを、旅のガイドが持って現地へ向かいます。<br />毎回入力しなくていい、あなたのための旅の下準備です。</p>
    </header>
    <div className="profile-layout">
      <aside className="profile-side"><div className="profile-photo"><img src={profile.avatar} alt="プロフィール画像" /></div><AvatarSetup profile={profile} setProfile={setProfile} mediaState={mediaState} /><h2>旅のガイドが<br />受け取ること</h2><p>「入れるか」だけでなく、どんな一日なら心地よく過ごせるかを確かめます。</p><ul><li>車いすの幅と越えられる段差</li><li>疲れずに移動できる時間</li><li>先に確認しておきたい場所</li></ul></aside>
      <form className="profile-form" onSubmit={event => { event.preventDefault(); save() }}>
        <div className="profile-form-head"><div><p className="eyebrow">BASIC CONDITIONS</p><h2>移動について</h2></div><span>必須ではありません。分かる範囲で大丈夫です。</span></div>
        <div className="profile-grid">
          <label className="departure-field">ふだんいる場所<span className="departure-input"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 10.1c0 5.2-7 10.4-7 10.4S5 15.3 5 10.1a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.3"/></svg><input value={profile.home} onChange={event => update('home', event.target.value)} placeholder="例：福岡・天神" /><i>出発地</i></span><small>旅のガイドは、ここから向かいます</small></label><label>車いすの種類<select value={profile.chair} onChange={event => update('chair', event.target.value)}><option>手動車いす</option><option>電動車いす</option><option>簡易型車いす</option><option>そのほか</option></select></label>
          <label>車いすの幅<div className="unit-input"><input inputMode="numeric" value={profile.width} onChange={event => update('width', event.target.value)} /><span>cm</span></div></label>
          <label>越えられる段差<div className="unit-input"><input inputMode="numeric" value={profile.step} onChange={event => update('step', event.target.value)} /><span>cm まで</span></div></label>
          <label>連続して移動できる時間<select value={profile.stamina} onChange={event => update('stamina', event.target.value)}><option value="10">10分まで</option><option value="20">20分まで</option><option value="30">30分まで</option><option value="60">60分まで</option></select></label>
        </div>
        <fieldset><legend>一緒に行く人</legend><div className="choice-row">{['ひとり', '家族・友人と', '介助者と'].map(item => <button type="button" className={profile.companion === item ? 'chosen' : ''} onClick={() => update('companion', item)} key={item}>{item}</button>)}</div></fieldset>
        <fieldset><legend>旅の前に、特に確かめてほしいこと</legend><p className="field-help">複数選べます。ガイドが役割を分けるヒントにします。</p><div className="priority-list">{['広い通路', '多目的トイレ', 'エレベーター', '休憩できるベンチ', '静かな場所', '屋内の移動ルート'].map(item => <button type="button" className={profile.priorities.includes(item) ? 'chosen' : ''} onClick={() => toggle(item)} key={item}><i>{profile.priorities.includes(item) ? '✓' : '+'}</i>{item}</button>)}</div></fieldset>
        <label className="note-label">ほかに、旅で気をつけてほしいこと<textarea placeholder="例：人混みが続くと疲れやすいので、途中で座れる場所を知りたい" value={profile.notes} onChange={event => update('notes', event.target.value)} /></label>
        <p className="form-note">写真は、アバター生成に同意したときだけ外部サービスへ送信します。</p>
        {saveError && <p role="alert" className="live-error">{saveError}</p>}
        <div className="profile-actions"><button type="submit" className="save-profile">{saved ? '保存しました' : '移動条件を保存する'} <span>{saved ? '✓' : '→'}</span></button><button type="button" className="profile-next" onClick={onPlan}>この条件で、旅を相談する <span>→</span></button></div>
      </form>
    </div>
  </section>
}

function Explore({ trip, profile, travelers: agents, result, loading, error, started, onRestore, onDetail, onEdit, onResults }) {
  const mapRef = useRef(null)
  const [mapSize, setMapSize] = useState({ width: Math.max(320, window.innerWidth - 36), height: Math.max(560, Math.min(window.innerHeight * .76, 820)) })
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setMapSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    if (mapRef.current) observer.observe(mapRef.current)
    return () => observer.disconnect()
  }, [])
  const mapView = mapFor(result, mapSize.width, mapSize.height)
  const [elapsed, setElapsed] = useState(0)
  const [selectedId, setSelectedId] = useState(0)
  const [showComplete, setShowComplete] = useState(true)
  const [revealedIds, setRevealedIds] = useState([])
  const [replayOrder, setReplayOrder] = useState([])
  useEffect(() => {
    setRevealedIds([]); setShowComplete(true)
    if (!result) { setReplayOrder([]); return }
    const order = result.twins.map(t => t.id)
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]
    }
    setReplayOrder(order)
    let delay = 0
    // Replay an already-returned response; these are not live backend events.
    const timers = order.map(id => {
      delay += 1000 + Math.random() * 2000
      return setTimeout(() => setRevealedIds(ids => [...ids, id]), delay)
    })
    return () => timers.forEach(clearTimeout)
  }, [result?.mission_id])
  useEffect(() => {
    if (!loading) return
    const tick = () => setElapsed(Math.floor((Date.now() - started) / 1000))
    tick(); const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [loading, started])
  const arrivalMode = false
  const activeAgents = agents.map(agent => {
    const point = mapView?.positions.get(agent.detail.reports[0]?.place_id)
    const mappedAgent = point ? { ...agent, ...point } : agent
    if (revealedIds.includes(agent.id)) return mappedAgent
    const status = error ? 'failed' : !result || replayOrder[revealedIds.length] === agent.id ? 'exploring' : 'moving'
    const thought = result ? '体験レポートをまとめています。もう少しで届きます。' : 'あなたの希望と条件をもとに、旅先を調べています。'
    return { ...mappedAgent, status, note: thought, thought }
  })
  const complete = activeAgents.filter(a => a.status === 'done').length
  const finished = !!result && revealedIds.length === agents.length
  const selected = activeAgents.find(agent => agent.id === selectedId) ?? activeAgents[0]
  const activity = revealedIds.slice(-3).reverse().map(id => agents.find(a => a.id === id)).filter(Boolean)
  return <section className="explore-page" id="content">
    <header className="map-intro"><p className="eyebrow">旅の相棒 / あなた目線のレポート</p><h1>{trip.destination}を、<em>{finished ? '先に確かめました。' : loading ? '先に体験中。' : '先に確かめよう。'}</em></h1><p>{trip.date}　{trip.time}　/　{trip.wish}</p></header>
<section className="mission"><span>あなたの依頼</span><b>{trip.destination}で「{trip.wish}」を叶えられるか</b><button onClick={onEdit}>条件を編集</button></section><SearchEvidence research={result.research} />
    {error && <section className="live-error" role="alert"><h2>結果を取得できませんでした</h2><p>{error}</p><div className="live-actions"><button className="journey-button" onClick={onEdit}>条件を見直す →</button><button className="button-text" onClick={onRestore}>保存済み結果を確認</button></div></section>}
    <section className="app map-focus" id="explore"><aside className="traveler"><div className="person"><Portrait agent={selected} large /><div><p className="eyebrow">あなたの条件</p><h2>あなたの旅</h2></div></div><div className="requirements"><span>♿ 幅 <b>{profile.width}cm</b></span><span>⌁ 段差 <b>{profile.step}cmまで</b></span></div><div className="progress"><div><span>{loading ? '旅先を調査中' : '体験の収集'}</span><b>{loading ? `${agents.length} 人` : `${complete} / ${agents.length} 完了`}</b></div><i className={loading ? 'restored-pending' : ''}><em style={{ width: loading ? '35%' : `${complete / agents.length * 100}%` }} /></i></div>{loading && <p className="restored-timing">目安 1〜2分 / 経過 {elapsed}秒<br />混雑時は最大約4分。結果が届くまで、この画面でお待ちください。</p>}<div className="activity-feed" aria-live="polite"><b>{loading ? '相棒たちが調べています' : '届いたこと'}</b>{activity.map(agent => <span key={agent.id}><i>{agent.status === 'done' ? '✓' : '◌'}</i>{agent.name}：{loading ? '希望と条件をもとに調査中' : agent.detail.timeline[0]}</span>)}</div></aside>
<section className="map" ref={mapRef} aria-label={`${trip.destination}の体験マップ`}><iframe title={`${trip.destination}のGoogleマップ`} src={`https://www.google.com/maps?q=${encodeURIComponent(mapView?.query || trip.destination)}${mapView ? `&ll=${mapView.query}&z=${mapView.zoom}` : ''}&output=embed`} /><div className="map-tint" /><span className="live map-live"><i />{loading ? '調査中' : 'レポート'}</span>{arrivalMode ? <div className="arrival-route" aria-live="polite"><p>あなたのいる場所</p><div><b>{profile.home}</b><i className="route-track"><span className="route-line" /><span className="route-guide one"><Portrait agent={agents[0]} /></span><span className="route-guide two"><Portrait agent={agents[2]} /></span><span className="route-guide three"><Portrait agent={agents[5]} /></span></i><b>東京・丸の内</b></div><strong>10人のガイドが、東京へ向かっています</strong><small>到着したガイドから、現地で体験を始めます。</small><span className="arrival-count"><i />福岡を出発　<span />東京へ到着中</span></div> : activeAgents.map(agent => <button key={agent.id} className={`agent ${agent.status} ${agent.id === selected.id ? 'selected' : ''}`} style={{ left: `${agent.x}%`, top: `${agent.y}%` }} onClick={() => setSelectedId(agent.id)} aria-label={`${agent.name}。${agent.place}で${agent.tag}`}><Portrait agent={agent} /><span className="agent-label"><b>{agent.name}</b><small>{agent.status === 'done' ? 'レポート到着' : agent.status === 'failed' ? '結果なし' : '調査中'}</small></span><span className="bubble"><b>{agent.note}</b><small>{agent.status === 'done' ? '公開情報からの仮想体験' : '結果が届くのを待っています'}</small></span></button>)}
        {finished && showComplete && <div className="complete-callout"><button className="dismiss-complete" onClick={() => setShowComplete(false)} aria-label="完了のお知らせを閉じる">×</button><span>{complete} / {agents.length} 完了</span><b>{result?.status === 'partial' ? '届いたレポートをまとめました。' : '全員のレポートがそろいました。'}</b><p>次は、あなたの一日を選びましょう。</p><button onClick={onResults}>体験をまとめて見る <i>→</i></button></div>}
        {finished && !showComplete && <button className="results-float" onClick={onResults}><span>{complete}人のレポートが届きました</span><b>一日のまとめを見る</b><i>→</i></button>}
        <div className="map-key"><span><i className="dot pink" />レポート到着</span><span><i className="dot blue" />調査中</span><span><i className="dot gray" />待機中</span></div><span className="restored-map-note">アイコンは担当の表示位置です。現在地ではありません。</span></section><Feedback agent={selected} onDetail={() => onDetail(selected)} /></section>
  </section>
}

function Feedback({ agent, onDetail }) { const done = agent.status === 'done'; return <section className="report" aria-live="polite"><p className="eyebrow">GUIDE REPORT</p><div className="report-head"><Portrait agent={agent} large /><div><h2>{agent.name} からのたより</h2><p>{agent.place} / {agent.role}</p></div></div>{agent.status === 'moving' ? <div className="loading"><span>◌</span><b>レポートを準備中</b><small>{agent.thought}</small></div> : <img src={agent.detail.image} alt={`${agent.place}を体験する旅のガイド`} />}<blockquote>「{done ? agent.detail.result : agent.status === 'exploring' ? agent.thought : agent.thought}」</blockquote><div className="judgement"><span>今回の判定</span><b>{done ? agent.tag : agent.status === 'exploring' ? '確認中' : '準備中'}</b></div><button className="detail" onClick={onDetail} disabled={!done}>{done ? '体験の詳細を見る' : '体験メモを待つ'} <span>→</span></button></section> }
function Detail({ agent, onClose }) { return <div className="overlay" onMouseDown={onClose} role="presentation"><section className="modal experience-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={event => event.stopPropagation()}><button className="close" onClick={onClose} aria-label="詳細を閉じる">×</button><p className="eyebrow">EXPERIENCE REPORT / {agent.name}</p><h2 id="detail-title">{agent.place}で、<br />あなたの条件で調べたこと。</h2><img src={agent.detail.image} alt={`${agent.place}の体験風景`} /><ExperienceReport agent={agent} /><button className="modal-close" onClick={onClose}>この体験を閉じる</button></section></div> }

function Results({ trip, profile, travelers: agents, result, saved, onSave, onExplore, onNewTrip }) {
  const [videoChoice, setVideoChoice] = useState(null)
  const recommended = itineraryCards(result, agents)
  const [openAgent, setOpenAgent] = useState(agents[0])
  const [tuning, setTuning] = useState('カフェで長めに休みたい')
  const [tuned, setTuned] = useState(false)
  const choices = ['桜をゆっくり見たい', 'カフェで長めに休みたい', '混雑をもっと避けたい']
  const response = 'この希望を条件に追記して、もう一度旅を相談できます。'
return <section className="results-page" id="content"><header className="results-hero"><p className="eyebrow">YOUR DAY, PUT TOGETHER</p><h1>{result.itinerary.hero_title || '行きたかった、その場所へ。'}<br /><em>あなたの「好き」を、一日の旅に。</em></h1><p>{trip.destination}で楽しむ、{recommended.length}か所の旅程案。<br />仮想の自分{agents.length}人が、あなたの条件で調べました。</p><button className="new-trip-top" onClick={onNewTrip}>別の旅をつくる <span>→</span></button></header><SearchEvidence research={result.research} /><section className="access-summary"><div><p className="eyebrow">ACCESSIBILITY SUMMARY</p><h2>楽しみも、気がかりも、<br /><em>旅の前に見つけよう。</em></h2><p>{result.itinerary.summary}</p></div><ul><li><i>✓</i><b>入口と店内</b><span>{agents.flatMap(a => a.detail.reports.flatMap(r => r.facts))[0] || '具体的な幅や段差は事前確認が必要です。'}</span></li><li><i>!</i><b>通行条件の確認状況</b><span>{conditionSummary(result)}</span></li><li><i>↺</i><b>休める場所</b><span>{restSummary(result)}</span></li></ul></section><section className="day-plan"><div className="plan-summary"><span>{tuned ? '調整した一日' : 'おすすめの一日'}</span><h2>{result.itinerary.title}</h2><p>{result.itinerary.summary}</p><div><b>{trip.time}</b><small>連続移動の条件 {profile.stamina}分 / 時間配分は案です</small></div></div><ol>{recommended.map((agent, index) => <li key={agent.id}><time> {String(index + 1).padStart(2, '0')}</time><img src={agent.detail.image} alt="" /><div><span>{agent.place}</span><b>{agent.detail.result}</b><p>{agent.stop.reasoning}</p><small>{agent.detail.facts[0][0]}：{agent.detail.facts[0][1]}　/　{agent.tag}</small></div></li>)}</ol></section><section className="story-video"><div><p className="eyebrow">EXPERIENCE STORY / PREVIEW</p><h2>この一日を、<br />体験の物語で見る。</h2><p>ガイドが持ち帰った写真・移動ログ・ひとことから、出発前に「その場にいる感覚」を見られる短い動画にします。</p><div className="video-choice" role="group" aria-label="旅の動画を作りますか"><button type="button" aria-pressed={videoChoice === 'create'} onClick={() => setVideoChoice('create')}>この旅を動画にしたい <span>▶</span></button><button type="button" aria-pressed={videoChoice === 'skip'} onClick={() => setVideoChoice('skip')}>今はレポートだけでいい</button></div><p className="video-choice-status" role="status">{videoChoice === 'create' ? '動画生成は準備中です。今はプレビューをお楽しみください。' : videoChoice === 'skip' ? '動画なしでも、レポートと旅程はそのまま使えます。' : '動画は任意です。レポートを読んでから選んでも大丈夫。'}</p></div><div className="video-skeleton" aria-label="体験ストーリー動画のプレビュー"><div className="video-frames"><img src="/images/tokyo-station-access.png" alt="" /><img src="/images/marunouchi-spring.png" alt="" /><img src="/images/cafe-spring-day-trip.png" alt="" /></div><div className="video-overlay"><i>▶</i><b>{result.itinerary.title}</b><small>{videoChoice === 'create' ? '動画生成機能は準備中' : videoChoice === 'skip' ? 'レポートで旅を楽しむ' : '動画を作るか選べます'}</small></div><div className="video-progress"><span /></div></div></section><section className="tuning-section"><div><p className="eyebrow">TUNE THE PLAN</p><h2>「もう少し」を、<br />旅のガイドに話す。</h2><p>時間や立ち寄る場所を変えたいときは、希望を選ぶだけ。希望を追記して、もう一度旅を相談できます。</p></div><div className="tuning-chat"><div className="chat-guide"><Portrait agent={agents[2]} /><p><b>{tuning}</b>ならこうしてみませんか？<br />{response}</p></div><div className="tuning-choices">{choices.map(choice => <button key={choice} className={tuning === choice ? 'selected' : ''} onClick={() => { setTuning(choice); setTuned(false) }}>{choice}</button>)}</div><button className="tune-button" onClick={() => onNewTrip(tuning)}>{tuned ? '希望を追記する' : 'この希望で、旅を相談し直す'} <span>{tuned ? '✓' : '→'}</span></button></div></section><section className="experience-stories"><div><p className="eyebrow">ALL EXPERIENCE NOTES</p><h2>{agents.length}人が調べた、<br />場所ごとの体験談。</h2></div><div className="story-grid">{agents.map(agent => <button key={agent.id} className={openAgent.id === agent.id ? 'selected' : ''} onClick={() => setOpenAgent(agent)}><img src={agent.detail.image} alt="" /><span>{agent.place}</span><b>{agent.role}</b><small>{agent.detail.result}</small></button>)}</div><article className="open-story"><img src={openAgent.detail.image} alt="" /><ExperienceReport agent={openAgent} /></article></section><section className="decision-panel"><div><p className="eyebrow">MAKE IT YOUR PLAN</p><h2>この一日なら、<br />行ってみたい。</h2><p>保存しておけば、出発前にまた確認できます。Google のサービスへ渡して、当日の準備にも使えます。</p></div><div className="decision-actions"><button className="save-trip" onClick={onSave}>{saved ? 'この旅を保存しました' : 'この旅を保存する'} <span>{saved ? '✓' : '→'}</span></button><a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(recommended.at(-1).place)}&waypoints=${encodeURIComponent(recommended.slice(0,-1).map(a => a.place).join('|'))}`} target="_blank" rel="noreferrer">Google マップで経路を見る <span>↗</span></a><a href={`https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(result.itinerary.title)}&details=${encodeURIComponent(result.itinerary.summary)}`} target="_blank" rel="noreferrer">Google カレンダーに追加 <span>↗</span></a><button className="export-trip" onClick={() => window.print()}>旅程を印刷・PDF保存 <span>↓</span></button></div></section><div className="results-footer-actions"><button className="back-to-map" onClick={onExplore}>{agents.length}人の体験ログに戻る <span>←</span></button><button className="new-trip-bottom" onClick={onNewTrip}>別の旅をつくる <span>→</span></button></div></section> }
createRoot(document.getElementById('root')).render(<App />)
