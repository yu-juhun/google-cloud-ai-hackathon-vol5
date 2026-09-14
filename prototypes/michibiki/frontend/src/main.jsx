import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
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
const initialTrip = { destination: '東京・丸の内', date: '4月6日（日）', time: '10:00–16:00', wish: '桜を見たい、静かなカフェに入りたい' }
const defaultAvatar = '/images/agent-hinata.png'
const initialProfile = { chair: '手動車いす', width: '70', step: '2', stamina: '20', companion: 'ひとり', home: '出発地を設定してください', notes: '', priorities: ['広い通路', '休憩できるベンチ', '多目的トイレ'], avatar: defaultAvatar }

function Portrait({ agent, large = false }) {
  return <span className={`portrait ${large ? 'large' : ''}`}><img src={imageFor(agent?.status ?? 'done')} alt="" /></span>
}

function App() {
  const [page, setPage] = useState(location.hash.slice(1) || 'home')
  const [trip, setTrip] = useState(initialTrip)
  const [profile, setProfile] = useState(() => { try { return { ...initialProfile, ...JSON.parse(localStorage.getItem('michibiki-profile') || '{}') } } catch { return initialProfile } })
  const [arrivalMode, setArrivalMode] = useState(false)
  const [detail, setDetail] = useState(null)
  const [savedTrip, setSavedTrip] = useState(false)
  const [missionComplete, setMissionComplete] = useState(false)
  const [transition, setTransition] = useState(false)
  const go = (next, animate = false) => { const move = () => { location.hash = next === 'home' ? '' : next; setPage(next); window.scrollTo(0, 0) }; if (!animate) { move(); return }; setTransition(true); setTimeout(() => { move(); setTimeout(() => setTransition(false), 650) }, 2800) }
  useEffect(() => { const sync = () => setPage(location.hash.slice(1) || 'home'); addEventListener('hashchange', sync); return () => removeEventListener('hashchange', sync) }, [])
  useEffect(() => { const observer = new IntersectionObserver(entries => entries.forEach(entry => entry.isIntersecting && entry.target.classList.add('is-visible')), { threshold: .12 }); document.querySelectorAll('.reveal').forEach(node => observer.observe(node)); return () => observer.disconnect() }, [page])

  return <main>
    <a className="skip-link" href="#content">本文へ移動</a>
    <nav aria-label="メインナビゲーション"><button className="brand" onClick={() => go('home')} aria-label="michibiki のホームへ"><svg className="brand-mark" viewBox="0 0 34 34" aria-hidden="true"><rect x="2" y="2" width="30" height="30" rx="10" fill="#e8f7ff"/><path d="M9 10.5c3.8-3.1 10.5-2.9 13.5.7 3 3.7.8 8.1-2.3 9.8-3.2 1.7-6.7.2-7.1 4.4" fill="none" stroke="#4d85b3" strokeWidth="3" strokeLinecap="round"/><circle cx="13" cy="25" r="3.5" fill="#ef8db3"/></svg><span className="brand-word">michibiki</span><span className="brand-dot">•</span></button><div className="nav-actions"><button className="nav-button nav-profile" onClick={() => go('profile')}>あなたの条件 <span>→</span></button><button className="nav-button" onClick={() => go('plan')}>旅をつくる <span>→</span></button><button className="avatar" onClick={() => go('profile')} aria-label="mioの移動条件"><img src={profile.avatar} alt="" /></button></div></nav>
    <div className="page-shell" key={page}>
    {page === 'home' && <Landing onStart={() => go('plan')} />}
    {page === 'plan' && <Plan trip={trip} setTrip={setTrip} profile={profile} onDispatch={() => { setMissionComplete(false); setArrivalMode(true); go('map', true) }} onProfile={() => go('profile')} />}
    {page === 'profile' && <Profile profile={profile} setProfile={setProfile} onPlan={() => go('plan')} />}
    {page === 'map' && <Explore trip={trip} profile={profile} arrivalMode={arrivalMode} missionComplete={missionComplete} onComplete={() => setMissionComplete(true)} onArrive={() => setArrivalMode(false)} onDetail={setDetail} onEdit={() => go('plan')} onResults={() => go('results')} />}
    {page === 'results' && <Results trip={trip} profile={profile} saved={savedTrip} onSave={() => setSavedTrip(true)} onExplore={() => go('map')} onNewTrip={() => go('plan')} />}
    </div>
    {detail && <Detail agent={detail} onClose={() => setDetail(null)} />}
    {transition && <div className="page-transition" aria-live="polite"><div><div className="dispatch-orbit"><Portrait agent={agents[0]} /><Portrait agent={agents[2]} /><Portrait agent={agents[5]} /></div><b>旅のガイドたちが、出発します</b><span>入口・桜の道・カフェ。それぞれの場所へ向かっています。</span><i className="dispatch-line" /></div></div>}
  </main>
}

function LegacyLanding({ onStart }) {
  return <>
    <header className="refined-hero" id="content">
      <div className="hero-photo"><img src="/images/hero-wheelchair-spring.png" alt="春の丸の内で車いすに乗り、桜を眺める旅行者" /><span>東京・丸の内の、春の一日</span></div>
      <div className="hero-message"><p className="eyebrow">A TRIP, MADE FOR YOU</p><h1>その旅を、<br /><em>あきらめる前に。</em></h1><p className="hero-lead">車いすで行けるか。休める場所はあるか。<br />あなたの条件で、分身がひと足先に体験してきます。</p><div className="hero-actions"><button className="button-primary" onClick={onStart}>旅の相談をはじめる <span>→</span></button><button className="button-text" onClick={() => document.querySelector('#solution').scrollIntoView({ behavior: 'smooth' })}>michibiki について ↓</button></div><div className="hero-proof"><span>✓ あなたの移動条件を反映</span><span>✓ 10人の分身が現地を分担</span></div></div>
    </header>
    <a className="scroll-cue" href="#why"><span>SCROLL TO DISCOVER</span><i>↓</i></a>
    <section className="intro-statement reveal" id="why"><p className="eyebrow">WHY MICHIBIKI</p><h2><span>「行ける」と書いてある。</span><span>でも、<em>わたしが過ごせるか</em>は</span><span>分からない。</span></h2><p>施設のバリアフリー情報だけでは、実際の旅は決められません。入口の幅、駅からの道、混雑のなかでの心地よさ。michibiki は、あなた自身の条件で確かめた体験を返します。</p></section>
    <section className="story-stack reveal" id="solution"><article className="story-card before"><p>これまでの旅の準備</p><b>情報を読み比べても、<br />最後は行ってみないと分からない。</b><small>「車いす可」という一言だけでは、入口、道のり、休める場所まで含めた一日を想像しにくい。</small></article><span className="story-arrow">↓</span><article className="story-card after"><p>michibiki の旅の準備</p><b>あなたに近い分身が体験して、<br />安心できる場所を選べる。</b><small>幅・段差・休憩・混雑を、あなたの条件で確認。行き先を決めるための「実感」を届けます。</small></article></section>
    <section className="field-notes"><div className="field-notes-head reveal"><p className="eyebrow">WHAT COMES BACK</p><h2>分身が持ち帰るのは、<br />検索結果ではない。</h2><p>あなたがその場にいるとき、知りたくなることです。</p></div><div className="note-list"><article className="reveal"><span>01</span><div><b>通れる？</b><p>入口・通路・エレベーターの幅を、あなたの車いす幅で判定。</p></div><i>↗</i></article><article className="reveal"><span>02</span><div><b>過ごせる？</b><p>段差、休憩できる場所、混雑のなかでの動きやすさを記録。</p></div><i>↗</i></article><article className="reveal"><span>03</span><div><b>行きたい？</b><p>写真と短い言葉で、そこに行く自分を想像できるように。</p></div><i>↗</i></article></div></section>
    <section className="journey-steps reveal"><div><p className="eyebrow">HOW IT WORKS</p><h2>あなたの旅が、<br />決まるまで。</h2></div><ol><li><span>1</span><div><b>行きたい時間を、教えてください</b><p>行き先・滞在時間・やってみたいことを、短く入力します。</p></div></li><li><span>2</span><div><b>分身たちが、それぞれ確かめます</b><p>車いす幅、段差、疲れやすさ。プロフィールの条件を持って、10人が現地へ向かいます。</p></div></li><li><span>3</span><div><b>あなたは、体験を見て選ぶだけ</b><p>写真と短いメモから「今日はここへ行こう」と納得して決められます。</p></div></li></ol><div className="final-cta"><p>準備ができたら、あなたの次の旅を教えてください。</p><button className="button-primary" onClick={onStart}>旅の条件を入力する <span>→</span></button></div></section>
  </>
}

function Landing({ onStart }) {
  return <>
    <header className="journey-hero" id="content">
      <div className="journey-hero-copy"><p>東京・丸の内　/　車いすで楽しむ、春の小旅行</p><h1><span>行けるだけじゃない。</span><em>行きたくなる旅へ。</em></h1><p className="journey-lead"><span>桜の下を寄り道して、おいしいコーヒーでひと休み。</span><span>あなたの条件を持った旅のガイドが、</span><span>心が動く時間まで先に体験します。</span></p><button className="journey-button" onClick={onStart}><span>次の旅を相談する</span><i>→</i></button><small>プロフィールの移動条件を使うので、入力は行き先と希望だけです。</small></div>
      <figure className="journey-hero-photo"><img src="/images/hero-spring-day-trip.png" alt="桜が咲く東京を、週末の小旅行として車いすで楽しむ人" /><figcaption><b>今日の分身レポート</b><span>丸の内仲通り｜桜の下で寄り道。最小幅 1.4m、ゆっくり写真も撮れました</span></figcaption></figure>
    </header>
    <section className="question-section reveal"><p>目的地を決める前に、<br />確かめたいことがある。</p><div className="question-cards"><span><i>↔</i><b>入口は通れる？</b><small>幅と段差を確認</small></span><span><i>☕</i><b>途中で休める？</b><small>席と導線を確認</small></span><span><i>◌</i><b>混んでいたら動ける？</b><small>人の流れを確認</small></span></div></section>
    <section className="case-study" id="solution"><div className="case-heading reveal"><p>4月6日、東京・丸の内。</p><h2>mioさんの「桜を見て、<br />気になるお店に寄る」一日。</h2><span>分身たちは、楽しみにしている時間を3つの場面に分けて先に歩きました。</span></div><div className="case-timeline">
      <article className="case-item reveal"><div className="case-time">10:00</div><div className="case-media"><img src="/images/tokyo-station-access.png" alt="東京駅丸の内口の広い入口を通る車いすユーザー" /></div><div className="case-copy"><p>東京駅 丸の内南口</p><h3>「ここから、ちゃんと始められる？」</h3><b>最狭部 92cm。70cmの車いすで余裕を持って通過。</b><span>ひなたが入口と自動ドアを確認。駅を出た瞬間に困らないルートです。</span></div></article>
      <article className="case-item reverse reveal"><div className="case-time">12:30</div><div className="case-media"><img src="/images/marunouchi-spring.png" alt="桜の下に広がる丸の内の歩道" /></div><div className="case-copy"><p>丸の内仲通り</p><h3>「桜を見ながら、寄り道できる？」</h3><b>平日午前は人の流れがゆるやか。ベンチ横も通りやすい。</b><span>あおいが混雑を確認。写真を撮って、気になるお店の前で立ち止まっても、後ろを気にせず過ごせます。</span></div></article>
      <article className="case-item reveal"><div className="case-time">14:00</div><div className="case-media"><img src="/images/cafe-spring-day-trip.png" alt="旅先のカフェでくつろぐ車いすユーザー" /></div><div className="case-copy"><p>春のカフェ休憩</p><h3><span>「気になるカフェに、</span><span>入れる？」</span></h3><b>入口幅 88cm。窓側の席に車いすを横付けできました。</b><span>はるが入口から席までを確認。旅の途中で見つけたカフェに、そのときの気分でふらっと入れます。</span></div></article>
    </div></section>
    <section className="answer-section reveal"><p>検索結果ではなく、<br />あなたが判断できる<strong>体験</strong>を。</p><div className="answer-cards"><article><i className="answer-icon">↔</i><span>通れる？</span><b>幅と段差を、<br />数字で持ち帰る。</b><small>最小幅 92cm / 段差 0–2cm<br />「ぎりぎり」ではなく「余裕があるか」まで分かります。</small></article><article><i className="answer-icon">☕</i><span>過ごせる？</span><b>混雑と休憩を、<br />時間で持ち帰る。</b><small>12:30 は混雑: 低 / 休憩席あり<br />疲れる前に休める場所と時間を見つけます。</small></article><article><i className="answer-icon">✿</i><span>行きたい？</span><b>写真と気持ちを、<br />旅の記憶にする。</b><small>桜の寄り道 / 入りたかったカフェ<br />条件を満たすだけでなく、行きたい理由が残ります。</small></article></div><div className="answer-action"><div><h2>次の旅で、<br />確かめたいことは何ですか？</h2><p>行き先と、したいことをひとつ書くだけ。<br />旅のガイドたちが、あなたの条件で先に歩きます。</p><div className="wish-chips"><span>桜を見たい</span><span>美術館へ行きたい</span><span>おいしいものを食べたい</span></div></div><button className="journey-button" onClick={onStart}><span>旅のガイドに相談する</span><i>→</i></button></div></section>
  </>
}

function Plan({ trip, setTrip, profile, onDispatch, onProfile }) {
  const update = (key, value) => setTrip({ ...trip, [key]: value })
  return <section className="plan-page" id="content"><div className="plan-progress"><span className="active">1　旅のこと</span><i /><span>2　ガイドが体験</span><i /><span>3　体験を受け取る</span></div><div className="plan-layout"><div className="plan-copy"><p className="eyebrow">あなたの次の旅</p><h1>今回の旅を、<br /><em>教えてください。</em></h1><p>行き先と、そこでしてみたいことを教えてください。あなたの移動条件を知っている旅のガイドたちが、どこを確かめるか考えます。</p><div className="profile-applied"><span>✓</span><p><b>あなたの移動条件を受け取っています</b><small>{profile.home}から出発 / 車いす幅 {profile.width}cm / 段差 {profile.step}cmまで</small></p><button type="button" onClick={onProfile}>見直す</button></div><div className="guide-roles"><span>入口を見るガイド</span><span>桜の道を見るガイド</span><span>休憩場所を見るガイド</span></div></div><form className="trip-form" onSubmit={event => { event.preventDefault(); onDispatch() }}><h2>この旅で、楽しみにしていることは？</h2><label>行き先<input value={trip.destination} onChange={event => update('destination', event.target.value)} required /></label><div className="form-row"><label>行く日<input value={trip.date} onChange={event => update('date', event.target.value)} required /></label><label>滞在時間<input value={trip.time} onChange={event => update('time', event.target.value)} required /></label></div><label>してみたいこと<textarea value={trip.wish} onChange={event => update('wish', event.target.value)} required /></label><p className="form-note">入力後、{profile.home}から旅のガイドたちが出発し、「通れる・過ごせる・行きたい」をそれぞれの場所で確かめます。</p><button className="journey-button dispatch" type="submit"><span>旅のガイドに、この旅を託す</span><i>→</i></button></form></div></section>
}

function Profile({ profile, setProfile, onPlan }) {
  const [saved, setSaved] = useState(false)
  const update = (key, value) => { setProfile({ ...profile, [key]: value }); setSaved(false) }
  const changeAvatar = event => { const file = event.target.files?.[0]; if (!file || !file.type.startsWith('image/')) return; const reader = new FileReader(); reader.onload = () => { setProfile(current => ({ ...current, avatar: String(reader.result) })); setSaved(false) }; reader.readAsDataURL(file) }
  const toggle = item => { update('priorities', profile.priorities.includes(item) ? profile.priorities.filter(value => value !== item) : [...profile.priorities, item]) }
  const save = () => { localStorage.setItem('michibiki-profile', JSON.stringify(profile)); setSaved(true); window.setTimeout(() => setSaved(false), 2600) }
  return <section className="profile-page" id="content">
    <header className="profile-hero">
      <p className="eyebrow">YOUR MOBILITY PROFILE</p>
      <h1>あなたに近い旅を、<br /><em>つくるための条件。</em></h1>
      <p>ここで伝えたことを、旅のガイドが持って現地へ向かいます。<br />毎回入力しなくていい、あなたのための旅の下準備です。</p>
    </header>
    <div className="profile-layout">
      <aside className="profile-side"><div className="profile-photo"><img src={profile.avatar} alt="プロフィール画像" /><div><label className="photo-upload">写真を選ぶ<input type="file" accept="image/*" onChange={changeAvatar} /></label><button type="button" className="photo-reset" onClick={() => update('avatar', defaultAvatar)} disabled={profile.avatar === defaultAvatar}>初期画像に戻す</button></div></div><h2>旅のガイドが<br />受け取ること</h2><p>「入れるか」だけでなく、どんな一日なら心地よく過ごせるかを確かめます。</p><ul><li>車いすの幅と越えられる段差</li><li>疲れずに移動できる時間</li><li>先に確認しておきたい場所</li></ul></aside>
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
        <div className="profile-actions"><button type="submit" className="save-profile">{saved ? '保存しました' : '移動条件を保存する'} <span>{saved ? '✓' : '→'}</span></button><button type="button" className="profile-next" onClick={onPlan}>この条件で、旅を相談する <span>→</span></button></div>
      </form>
    </div>
  </section>
}

function Explore({ trip, profile, arrivalMode, missionComplete, onComplete, onArrive, onDetail, onEdit, onResults }) {
  const [elapsed, setElapsed] = useState(missionComplete ? 20 : 0)
  const [selectedId, setSelectedId] = useState(0)
  const [showComplete, setShowComplete] = useState(true)
  useEffect(() => { if (arrivalMode || missionComplete) return; setElapsed(0); const timer = window.setInterval(() => setElapsed(value => { if (value >= 20) { window.clearInterval(timer); return value }; return value + 1 }), 1500); return () => window.clearInterval(timer) }, [arrivalMode, missionComplete])
  useEffect(() => { if (!arrivalMode) return; const timer = window.setTimeout(onArrive, 5100); return () => window.clearTimeout(timer) }, [arrivalMode, onArrive])
  useEffect(() => { const map = document.querySelector('.map iframe'); if (map) map.src = 'https://www.google.com/maps?q=Tokyo%20Station%20Imperial%20Palace%20Hibiya%20Park&z=14&output=embed' }, [])
  const complete = Math.floor(elapsed / 2)
  useEffect(() => { if (complete === 10) onComplete() }, [complete, onComplete])
  useEffect(() => { if (complete === 10) setShowComplete(true) }, [complete])
  const activeAgents = agents.map((agent, index) => ({ ...agent, status: index < complete ? 'done' : index === complete && elapsed % 2 ? 'exploring' : 'moving' }))
  const selected = activeAgents.find(agent => agent.id === selectedId) ?? activeAgents[0]
  const activity = activeAgents.filter(agent => agent.status !== 'moving').slice(-3).reverse()
  return <section className="explore-page" id="content">
    <header className="map-intro"><p className="eyebrow">旅のガイド / 現地からのレポート</p><h1>{arrivalMode ? <><span>{profile.home}から、</span><em>東京へ出発。</em></> : complete === 10 ? <><span>東京・丸の内を、</span><em>体験し終えました。</em></> : <>{trip.destination}を、<em>先に体験中。</em></>}</h1><p>{arrivalMode ? '10人のガイドが、それぞれの確認場所へ向かっています。' : `${trip.date}　${trip.time}　/　${trip.wish}`}</p></header>
    <section className="mission"><span>あなたの依頼</span><b>{trip.destination}で「{trip.wish}」を叶えられるか</b><button onClick={onEdit}>条件を編集</button></section>
    <section className="app map-focus" id="explore"><aside className="traveler"><div className="person"><Portrait agent={selected} large /><div><p className="eyebrow">あなたの条件</p><h2>mio の旅</h2></div></div><div className="requirements"><span>♿ 幅 <b>{profile.width}cm</b></span><span>⌁ 段差 <b>{profile.step}cmまで</b></span></div><div className="progress"><div><span>{arrivalMode ? '東京へ移動中' : '体験の収集'}</span><b>{arrivalMode ? '10 人' : `${complete} / 10 完了`}</b></div><i><em style={{ width: arrivalMode ? '68%' : `${complete * 10}%` }} /></i></div><div className="activity-feed" aria-live="polite"><b>いま届いたこと</b>{activity.length ? activity.map(agent => <span key={agent.id}><i>{agent.status === 'done' ? '✓' : '◌'}</i>{agent.name}：{agent.status === 'done' ? agent.detail.timeline[2] : agent.detail.timeline[1]}</span>) : <span><i>◌</i>東京に到着したガイドから確認を始めます</span>}</div></aside>
      <section className="map" aria-label="Google Maps を使った丸の内の体験マップ"><iframe title="東京・丸の内のGoogleマップ" src="https://www.google.com/maps?q=Marunouchi%20Tokyo&z=15&output=embed" /><div className="map-tint" /><span className="live map-live"><i />LIVE</span>{arrivalMode ? <div className="arrival-route" aria-live="polite"><p>あなたのいる場所</p><div><b>{profile.home}</b><i className="route-track"><span className="route-line" /><span className="route-guide one"><Portrait agent={agents[0]} /></span><span className="route-guide two"><Portrait agent={agents[2]} /></span><span className="route-guide three"><Portrait agent={agents[5]} /></span></i><b>東京・丸の内</b></div><strong>10人のガイドが、東京へ向かっています</strong><small>到着したガイドから、現地で体験を始めます。</small><span className="arrival-count"><i />福岡を出発　<span />東京へ到着中</span></div> : activeAgents.map(agent => <button key={agent.id} className={`agent ${agent.status} ${agent.id === selected.id ? 'selected' : ''}`} style={{ left: `${agent.x}%`, top: `${agent.y}%` }} onClick={() => setSelectedId(agent.id)} aria-label={`${agent.name}。${agent.place}で${agent.tag}`}><Portrait agent={agent} /><span className="agent-label"><b>{agent.name}</b><small>{agent.status === 'done' ? '体験完了' : agent.status === 'exploring' ? '体験中' : '移動中'}</small></span><span className="bubble"><b>{agent.status === 'done' ? agent.detail.result : agent.status === 'exploring' ? agent.detail.timeline[1] : agent.thought}</b><small>{agent.status === 'done' ? '体験を記録しました' : agent.status === 'exploring' ? 'いま現地で確認中' : '次の目的地へ移動中'}</small></span></button>)}
        {complete === 10 && showComplete && <div className="complete-callout"><button className="dismiss-complete" onClick={() => setShowComplete(false)} aria-label="完了のお知らせを閉じる">×</button><span>10 / 10 完了</span><b>全員の体験がそろいました。</b><p>次は、あなたの一日を選びましょう。</p><button onClick={onResults}>体験をまとめて見る <i>→</i></button></div>}
        {complete === 10 && !showComplete && <button className="results-float" onClick={onResults}><span>10人の体験がそろいました</span><b>一日のまとめを見る</b><i>→</i></button>}
        <div className="map-key"><span><i className="dot pink" />体験完了</span><span><i className="dot blue" />体験中</span><span><i className="dot gray" />移動中</span></div></section><Feedback agent={selected} onDetail={() => onDetail(selected)} /></section>
  </section>
}

function Feedback({ agent, onDetail }) { const done = agent.status === 'done'; return <section className="report" aria-live="polite"><p className="eyebrow">GUIDE REPORT</p><div className="report-head"><Portrait agent={agent} large /><div><h2>{agent.name} からのたより</h2><p>{agent.place} / {agent.role}</p></div></div>{agent.status === 'moving' ? <div className="loading"><span>◌</span><b>現地へ移動中</b><small>{agent.detail.timeline[0]}</small></div> : <img src={agent.detail.image} alt={`${agent.place}を体験する旅のガイド`} />}<blockquote>「{done ? agent.detail.result : agent.status === 'exploring' ? agent.thought : '現地に到着したら、最初の観察を届けます。'}」</blockquote><div className="judgement"><span>今回の判定</span><b>{done ? agent.tag : agent.status === 'exploring' ? '確認中' : '移動中'}</b></div><button className="detail" onClick={onDetail} disabled={!done}>{done ? '体験の詳細を見る' : '体験メモを待つ'} <span>→</span></button></section> }
function Detail({ agent, onClose }) { return <div className="overlay" onMouseDown={onClose} role="presentation"><section className="modal experience-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={event => event.stopPropagation()}><button className="close" onClick={onClose} aria-label="詳細を閉じる">×</button><p className="eyebrow">EXPERIENCE REPORT / {agent.name}</p><h2 id="detail-title">{agent.place}で、<br />実際に確かめたこと。</h2><img src={agent.detail.image} alt={`${agent.place}の体験風景`} /><p className="modal-lead">{agent.detail.result}</p><ol className="experience-log">{agent.detail.timeline.map((item, index) => <li key={item}><i>{index + 1}</i>{item}</li>)}</ol><dl>{agent.detail.facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><button className="modal-close" onClick={onClose}>この体験を閉じる</button></section></div> }

function Results({ trip, profile, saved, onSave, onExplore, onNewTrip }) {
  const recommended = agents.filter(agent => ['ひなた','さくら','はる','ゆき'].includes(agent.name))
  const [openAgent, setOpenAgent] = useState(agents[0])
  const [tuning, setTuning] = useState('桜をゆっくり見たい')
  const [tuned, setTuned] = useState(false)
  const choices = ['桜をゆっくり見たい', 'カフェで長めに休みたい', '混雑をもっと避けたい']
  const response = tuning === choices[1] ? 'カフェは窓側席で40分に。仲通りの後にKITTEで一度休む順番にします。' : tuning === choices[2] ? '出発を10:00に固定し、仲通りは11:00前に通るプランにします。' : '仲通りの滞在を30分に。写真を撮るための余白を予定に入れます。'
  useEffect(() => { document.querySelector('.results-hero h1')?.setAttribute('aria-label', '行きたい、を。今日の予定に。') }, [])
  return <section className="results-page" id="content"><header className="results-hero"><p className="eyebrow">YOUR DAY, PUT TOGETHER</p><h1>10人が歩いたから、<br /><em>行きたい一日を選べる。</em></h1><p>{profile.width}cmの車いすで、休憩をはさみながら。<br />「{trip.wish}」を叶える一日を組みました。</p><button className="new-trip-top" onClick={onNewTrip}>別の旅をつくる <span>→</span></button></header><section className="access-summary"><div><p className="eyebrow">ACCESSIBILITY SUMMARY</p><h2>大きな困りごとは、<br /><em>見つかりませんでした。</em></h2><p>{profile.width}cmの車いすで、今回選んだ4地点はすべて通行・入店できました。ただし「行ける」と「気持ちよく過ごせる」は別です。</p></div><ul><li><i>✓</i><b>入口と店内</b><span>東京駅 92cm、カフェ 88cm。どちらも余裕を持って通過。</span></li><li><i>!</i><b>気をつけること</b><span>仲通りは平日昼過ぎから人が増えます。桜を見るなら11:00前がおすすめ。</span></li><li><i>↺</i><b>休める場所</b><span>連続移動20分の手前で、KITTEの休憩席へ寄れるようにしています。</span></li></ul></section><section className="day-plan"><div className="plan-summary"><span>{tuned ? '調整した一日' : 'おすすめの一日'}</span><h2>東京駅から、桜とコーヒーへ。</h2><p>{tuned ? response : '無理なく移動できる順番と、立ち止まりたくなる場所をつなげています。'}</p><div><b>10:00–15:00</b><small>連続移動 20分以内 / 休憩 2回</small></div></div><ol>{recommended.map((agent, index) => <li key={agent.id}><time>{['10:00','10:20','11:30','13:00'][index]}</time><img src={agent.detail.image} alt="" /><div><span>{agent.place}</span><b>{agent.detail.result}</b><small>{agent.detail.facts[0][0]}：{agent.detail.facts[0][1]}　/　{agent.tag}</small></div></li>)}</ol></section><section className="story-video"><div><p className="eyebrow">EXPERIENCE STORY / PREVIEW</p><h2>この一日を、<br />体験の物語で見る。</h2><p>ガイドが持ち帰った写真・移動ログ・ひとことから、出発前に「その場にいる感覚」を見られる短い動画にします。</p><span className="cloud-note">動画生成は Google Cloud 連携で実装予定</span></div><div className="video-skeleton" aria-label="体験ストーリー動画は生成準備中"><div className="video-frames"><img src="/images/tokyo-station-access.png" alt="" /><img src="/images/marunouchi-spring.png" alt="" /><img src="/images/cafe-spring-day-trip.png" alt="" /></div><div className="video-overlay"><i>▶</i><b>東京・丸の内、春の一日</b><small>生成準備中　/　0:42</small></div><div className="video-progress"><span /></div></div></section><section className="tuning-section"><div><p className="eyebrow">TUNE THE PLAN</p><h2>「もう少し」を、<br />旅のガイドに話す。</h2><p>時間や立ち寄る場所を変えたいときは、希望を選ぶだけ。体験ログをもとに、一日の順番を整え直します。</p></div><div className="tuning-chat"><div className="chat-guide"><Portrait agent={agents[2]} /><p>mioさん、<b>{tuning}</b>ならこうしてみませんか？<br />{response}</p></div><div className="tuning-choices">{choices.map(choice => <button key={choice} className={tuning === choice ? 'selected' : ''} onClick={() => { setTuning(choice); setTuned(false) }}>{choice}</button>)}</div><button className="tune-button" onClick={() => setTuned(true)}>{tuned ? 'この内容で旅程を更新しました' : 'この条件で旅程をつくり直す'} <span>{tuned ? '✓' : '→'}</span></button></div></section><section className="experience-stories"><div><p className="eyebrow">ALL EXPERIENCE NOTES</p><h2>10人が見てきた、<br />場所ごとの体験談。</h2></div><div className="story-grid">{agents.map(agent => <button key={agent.id} className={openAgent.id === agent.id ? 'selected' : ''} onClick={() => setOpenAgent(agent)}><img src={agent.detail.image} alt="" /><span>{agent.place}</span><b>{agent.role}</b><small>{agent.detail.result}</small></button>)}</div><article className="open-story"><img src={openAgent.detail.image} alt="" /><div><p>{openAgent.name} の体験談　/　{openAgent.place}</p><h3>「{openAgent.detail.result}」</h3><ol>{openAgent.detail.timeline.map(item => <li key={item}>{item}</li>)}</ol><div>{openAgent.detail.facts.map(([label,value]) => <span key={label}><small>{label}</small><b>{value}</b></span>)}</div></div></article></section><section className="decision-panel"><div><p className="eyebrow">MAKE IT YOUR PLAN</p><h2>この一日なら、<br />行ってみたい。</h2><p>保存しておけば、出発前にまた確認できます。Google のサービスへ渡して、当日の準備にも使えます。</p></div><div className="decision-actions"><button className="save-trip" onClick={onSave}>{saved ? 'この旅を保存しました' : 'この旅を保存する'} <span>{saved ? '✓' : '→'}</span></button><a href="https://www.google.com/maps/dir/Tokyo+Station/Marunouchi+Naka-dori/KITTE+Marunouchi" target="_blank" rel="noreferrer">Google マップで経路を見る <span>↗</span></a><a href="https://calendar.google.com/calendar/render?action=TEMPLATE&text=丸の内で桜とカフェの一日&dates=20260406T010000Z/20260406T060000Z&details=michibikiの体験レポートをもとに作成" target="_blank" rel="noreferrer">Google カレンダーに追加 <span>↗</span></a><button className="export-trip" onClick={() => window.print()}>旅程を印刷・PDF保存 <span>↓</span></button></div></section><div className="results-footer-actions"><button className="back-to-map" onClick={onExplore}>10人の体験ログに戻る <span>←</span></button><button className="new-trip-bottom" onClick={onNewTrip}>別の旅をつくる <span>→</span></button></div></section> }
createRoot(document.getElementById('root')).render(<App />)
