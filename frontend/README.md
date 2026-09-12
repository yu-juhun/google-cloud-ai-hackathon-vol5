# フロントエンド

車いす利用者向け飲食店推薦のWeb UIです。API契約の正本は
[`../api/openapi.yaml`](../api/openapi.yaml)です。

## ローカル起動（モック）

```bash
cd frontend
npm install
npm run dev
```

初期状態では架空の店舗データを返すモッククライアントを使います。外部APIキーは不要です。
`npm run generate:api` により、OpenAPIから `src/api/schema.ts` の型を再生成できます。

## バックエンドへの切り替え

`.env.local` を作成して以下を設定し、開発サーバーを再起動します。

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=https://your-cloud-run-service.run.app
```

画面コンポーネントは変更せず、`src/api/client.ts` のHTTPクライアント経由で
`POST /v1/recommendations` を呼び出します。

## 検証

```bash
npm run check
```

現在の地図は座標と選択操作を確認するための簡易表示です。実際の地図プロバイダーは、APIキーと
デプロイ方式が決まった後に `MapPanel` 内部だけを置き換えます。
