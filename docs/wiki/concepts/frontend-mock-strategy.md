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
---

# フロントエンドのモック先行開発とAPI差し替え方針

## 概要

推薦APIの実装完了を待たずにWeb UIを開発し、API完成後は通信層だけを差し替える。

## 決定/結論

- `frontend/` は React、TypeScript、Vite で構築する
- `api/openapi.yaml` と同じ入出力型をモックとHTTPクライアントで共有する
- `VITE_API_MODE=mock|http` で通信先を切り替え、画面コンポーネントから通信方式を分離する
- OpenAPIからTypeScript型を自動生成し、スキーマ更新時の型ずれをビルドで検出する
- 本番ではCloud Runのfrontendサービスとして配置し、backend-apiだけを呼び出す[^service-topology]
- モック店舗は実在店舗のアクセシビリティ情報と誤解されない架空データにする
- 外部の地図APIキーが未設定でも開発できるよう、当初は座標確認用の簡易地図を使う
- 実地図導入時は地図コンポーネント内部のみを置き換える

## 根拠

バックエンドと並行して、条件入力、○・△・×の判定、根拠表示、地図選択のUIを検証するため[^steering]。
モックと実APIが同じ契約を使うことで、バックエンド接続時の画面変更を抑える[^recommendation-api-contract]。

## 未解決の論点

- 本番で利用する地図プロバイダーとAPIキーの配信・制限方法
- Cloud Runデプロイ用のscaffold、Dockerfile、Terraformの実装
- 実API接続時に許可するフロントエンドオリジン(CORS)

## 履歴

- 2026-09-12: 初版作成。モック先行開発と環境変数によるHTTP API切り替えを採用
