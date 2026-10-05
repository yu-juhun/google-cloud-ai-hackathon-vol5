# 旅行履歴機能: client_hash ベースの所有者モデルへの移行 — 設計

## 背景・スコープ

`backend/michibiki`の`profiles`/`missions`テーブルは、現在すべて`DEMO_OWNER`
(`"hackathon-demo"`という固定文字列)という単一の所有者IDで保存されている。
ログイン機能は存在せず、ブラウザ・利用者を区別する手段が全くない。

一方、同じバックエンドの`media.py`/`video.py`(アバター・音声相談・動画生成機能)は
既に`client_hash(token)`パターンを使っている: フロントエンドが`localStorage`に
ランダムトークン(UUID)を保存し、すべてのAPIリクエストで`X-Michibiki-Client`ヘッダーとして
送信、バックエンドがそれをSHA256でハッシュして「このブラウザ」を識別するキーとして使う。
実際、フロントエンドの`api()`関数(`frontend/src/api.js`)は**既に全リクエストに
このヘッダーを付けている**が、`/api/missions`・`/api/profile`はそれを無視している。

今回のスコープは、`missions`/`profiles`を同じ`client_hash`パターンに乗せ替え、
「このブラウザで過去に作った旅行の一覧」を取得できるAPIを追加すること。
実際のログイン/アカウント機能は将来の別スコープとし、今回は作らない。

## 決定/結論

### 1. 所有者識別は`client_hash`方式を再利用する

新しい識別方式を発明せず、`media.py`の`client_hash(token)`関数をそのまま
`server.py`からもインポートして使う。理由:
- フロントエンドは既に全リクエストでこのヘッダーを送っている(変更不要)
- サーバー側に状態(セッション)を持たない — トークン自体が識別子
- 将来ログイン機能を追加する際も「`client_hash` → アカウント」のマッピングを
  後から足せばよく、今回の設計を無駄にしない

### 2. スキーマ変更は不要、データ移行のみ

`profiles.owner_id`/`missions.owner_id`は元々長さ制限のない`String`型であり、
`"hackathon-demo"`をSHA256ハッシュ値(64文字)に置き換えても**テーブル定義の変更
(`migrate()`のバージョン更新)は不要**。

既存の`DEMO_OWNER`データ(実環境で既にテスト済みの1件の`mission`・`profile`・
`avatar_set`)は、削除せず、該当する実クライアントの`client_hash`に
`UPDATE`文で付け替える1回限りのデータ移行で対応する。この移行は本番適用時に
手動で一度だけ実行する(スキーマではなくデータの話なので`migrate()`には含めない)。

### 3. 新規・変更APIエンドポイント

| エンドポイント | 変更内容 |
|---|---|
| `GET /api/missions` (新規) | `client_hash`で絞った最新20件の一覧。各要素は`{id, destination, date, status, created_at}` |
| `GET /api/missions/{id}` (既存) | `DEMO_OWNER`固定 → `client_hash`で絞り込み。他人のIDを指定したら`404`(存在の有無を区別しない) |
| `POST /api/missions` (既存) | `begin_mission`が`client_hash`を`owner_id`として使う |
| `POST /api/missions/{id}/save` (既存) | 同様に`client_hash`で所有者確認 |
| `PUT /api/profile` (既存) | `save_profile`が`client_hash`で分離保存 |
| `GET /api/profile` (新規) | 再訪問時に自分のプロフィールを取得する手段がこれまで存在しなかった。見つからない場合は`404`ではなく`Profile`モデルのデフォルト値を返す(初回訪問者も正常動作する必要があるため) |

### 4. `db.py`の変更方針

`DEMO_OWNER`への内部参照を全て削除し、各関数が`owner_id`を引数として受け取る形に変える:
- `save_profile(owner_id, conditions)` (引数追加)
- `get_profile(owner_id)` (新規)
- `begin_mission(owner_id, request, retry=True)` (引数追加)
- `get_mission(owner_id, mission_id)` (既存の内部`DEMO_OWNER`フィルタを引数化)
- `list_missions(owner_id, limit=20)` (新規)
- `save_mission_trip(owner_id, mission_id)` (既存、引数化)

`DEMO_OWNER`定数自体はデータ移行の対象データを指す目的でしばらく残してよいが、
通常の読み書きパスからは参照されなくなる。

## 根拠

- 既存のavatar/video機能が同じパターンで実装・レビュー済みであり、一貫性のため
  新しい識別方式を増やさない。
- `backend/README.md`に「利用者ログイン・ユーザーごとのデータ分離はない」と
  明記されている通り、これは元々意図的なスコープ外だったが、実環境でのE2E確認中に
  「旅行履歴が復元できない」問題として表面化した。ログインを今回作らない判断は、
  既存の方針と整合する最小の変更。

## 未解決の論点

- `client_hash`はブラウザ・デバイスに紐づくため、ブラウザを変えると履歴は引き継がれない。
  将来ログイン機能を追加する際に解消する前提で、今回は許容する。
- `list_missions`は20件固定・ページネーションなし。件数が増えた場合は将来拡張する。
- `avatar_sets`/`video_jobs`は既に`client_hash`スコープ済みなので、今回の変更後は
  `profiles`/`missions`/`avatar_sets`/`video_jobs`が同じ`client_hash`で統一的に
  紐づくことになる(今回新たに整合性が生まれる副次効果であり、意図的な設計)。

## 変更しないもの

- 実際のログイン/アカウントシステム(将来スコープ)
- `avatar_sets`/`video_jobs`のテーブル定義・所有権ロジック(既に`client_hash`済み、無変更)
- `DEMO_OWNER`で作られた既存データの削除(移行するだけで、削除しない)

## 履歴

- 2026-10-06: 初版作成。実環境E2Eテスト中に発覚した「旅行履歴が復元できない」問題を
  受けてのブレインストーミングから起票。
