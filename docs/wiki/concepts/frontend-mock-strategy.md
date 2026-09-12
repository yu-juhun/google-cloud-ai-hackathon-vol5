---
type: decision
title: "フロントエンドのモック先行開発とAPI差し替え方針"
status: stable
owner: frontend
generated:
  by: codex
  at: 2026-09-12
sources:
  - id: steering
    resource: docs/wiki/concepts/steering.md
    title: "バリアフリー飲食店 推薦エージェント: 方針・体制"
    credibility_signals: "team-internal-agreement"
  - id: recommendation-api-contract
    resource: docs/wiki/concepts/recommendation-api-contract.md
    title: "フロントエンド連携用の推薦API契約"
    credibility_signals: "team-internal-agreement"
  - id: service-topology
    resource: docs/wiki/concepts/service-topology.md
    title: "サービス構成: frontend / backend-api / search-agent / judge-agent / recommend-agent の5台体制"
    credibility_signals: "team-internal-agreement"
  - id: backend-integration-guide
    resource: docs/integration-guide.md
    title: "推薦API フロントエンド連携ガイド"
    credibility_signals: "backend-owner-provided"
  - id: places-fields
    resource: https://developers.google.com/maps/documentation/javascript/place-class-data-fields
    title: "Place Class Data Fields"
    credibility_signals: "primary-source"
  - id: places-policies
    resource: https://developers.google.com/maps/documentation/places/web-service/policies
    title: "Policies and attributions for Places API"
    credibility_signals: "primary-source"
  - id: street-view
    resource: https://developers.google.com/maps/documentation/javascript/streetview
    title: "Street View Service"
    credibility_signals: "primary-source"
---

# フロントエンドのモック先行開発とAPI差し替え方針

## 概要

Web UIは検証用backend-apiを既定で利用し、オフライン開発やUIテスト時だけモックへ切り替える。

## 決定/結論

- `frontend/` は React、TypeScript、Vite で構築する
- `api/openapi.yaml` と同じ入出力型をモックとHTTPクライアントで共有する
- `VITE_API_MODE=mock|http` で通信先を切り替え、画面コンポーネントから通信方式を分離する
- 既定値は`VITE_API_MODE=http`とし、検証用Cloud Runのbackend-apiだけを呼び出す。2026-09-12に
  ブラウザ用CORSと正常レスポンスを実呼び出しで確認済み[^backend-integration-guide]
- OpenAPIからTypeScript型を自動生成し、スキーマ更新時の型ずれをビルドで検出する
- 本番ではCloud Runのfrontendサービスとして配置し、backend-apiだけを呼び出す[^service-topology]
- モック候補は福岡市内の実在店舗の名称・住所・座標・Place IDを使う。AIによる入店可否判定と
  推薦理由はデモ用であることを画面に明示し、店舗の最新状況を保証しない
- 地図はMaps JavaScript APIと`@vis.gl/react-google-maps`を使い、推薦APIが返した候補だけを表示する
- 地図上の○・△・×マーカーと候補カードの選択状態を同期し、選択した候補の要点をInfoWindowに表示する
- ブラウザから追加の候補検索は行わず、候補の正本を推薦APIレスポンスに一本化する。選択した候補の
  Place IDに対するPlace Detailsだけをブラウザから取得する
- Place Detailsから写真・評価・口コミ・電話・Webサイト・営業時間・車いす対応属性を表示し、
  周辺50m以内にパノラマがある場合はStreet Viewを埋め込む[^places-fields][^street-view]
- Places由来の写真と口コミには著者帰属とGoogle Maps上の元コンテンツへのリンクを表示し、
  Placesデータを永続化・キャッシュしない[^places-policies]
- `VITE_GOOGLE_MAPS_API_KEY`と`VITE_GOOGLE_MAPS_MAP_ID`をビルド時に設定する。開発では
  `DEMO_MAP_ID`、本番では本番プロジェクト専用のMap IDを使う
- APIキーまたはMap IDの未設定、Maps JavaScript APIの読込失敗時は架空地図を表示せず、
  地図のエラー状態へ切り替える。候補カードとGoogle Mapsへの外部リンクは利用可能なままにする
- ブラウザ用APIキーはMaps JavaScript APIとPlaces API (New)だけにAPI制限し、開発・本番の利用URLだけに
  HTTPリファラー制限する。キー値はリポジトリへ保存しない
- 現在のbackend-apiが`AssessmentReason.result`へ店舗全体のstatus値を返した場合は、HTTPクライアント境界で
  `accessible`→`supported`、`not_accessible`→`unsupported`、`uncertain`→`unknown`へ互換変換する。
  OpenAPI契約と画面コンポーネントは変更しない[^backend-integration-guide]

## 根拠

バックエンドと並行して、条件入力、○・△・×の判定、根拠表示、地図選択のUIを検証するため[^steering]。
モックと実APIが同じ契約を使うことで、通信方式を切り替えても画面変更を不要にする
[^recommendation-api-contract]。

## 未解決の論点

- Cloud Runデプロイ用のscaffold、Dockerfile、Terraformの実装
- backend-apiの`AssessmentReason.result`をOpenAPIどおりの値へ統一した後、互換変換を削除する時期

## 履歴

- 2026-09-12: 初版作成。モック先行開発と環境変数によるHTTP API切り替えを採用
- 2026-09-12: 地図プロバイダーをGoogle Maps JavaScript APIに決定し、推薦候補との選択連動、
  障害時表示、APIキーとMap IDの運用を定義
- 2026-09-12: モック候補を実在店舗ベースへ変更。マーカー選択時のPlace Details、写真・口コミの
  帰属表示、Street View埋め込みを追加
- 2026-09-12: 検証用backend-apiへの接続を既定化。CORS・実レスポンスを確認し、判定根拠の値差異を
  HTTPクライアント境界で互換変換
