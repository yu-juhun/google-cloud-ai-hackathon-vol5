# アバター生成: スタイルプール化 — 設計

## 背景・スコープ

現在のアバター生成は「ユーザーが1つのYouCamスタイル(`template_id`)を手動選択 → そのスタイルのバリエーションを11枚生成(1枚が自分用アイコン、10枚が旅の相棒)」という構造。

この構造を次の3点で変更する:

1. スタイル選択をユーザーの手動選択から、**重複なしのランダム10種選出**に変える。再生成時も既に使ったスタイルは避ける(クライアントごとに累積)。71種類全てを使い切ったら、既存のプールを全削除し、71種類を対象に再抽選する("v2")。
2. プロフィールアバター(自分のアイコン)を、生成直後の固定画像ではなく、**生成済みプールの中からいつでも選び直せる**ようにする。
3. 旅づくり画面で使う10体の相棒アバターを、**その時点で累積しているプール全体からランダムに10体(重複なし)選ぶ**ように変える(今は直近の1回分の生成結果に固定)。

## 決定/結論

### 1. 役割分担

- **persona-agent-backend**: YouCam呼び出しのみを担当する。「どのスタイルを何個使うか」の判断は一切持たない — 呼び出し元(backend/michibiki)から渡された`template_id`のリストをそのまま実行する、ステートレスな実行役のまま変わらない[^role-split]。
- **backend/michibiki**: 「クライアントごとに累積するアバタープール」「使用済みスタイルの追跡」「バージョン(v2)切り替え」「プロフィールアバターの選択状態」を所有する。ランダム抽選もここで行う。

この分担により、persona-agent-backendは今まで通りステートレス(Cloud SQLへのアクセスを持たない)という既存方針を変えない。

### 2. データモデル変更(`backend/michibiki/michibiki/db.py`)

スキーママイグレーションは新バージョンを追加する(現在の最新は version 4 = `video_jobs`)。このブランチは`frontend/michibiki-prototype`から分岐しており、同時期に別PR(#20、`journey_video`機能)が同じブランチにversion 5を使う形で進行中——両者がマージされる際にバージョン番号の衝突が再発する可能性が高い。マージ時に以前(PR#19統合時)と同様の手順(片方を次の空き番号へ繰り上げる)で解消する前提とし、このspecではいったんversion 5として進める。

新テーブル `avatar_pool`(累積する個別アバター1枚ごとに1行):

```python
avatar_pool = Table(
    "avatar_pool", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("template_id", String, nullable=False),
    Column("object_name", String, nullable=False),
    Column("version", Integer, nullable=False),  # 1から開始、71種類使い切ったら+1
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

既存テーブル `avatar_sets` の変更(1回の生成バッチ = 10個の個別YouCamタスクの進行状況を追跡する役割に変わる):

```python
avatar_sets = Table(
    "avatar_sets", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("provider_task_ids", json_type, nullable=False),  # [{"template_id": str, "task_id": str}, ...] 10件
    Column("status", String, nullable=False),  # generating / ready / failed
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

`provider_task_id`(単数)列は`provider_task_ids`(複数)に置き換える。既存の`assets`列は不要になる(個別アバターは`avatar_pool`側に移るため)。

既存テーブル `profiles` に列追加:

```python
Column("avatar_object_name", String)  # 現在選択中のプロフィールアバター。NULLなら未選択(デフォルトは最初に生成された1枚)
```

### 3. 生成フロー

1. `POST /api/avatars`(写真・同意)を受け取ったら、backendは自分の`avatar_pool`から`(client_hash, 現在のversion)`で使用済み`template_id`を取得する。
2. カタログ全71種類から使用済みを除いた「未使用スタイル」を数える。**10種類未満しか残っていない場合**、そのクライアントの現在versionの`avatar_pool`行を全削除し(対応するGCSオブジェクトも削除)、versionを+1して、71種類全てを「未使用」として扱う[^v2-decision]。
3. 未使用スタイルからランダムに10種類選ぶ(`random.sample`)。
4. persona-agent-backendの新エンドポイント`POST /avatar-jobs-batch`に`{photo, consent, template_ids: [...10件...]}`を渡す。persona-agent-backendは10個の`template_id`それぞれについて**個別に**`start_avatar_task(photo, mime, template_id, output_count=1)`を呼び、同時実行数3件までに制限しながら全て投げる(YouCam側の実際のレート制限は未検証— 3件同時は保守的な初期値とし、実機確認で調整する)。`{tasks: [{template_id, task_id}, ...]}`を返す。
5. backendは`avatar_sets`に新しい行(`provider_task_ids` = 上記の10件、`status="generating"`)を作る。
6. フロントエンドがポーリングする`GET /api/avatars/{set_id}`は、backend側でpersona-agent-backendの新エンドポイント`POST /avatar-results-batch`(`{tasks: [...]}`を渡す)を呼び、まだ完了していないタスクがあれば`generating`、全10件完了していれば各画像をGCSへアップロードして`avatar_pool`に10行追加、`avatar_sets.status="ready"`にする。1件でも`error`状態のタスクがあれば、そのタスクだけスキップして残り9件は成功として扱う(10種類ぴったり集められないことを許容する — 理由は未解決の論点に記載)。
7. 生成直後、そのクライアントに選択中のプロフィールアバター(`profiles.avatar_object_name`)が無ければ、新しく追加された10件の最初の1件を自動的にデフォルト選択する。既に選択済みなら変更しない。

### 4. プロフィールアバター選択

新エンドポイント:
- `GET /api/avatars/pool`: 呼び出し元の`client_hash`が持つ`avatar_pool`全件を、署名付きURL付きで返す(`avatar_sets`の`signed_assets`と同じ署名パターンを再利用)。
- `PUT /api/profile/avatar`: `{object_name}`を受け取り、それが呼び出し元の`avatar_pool`に実在することを確認した上で`profiles.avatar_object_name`を更新する。他人の`object_name`を指定しても404(存在の有無を区別しない、既存の映像機能と同じ方針[^ownership-pattern])。

口の開いた変種(mouth-open、音声相談のリップシンク用)は、今は生成バッチの最初の1枚から自動生成していたが、プロフィールアバターが後からいつでも変更できるようになるため、**生成時に先回りして作らず、`PUT /api/profile/avatar`が呼ばれた時点でその画像から生成する**(無駄な事前生成を避ける)。

### 5. フロントエンド

- `AvatarSetup.jsx`: スタイル選択`<select>`を削除(ランダム選出のため不要)。`GET /api/avatars/pool`で取得した全アバターをグリッド表示し、クリックで`PUT /api/profile/avatar`を呼んでプロフィールアバターを切り替えられるようにする。
- 旅づくり画面(`trip-view.js`の`travelersFor`が使う`avatars`配列の渡し方): `Plan`ページが`GET /api/avatars/pool`で取得したプール全体から、旅の作成(`dispatch`)ごとにクライアント側で`random`に10体を選んで`travelersFor`に渡す(新しいバックエンドエンドポイントは不要)。

## 根拠

ユーザーからの直接の要件確認による(本spec作成時のブレインストーミング)[^user-decisions]。

## 未解決の論点

- 10種類の生成タスクのうち一部が失敗した場合、「9件で妥協してreadyにする」か「全部やり直す」かは、実機でのYouCam失敗率を見てから調整が必要かもしれない。今回は前者(9件でも可)を採用。
- YouCam APIの実際の同時実行数の上限は未検証(今回は保守的に3件に設定)。実装時に実機で確認し、必要なら調整する。
- マイグレーションバージョン番号(5)はPR#20とのマージ時に衝突する可能性が高い(背景・スコープ参照)。マージ時に対応する。

## 変更しないもの

- persona-agent-backendがステートレスであること(Cloud SQLへの直接アクセスを持たない)
- YouCam APIの認証フロー・テンプレートカタログの取得方法

## 履歴

- 2026-10-11: 初版作成。

[^role-split]: backend/michibikiが状態(累積プール・使用済みスタイル・バージョン)を持ち、persona-agent-backendは実行のみという分担は、既存のvideo-agent(ステートレス)の設計方針を踏襲している。
[^v2-decision]: ユーザーとのブレインストーミングで確定: 既存71個を全削除し、同じ71スタイルを対象に再抽選する。
[^ownership-pattern]: `backend/michibiki/michibiki/video.py`の`create_video_job`が他人のreport_idに対して404を返す既存パターンと同じ。
[^user-decisions]: 本人アイコンは10スタイルの輪に含まれ後から変更可能/累積プール方式/v2は全削除して再抽選/旅ごとにプール全体からランダム10体、という4点はこのspec作成の直前にブレインストーミングで確定した。
