# フロントエンド

車いす利用者向け飲食店推薦のWeb UIです。API契約の正本は
[`../api/openapi.yaml`](../api/openapi.yaml)です。

## ローカル起動（推薦API）

```bash
cd frontend
npm install
npm run dev
```

初期状態では、検証用Cloud Runのbackend-apiへ直接
`POST /v1/recommendations`を送り、実際の検索・判定・推薦結果を表示します。通常は15〜40秒、
コールドスタート時はさらに数秒かかります。読み込み中は再送信ボタンを無効化します。

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=https://backend-api-378214973378.asia-northeast1.run.app
```

この接続先は2026-09-12に、ブラウザ用CORSの許可と200レスポンスを確認済みです。
フロントエンドが呼ぶのはbackend-apiだけで、個別agentのURLや認証情報は不要です。
`npm run generate:api` により、OpenAPIから `src/api/schema.ts` の型を再生成できます。

Google Mapsを表示する場合は `.env.example` を `.env.local` にコピーし、Google Maps Platformの
ブラウザ用APIキーを設定します。`.env.local` はGitの追跡対象外です。

```dotenv
VITE_GOOGLE_MAPS_API_KEY=your-browser-api-key
VITE_GOOGLE_MAPS_MAP_ID=DEMO_MAP_ID
```

ローカル開発では、Advanced Markerを利用するためのMap IDとしてGoogle公式の
`DEMO_MAP_ID`を使用できます。APIキーまたはMap IDが未設定の場合、架空地図へは戻さず、
地図を読み込めない旨を表示します。候補一覧と各店舗のGoogle Mapsリンクは引き続き利用できます。

## モックへの切り替え

`.env.local` を作成して以下を設定し、開発サーバーを再起動します。

```dotenv
VITE_API_MODE=mock
```

モックでは、福岡市内の実在店舗の名称・住所・座標・Place IDを使います。AIによる入店可否判定と
推薦理由はデモ用であり、店舗の最新状況を保証するものではありません。

## Google Maps Platformの設定

1. 課金を有効化したGoogle CloudプロジェクトでMaps JavaScript APIとPlaces API (New)を
   有効化します。
2. Webサイト用のAPIキーを作成し、API制限をMaps JavaScript APIとPlaces API (New)に限定します。
3. HTTPリファラー制限へ、ローカル開発URLと実際に利用する公開URLだけを登録します。
4. 本番用にJavaScriptのMap IDを作成します。
5. フロントエンドのビルド環境で `VITE_GOOGLE_MAPS_API_KEY` と
   `VITE_GOOGLE_MAPS_MAP_ID` を設定します。

`VITE_` で始まる値はViteのビルド時にブラウザ向けJavaScriptへ埋め込まれます。APIキーは
Secretとして隠すのではなく、API制限とHTTPリファラー制限を必ず設定してください。本番では
`DEMO_MAP_ID`を使わず、本番Google Cloudプロジェクトで作成したMap IDへ差し替えます。

マーカーを選択すると、Places APIから写真、評価、口コミ1件、電話番号、公式サイト、営業時間、
車いす対応属性を取得します。口コミと写真はGoogle Mapsの著者情報と元コンテンツへのリンクを
併記し、ブラウザや永続ストレージへキャッシュしません。周辺50m以内にパノラマがある場合は、
Street Viewも同じ画面に表示します。

`reviews`、電話番号、評価などはPlace Detailsの上位SKUに該当し、Street Viewの表示にも料金が
発生し得ます。本番ではGoogle Cloud側で予算アラートとクォータを設定してください。

- [Advanced Markerの設定](https://developers.google.com/maps/documentation/javascript/advanced-markers/start)
- [Place Classで取得できるデータ項目](https://developers.google.com/maps/documentation/javascript/place-class-data-fields)
- [Places APIの表示・帰属ポリシー](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Street View Service](https://developers.google.com/maps/documentation/javascript/streetview)
- [Google Maps Platform APIキーのセキュリティ指針](https://developers.google.com/maps/api-security-best-practices)

## 検証

```bash
npm run check
```
