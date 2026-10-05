# michibiki 体験動画生成(Veo連携) Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this into a task-by-task implementation plan before implementing.

## 背景・スコープ

`michibiki` では、アバター画像生成(`persona-agent-backend`)と体験談生成(`backend/michibiki`の missions/itinerary/reports)はすでに実装済み。本設計は、その両方が完了した**後**にユーザーが任意で実行できる、**Veo APIによる体験動画生成**を新規に追加する。

現状、`frontend/src/main.jsx`の「story-video」セクションと`frontend/src/LiveTrip.jsx`は UI の骨組みだけがあり、「動画生成は準備中です」という固定文言を返すのみ。`backend/README.md`にも「画像・動画生成APIと画像用Storageは未実装」と明記されている — 本設計がこれを実装する最初の設計書であり、既存のコード・wikiに動画生成の定義は一切ない。

**対象シーン(C案で確定)**: アバター(分身)が登場しつつ、場所(体験談の対象地点)も映る動画。ユーザーのプロフィール条件・フィードバックが反映されることを重視する。

## 追加入力(ユーザーが動画生成前に指定するもの)

1. **対象の体験談**: どの twin(分身)の体験談を動画化するか選択。`backend/michibiki/db.py`の`finish_mission`が各twin dictに`twin["report_id"]`を直接埋め込んでいる(`reports`テーブルの1行、ミッション結果JSONの`agent.report_id`としてフロントエンドから既に参照可能)ので、新規にIDを運ぶ仕組みは不要
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
frontend (frontend/src/main.jsx の既存「story-video」セクションを実装化)
   │ POST /api/videos (体験談ID, フィードバック, スタイル, トーン, consent)
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
    Column("status", String, nullable=False),  # queued / generating / rendering / ready / failed
    Column("object_name", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

`migrate()`は既存の`if version==1 and not version==2: ... insert(2)`と同じ形で`version==2 and not version==3`の分岐を追加し、`video_jobs.create(conn, checkfirst=True)`してから`insert(migrations).values(version=3)`する。

## バックエンドAPI(`backend/michibiki`, 新規 `video.py` router, `media.py`と同じ`/api`プレフィックス)

- `POST /api/videos` — body: `{report_id, feedback, style, tone, consent}`(`x-michibiki-client`ヘッダーで`client_hash`を特定、`avatar_api.py`の`AvatarPhoto.consent`と同じ形)
  1. `consent=false`なら`400`で即終了(下記「データ要件」参照)
  2. `report_id`から体験談本文を取得(`reports`テーブル、`twin_id`経由の所有権は`missions.owner_id`からは辿れないため、v1では`DEMO_OWNER`前提の既存コードと同様に`client_hash`での所有権チェックは行わない — 既存`avatar_sets`/`consultations`は`client_hash`で所有権を区別するが、`reports`は現状誰でも読める設計になっている点に注意。本設計もその既存の非分離方針を継続するが、実装計画でこの前提が正しいか再確認すること)
  3. 同一`client_hash`+`report_id`で status が未終了(`queued`/`generating`/`rendering`)のジョブが既に存在するか確認し、あれば`409`(下記「データ要件・冪等性」参照)
  4. **関連性ガード呼び出し**(Gemini分類、ここがブロックする唯一の同期ステップ)。`on_topic=false`なら`400`+理由メッセージを返し、ここで終了(`video_jobs`には何も記録しない、video-agentもVeoも呼ばない)
  5. 通過したら`video_jobs`にstatus=`queued`で作成し、`video_rpc("/video-jobs", {...})`で`video-agent`にジョブ開始を依頼、返ってきた`provider_operation_name`を保存
  6. `{"id": record["id"], "status": "queued"}`を返す
- `WS /api/video-jobs/{job_id}/progress` — `persona/converse`と同様のIAM・origin検証パターン。メッセージスキーマは下記「WSメッセージスキーマ」節。

## video-agent API(新規サービス、`persona-agent-backend`と同じ最小構成)

- `POST /video-jobs` — body: `{report_text, feedback, style, tone, avatar_image_object_name}`。プロンプトを組み立て(体験談本文 + mobility属性のみ + スタイル + トーン + フィードバック)、Veo `generateVideos`をimage-to-videoモードで起動(アバターの最終画像を参照フレームに使用)。レスポンスで`operation_name`を返す。この呼び出し自体は同期だが、Veo操作はLROなので即座に返る。
- バックグラウンドタスク(リクエストとは独立): `operation_name`を受け取ったら、別の`asyncio.create_task`でVeoのLROを定期ポーリングし、完了したらGCSに保存して呼び出し元(`backend/michibiki`)にstatus更新を通知する必要がある — ここは実装計画で具体化する(同一プロセス内タスクか、Cloud Tasksで分離するかは実装時に判断。v1は同一プロセス内の`asyncio.create_task`で十分とする)。

## WSメッセージスキーマ

既存`/api/persona/converse`(`media.py`)と同じ`{"type": ...}`の封筒形式を踏襲する。

- 接続直後、現在のDB状態を1回送信: `{"type": "status", "status": "queued" | "generating" | "rendering"}`
- その後、`video_jobs.status`が変化するたびに同形式でpush(ポーリング間隔3秒想定、実装時に調整)
- 完了時のみ追加フィールド: `{"type": "status", "status": "ready", "video_url": "<署名付きURL>", "expires_in": 3600}`(`media.py`の`signed_assets`と同じ発行方式)
- 失敗時のみ追加フィールド: `{"type": "status", "status": "failed", "message": "動画生成に失敗しました。もう一度お試しください。"}`
- `ready`/`failed`を送った後、サーバー側で接続を閉じる
- `rejected`はこのWSには一切現れない — 関連性ガードの拒否は`POST /api/videos`の同期`400`応答のみで完結し、`video_jobs`行も`job_id`も作られないため、WS接続自体が始まらない

## フロントエンドUI設計

対象: `frontend/src/main.jsx`の既存「story-video」セクション(`videoChoice`state、`video-skeleton`/`video-frames`/`video-overlay`/`video-progress`のマークアップは既に骨組みがある)。`AvatarSetup.jsx`の既存UI規約(入力disable、`aria-live="polite"`の進行テキスト、`role="alert"`のエラー、「データの扱い」の`<details>`開示)を踏襲する。

1. `videoChoice === 'create'`を選んだ時に表示するフォーム:
   - **対象選択** `<select>`: `agents`を列挙、`value={agent.report_id}`、ラベルは`agent.place`
   - **自由形式フィードバック** `<textarea maxLength={500}>`、残り文字数表示
   - **動画スタイル** `<select>`: 事前定義3〜4択(シネマティック/ロングテイク/ナレーション付き)
   - **感情トーン** `<select>`: 事前定義3〜4択(穏やかな/ドラマチックな/落ち着いた)
   - **同意チェックボックス**: 「あなたのアバター画像とこの体験談をもとに、Veoへ送信して動画を生成することに同意します。」(`avatar-consent`と同じスタイルクラスを再利用)
   - 送信ボタン: 全項目+同意が揃うまで`disabled`、生成中も`disabled`(`AvatarSetup.jsx`の`disabled={generating}`と同じ)
2. 送信後: `POST /api/videos`→成功したら`job.id`を`profile`同様`localStorage`に保存し、WS接続を開く
3. 状態別表示(`video-progress`/`video-overlay`領域を実装化):
   - `queued`/`generating`/`rendering`: `aria-live="polite"`で"動画生成には数分かかります。生成依頼は保存されるので、ページを再読み込みしても続きから確認できます。"(アバターの既存コピーと同じ言い回し)
   - `ready`: `video-overlay`のプレースホルダー画像を`<video controls src={videoUrl} />`に置き換え
   - `failed`: `role="alert"`でエラー文言
   - `POST /api/videos`が`400`/`409`を返した場合(同意漏れ・関連性ガード拒否・重複送信): フォーム直下にインラインエラー表示、WS接続は開かない

## データ要件(同意・冪等性・保存方針・入力制約)

1. **同意(consent)**: `avatar_api.py`の`AvatarPhoto.consent`と同じ理由・同じ強制(`POST /api/videos`に`consent: bool`必須、`false`なら`400`)。アバター画像・体験談というユーザー由来データをVeoという第三者APIへ送ることへの明示同意。
2. **冪等性(重複送信防止)**: フロントは生成中ボタンを`disabled`にするが、それだけでは二重タブ操作等を防げない。バックエンドでも同一`client_hash`+`report_id`で未終了ジョブが存在する場合は新規作成を`409`で拒否する(`video_jobs`へのinsert前にSELECTで確認)。`missions`テーブルの`idempotency_key`のような専用カラムは今回は導入しない(user操作の頻度が低く、SELECTチェックで十分なため)。
3. **入力制約**: フィードバックは最大500文字。フロントの`maxLength`はUXのためであり、バックエンドでも同じ上限を再検証する(信頼できない入力として扱う)。
4. **保存期間**: `avatars/`バケットに現状GCSライフサイクルルールが無いのと同じ方針を継続し、`videos/`にも今回は削除ポリシーを導入しない(既存方針と非対称にしない)。コスト監視は運用側の手動確認に委ねる — 本番運用に進む場合の将来課題として残す。

## エラー処理まとめ

| 発生箇所 | 原因 | 挙動 |
|---|---|---|
| `POST /api/videos` | `consent=false` | `400`、フォームにインライン表示 |
| `POST /api/videos` | 関連性ガード拒否(`on_topic=false`) | `400`+理由、フォームにインライン表示。`video_jobs`には何も記録しない |
| `POST /api/videos` | 同一`report_id`で未終了ジョブが既存 | `409`、「既に生成中です」表示 |
| `POST /api/videos` | フィードバックが500文字超 | `400` |
| video-agent → Veo呼び出し | Veo API エラー/タイムアウト | `video_jobs.status = "failed"`に更新、WS経由で`{"type":"status","status":"failed",...}` |
| WS接続 | 途中で切断 | クライアントは再接続すればDBの最新状態を即座に受け取れる(ジョブ自体はDBに残っているため再送不要) |

## テスト方針

- 関連性ガードのユニットテスト: 体験談本文と無関係なフィードバック(例: 「全く違う話題」)が`on_topic=false`になることを、モックしたGemini分類レスポンスで検証
- `video_jobs`のDB操作(create/get/update)を`avatar_sets`のテストパターンに合わせてユニットテスト
- WebSocket進行状況配信: 接続→DB状態変化→pushの一連を、`persona/converse`のテストパターン(フェイクWebSocket)で検証
- Veoの実呼び出しは、**この設計書だけでは入出力の正確な形を保証しない** — 実装時にYouCam/Gemini Live同様、実APIに対して最小のスモークテストを行い、レスポンス形状・LROのポーリング間隔・平均生成時間を実測してからポーリングロジックを確定する(推測で実装しない、という既存チームの方針を継続)。
- フロントエンド: 同意チェック未済・関連性ガード拒否・重複送信(409)それぞれでフォームにインラインエラーが出ること、`ready`到達でプレースホルダーが実際の`<video>`に切り替わることを、既存`AvatarSetup.jsx`系コンポーネントのテストパターンに合わせて検証する。

## 変更しないもの

- アバター画像生成(`persona-agent-backend`)・体験談生成(`backend/michibiki`の既存missions/itineraryフロー)は無変更
- `avatar_policy.py`のdomain許可リストは無変更(Veo側で別途mobilityのみを参照するだけで、ポリシーの定義自体はavatar_policy.pyに集約しない — 両方の場所で同じ`mobility`のみという判断を明文化しているが、コード共有が必要かは実装計画で検討)

## 将来課題(今回は実装しない)

- 複数ショットの編集・つなぎ合わせ(今回は単一Veoクリップのみ)
- 動画の長さ・アスペクト比のユーザー選択
- Veo生成の再試行・キャンセルUI
