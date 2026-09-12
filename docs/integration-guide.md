# 推薦 API の動かし方

## この API がすること

車椅子で飲食店を利用したい人の条件を渡すと、店舗候補を探し、入店しやすさを判定して推薦します。

呼び出し先は `backend-api` だけです。フロントエンドは、検索・判定・推薦の3 agentを意識する必要はありません。

```text
フロントエンド / curl
        ↓
POST /v1/recommendations
        ↓
backend-api → search-agent → judge-agent → recommend-agent
        ↓
RecommendationResponse
```

検証用エンドポイント: [backend-api](https://backend-api-378214973378.asia-northeast1.run.app)

```text
https://backend-api-378214973378.asia-northeast1.run.app
```

現時点では API キーなしで呼べます。

## CLI で試す

ターミナルでリポジトリの場所に移動し、次を貼り付けて実行します。

```bash
curl --silent --show-error --max-time 120 \
  -X POST 'https://backend-api-378214973378.asia-northeast1.run.app/v1/recommendations' \
  -H 'Content-Type: application/json' \
  --data '{
    "area": "福岡市",
    "cuisine": "和食",
    "wheelchair_width_cm": 70,
    "prompt": "静かな店",
    "limit": 3
  }'
```

| 入力 | 必須 | 例 | 意味 |
| --- | --- | --- | --- |
| `area` | はい | `福岡市` | 探すエリア |
| `cuisine` | いいえ | `和食` | 料理ジャンル |
| `wheelchair_width_cm` | はい | `70` | 車椅子の横幅（cm） |
| `prompt` | いいえ | `静かな店` | 利用者の自由な希望 |
| `limit` | いいえ | `3` | 返す候補数。1以上 |

Places API と Gemini を呼ぶため、通常は **15〜40秒程度**かかります。Cloud Run が停止状態から起動する最初の呼び出しでは、さらに数秒かかることがあります。

成功時は `200` と候補一覧が返ります。

```json
{
  "recommendations": [
    {
      "rank": 1,
      "place_id": "ChIJ...",
      "name": "店舗名",
      "address": "住所",
      "location": { "latitude": 33.59, "longitude": 130.40 },
      "maps_url": "https://maps.google.com/...",
      "accessibility": {
        "status": "accessible",
        "confidence": "medium",
        "reasons": [
          {
            "condition": "wheelchair_width_cm",
            "result": "accessible",
            "evidence": "レビュー・写真・店舗属性をもとにした理由"
          }
        ]
      },
      "recommendation_reason": "この候補を勧める理由"
    }
  ]
}
```

`accessibility.status` は以下の3種類です。

| 値 | UI 表示 | 意味 |
| --- | --- | --- |
| `accessible` | ○ | 利用できる根拠がある |
| `uncertain` | △ | 情報が不足し、確認が必要 |
| `not_accessible` | ✕ | 利用が難しい根拠がある |

必須値がない、または形式が誤っている場合は `400` が返ります。

```json
{
  "code": "VALIDATION_ERROR",
  "message": "入力内容を確認してください。",
  "fields": [
    {
      "field": "wheelchair_width_cm",
      "code": "REQUIRED",
      "message": "wheelchair_width_cm を入力してください。"
    }
  ]
}
```

## フロントエンドから呼ぶ

### 開発時の設定

フロントエンドは初期状態ではモックを使います。Cloud Run の実 API を使う場合は、`frontend/.env.local` を作成して次を設定してください。`.env.local` はローカル専用なのでコミットしません。

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=https://backend-api-378214973378.asia-northeast1.run.app
```

設定後にフロントの開発サーバーを再起動します。Vite は起動時に環境変数を読み込むため、設定後の再起動が必要です。

```bash
cd frontend
npm install
npm run dev
```

ブラウザで表示された URL（通常は `http://localhost:5173`）を開き、検索を実行してください。ブラウザからは backend-api だけを呼び、agent の URL や API キーは使いません。

### 呼び出しコード

フォーム送信時に `fetch` を使います。読み込み中はボタンを無効化し、結果が返るまでローディング表示を出してください。

```ts
const apiBaseUrl = 'https://backend-api-378214973378.asia-northeast1.run.app';

const response = await fetch(`${apiBaseUrl}/v1/recommendations`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    area: '福岡市',
    cuisine: '和食',
    wheelchair_width_cm: 70,
    prompt: '静かな店',
    limit: 3,
  }),
});

const body = await response.json();

if (!response.ok) {
  // body.fields をフォームの各項目のエラー表示に使う
  throw new Error(body.message);
}

// body.recommendations を地図と推薦カードへ渡す
console.log(body.recommendations);
```

フロントエンドは `recommendations` だけを扱ってください。agent の URL や認証情報をフロントへ置く必要はありません。
