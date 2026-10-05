# michibiki 体験動画生成(Veo連携) Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this into a task-by-task implementation plan before implementing.

## 背景・スコープ

`michibiki` では、アバター画像生成(`persona-agent-backend`)と体験談生成(`backend/michibiki`の missions/itinerary/reports)はすでに実装済み。本設計は、その両方が完了した**後**にユーザーが任意で実行できる、**Veo APIによる体験動画生成**を新規に追加する。

現状、`frontend/src/main.jsx`の「story-video」セクションと`frontend/src/LiveTrip.jsx`は UI の骨組みだけがあり、「動画生成は準備中です」という固定文言を返すのみ。`backend/README.md`にも「画像・動画生成APIと画像用Storageは未実装」と明記されている — 本設計がこれを実装する最初の設計書であり、既存のコード・wikiに動画生成の定義は一切ない。

**対象シーン(C案で確定)**: アバター(分身)が登場しつつ、場所(体験談の対象地点)も映る動画。ユーザーのプロフィール条件・フィードバックが反映されることを重視する。

## 追加入力(ユーザーが動画生成前に指定するもの)

1. **対象の体験談**: どの twin(分身)の体験談(`reports`テーブルの1レコード)を動画化するか選択
2. **自由形式フィードバック**: 自由記述のテキスト(トーン・強調したい点など)
3. **動画スタイル**: 事前定義の選択肢(例: 「シネマティック」「ロングテイク」「ナレーション付き」)
4. **感情トーン**: 事前定義の選択肢(例: 「穏やかな」「ドラマチックな」「落ち着いた」)

## トラック分析: なぜこの設計が必要か

### 脱線防止(関連性ガード)

調査済み: Model Armor(プロンプトインジェクション/ジェイルブレイク/CSAM/機密データ漏洩/Responsible AI harms の5カテゴリのみ)と Gemini `safety_settings`(有害コンテンツのハームカテゴリのみ)は、いずれも「トピック関連性」を判定する機能を持たない。Google公式ドキュメントが推奨する方法は、**軽量な分類専用のGemini呼び出し**(構造化JSON出力)を自前で組むこと([Gemini for filtering and moderation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-for-filtering-and-moderation)参照)。

→ 本設計では **2段階の検証**を行う:
1. **関連性分類**(自前のGemini呼び出し。`gemini-2.5-flash-lite`想定): `(体験談本文, ユーザーのフィードバック)` → `{"on_topic": bool, "reason": str}`。`on_topic=false`ならVeoを呼ばずに即座にエラーを返す(コスト削減・脱線防止の両方を満たす)。
2. **有害性チェック**: 関連性チェックを通過したフィードバックに対して、通常のGemini `safety_settings`を適用(別の関心事として並行させる)。

### センシティブ属性の扱い(既存方針との一貫性)

`avatar_policy.py`の`VISUALIZABLE_DOMAINS = {"mobility"}`方針(宗教・出身等をアバター外見に反映しない)と同じ理由で、Veo動画のプロンプトにも**`domain == "mobility"`の属性のみ**を反映する。他のdomain(dietary/purpose/companions/language/background/other)はVeoプロンプトに渡さない。

### 進行状況配信とジョブの耐障害性

Veo の長時間処理(Long-Running Operation)は`done: true/false`のみを返し、数値の進行率は提供しない — 「進行度(%)をリアルタイムで」という当初要望は、実際には**段階(stage)メッセージ**(`queued`→`generating`→`rendering`→`ready`/`failed`)として実装する。

WebSocket接続はジョブの生存とは独立させる: `video-agent`がクライアントの接続有無に関わらずバックグラウンドでVeoのLROをポーリングしてDBの状態を更新し、メインバックエンドのWebSocketエンドポイントは**そのDB状態変化をクライアントへ中継するだけ**の薄い層にする。これにより、タブを閉じても再度開けば同じジョブの最新状態を見られる(アバター生成で実証済みの`avatar_sets`パターンと同じ耐障害性)。

## アーキテクチャ

```
frontend (ExperienceReport.jsx 等に動画生成UIを追加)
   │ POST /api/videos (体験談ID, フィードバック, スタイル, トーン)
   │ WS   /api/video-jobs/{job_id}/progress
   ▼
backend/michibiki (server.py, 新規 video.py router)
   │ - フィードバックの関連性ガード(Gemini分類呼び出し、ここで実行)
   │ - video_jobs テーブルへの作成・DB状態の中継のみ(Veoは直接呼ばない)
   │ IAM認証付きRPC (media.py の persona_rpc と同じパターン)
   ▼
video-agent (新規 Cloud Run サービス、persona-agent-backend と同じ構成で分離)
   │ - Veo generateVideos 呼び出し(image-to-video: アバター画像 + 構成済みプロンプト)
   │ - バックグラウンドタスクでVeo LROをポーリング、video_jobs の status を更新
   │ - 完了時、動画をGCS(既存アバターバケットの videos/ prefix)に保存
   ▼
Cloud SQL (video_jobs テーブル, migration version 3)
GCS (既存 {project}-michibiki-avatars バケット, videos/{job_id} オブジェクト)
```

## データモデル

`backend/michibiki/db.py`に`avatar_sets`と同じ書き方で追加(migration version 3):

```python
video_jobs = Table(
    "video_jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("report_id", String(36), ForeignKey("reports.id"), nullable=False),
    Column("feedback", String, nullable=False),
    Column("style", String, nullable=False),
    Column("tone", String, nullable=False),
    Column("provider_operation_name", String),
    Column("status", String, nullable=False),  # queued / generating / rendering / ready / failed / rejected
    Column("rejection_reason", String),
    Column("object_name", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

`migrate()`は既存の`if version==1 and not version==2: ... insert(2)`と同じ形で`version==2 and not version==3`の分岐を追加し、`video_jobs.create(conn, checkfirst=True)`してから`insert(migrations).values(version=3)`する。

## バックエンドAPI(`backend/michibiki`, 新規 `video.py` router, `media.py`と同じ`/api`プレフィックス)

- `POST /api/videos` — body: `{report_id, feedback, style, tone}`
  1. `report_id`から体験談本文を取得(`reports`テーブル、`client_hash`で所有権確認)
  2. **関連性ガード呼び出し**(Gemini分類、ここがブロックする唯一の同期ステップ)。`on_topic=false`なら`400`+`rejection_reason`相当のメッセージを返し、ここで終了(video-agentもVeoも呼ばない)
  3. 通過したら`video_jobs`にstatus=`queued`で作成し、`video_rpc("/video-jobs", {...})`で`video-agent`にジョブ開始を依頼、返ってきた`provider_operation_name`を保存
  4. `{"id": record["id"], "status": "queued"}`を返す
- `WS /api/video-jobs/{job_id}/progress` — `persona/converse`と同様のIAM・origin検証パターン。接続直後に現在のDB状態を1回送信し、その後は`video_jobs`のstatus変化をポーリング(短い間隔、例: 3秒)して差分だけpush。status が `ready`/`failed`/`rejected` になったら、最終メッセージ(readyなら署名付きURLを`signed_assets`と同じ方式で発行)を送って接続を閉じる。

## video-agent API(新規サービス、`persona-agent-backend`と同じ最小構成)

- `POST /video-jobs` — body: `{report_text, feedback, style, tone, avatar_image_object_name}`。プロンプトを組み立て(体験談本文 + mobility属性のみ + スタイル + トーン + フィードバック)、Veo `generateVideos`をimage-to-videoモードで起動(アバターの最終画像を参照フレームに使用)。レスポンスで`operation_name`を返す。この呼び出し自体は同期だが、Veo操作はLROなので即座に返る。
- バックグラウンドタスク(リクエストとは独立): `operation_name`を受け取ったら、別の`asyncio.create_task`でVeoのLROを定期ポーリングし、完了したらGCSに保存して呼び出し元(`backend/michibiki`)にstatus更新を通知する必要がある — ここは実装計画で具体化する(同一プロセス内タスクか、Cloud Tasksで分離するかは実装時に判断。v1は同一プロセス内の`asyncio.create_task`で十分とする)。

## テスト方針

- 関連性ガードのユニットテスト: 体験談本文と無関係なフィードバック(例: 「全く違う話題」)が`on_topic=false`になることを、モックしたGemini分類レスポンスで検証
- `video_jobs`のDB操作(create/get/update)を`avatar_sets`のテストパターンに合わせてユニットテスト
- WebSocket進行状況配信: 接続→DB状態変化→pushの一連を、`persona/converse`のテストパターン(フェイクWebSocket)で検証
- Veoの実呼び出しは、**この設計書だけでは入出力の正確な形を保証しない** — 実装時にYouCam/Gemini Live同様、実APIに対して最小のスモークテストを行い、レスポンス形状・LROのポーリング間隔・平均生成時間を実測してからポーリングロジックを確定する(推測で実装しない、という既存チームの方針を継続)。

## 変更しないもの

- アバター画像生成(`persona-agent-backend`)・体験談生成(`backend/michibiki`の既存missions/itineraryフロー)は無変更
- `avatar_policy.py`のdomain許可リストは無変更(Veo側で別途mobilityのみを参照するだけで、ポリシーの定義自体はavatar_policy.pyに集約しない — 両方の場所で同じ`mobility`のみという判断を明文化しているが、コード共有が必要かは実装計画で検討)

## 将来課題(今回は実装しない)

- 複数ショットの編集・つなぎ合わせ(今回は単一Veoクリップのみ)
- 動画の長さ・アスペクト比のユーザー選択
- Veo生成の再試行・キャンセルUI
