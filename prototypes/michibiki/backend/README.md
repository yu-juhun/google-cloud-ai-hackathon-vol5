# michibiki services

同じコンテナを `SERVICE_ROLE=backend / orchestrator / search / judge / recommend` で使う。
元構成と同じ Google GenAI SDK ベース。新しいADKランタイムやキューは追加しない。
オーケストレーター内で希望から3体の担当を計画し、独立した入力コンテキストで検索・分析を並列実行し、旅程へまとめる。

- `POST /api/missions`：条件・希望から分析。同期レスポンスにレポート・旅程・処理時間・保存IDを返す。
- `GET /api/missions/{id}`：保存済み結果。Placesの地点情報は再取得する。
- `POST /api/missions/{id}/save`：旅程の保存操作を記録する。
- `PUT /api/profile`：写真を含まない移動条件を保存する。
- `/execute`：内部Cloud Run間の処理。一般公開しない。

DBは PostgreSQL。`schema_migrations` の版1で `profiles / missions / twins / reports / itineraries` を作成する。
分析完了時にレポートと旅程を同じトランザクションで保存。冪等キー再送は二重生成しない。
画像はフロントエンドの固定画像。画像・動画生成APIと画像用Storageは未実装。

## 個人環境

`infra/terraform/backend` は既存フロント用の状態バケットに別prefixで初期化する。
project ID / 接続先 / image digest は環境変数 `TF_VAR_*` 等で指定し、Gitへ保存しない。
Cloud SQLは検証用の小さい単一ゾーン構成だが、常時料金が発生する。

APIのみ共有デモとして公開。利用者ログイン・ユーザーごとのデータ分離はない。
実際の個人情報を入力しない。プロフィール画像はブラウザ内のみ。
専門サービスはIAM認証、DB接続はCloud SQL Connector、秘密値はSecret Managerを利用する。

## ローカル

`uv sync` の後、ADCで認証した環境から `uv run uvicorn michibiki.server:app --port 8081`。
DB接続には `INSTANCE_CONNECTION_NAME / DB_USER / DB_NAME / DB_PASSWORD` を安全に環境へ設定する。
ローカルで全処理を同一プロセスで動かす場合は `LOCAL_EXECUTION=1 / GOOGLE_CLOUD_PROJECT / PLACES_API_KEY` も設定する。
`DATABASE_URL` はローカルDBの代替用。`LOCAL_EXECUTION` はデプロイには設定しない。

フロントのローカル開発は `frontend/.env.local` の `VITE_API_URL` でデプロイ済みAPIへも接続できる。
Cloud Runでは `/config.js` をNginxが `BACKEND_URL` から返す。接続先が未設定ならエラーにし、モックへはフォールバックしない。

## 確認用

`uv run pytest` は保存と契約だけ。実AIの品質評価は `tests/eval/run_pipeline.py` で実データのトレースを出し、
`agents-cli eval grade --traces eval-results/traces --config tests/eval/eval_config.yaml --output eval-results/grade`。
`eval-results` はGit・コンテナ・Cloud Buildの送信対象外。

## 初回の実環境確認（2026-10-04）

デプロイ済みフロントから「推し活・聖地巡礼」を送信し、3体の分析と旅程表示まで完了。
ブラウザでの待機は49.8秒（今回1回の実測）。プロフィール保存APIも200で応答。
Cloud SQLでプロフィール1件、対象依頼の分身3件・レポート3件・旅程1件と保存状態を確認。
保存ボタン操作後にブラウザを再読み込みし、同じ依頼IDの旅程と保存済み表示を復元できた。
聖地との関係・幅・段差・営業時間など未確認事項は残る。現地適合性を保証する完成版ではない。
