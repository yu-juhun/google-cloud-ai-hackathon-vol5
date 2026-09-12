---
type: decision
title: "統合デモ環境のデプロイ済みURL"
status: stable
owner: infra
generated:
  by: human:juhun.yu
  at: 2026-09-12
sources:
  - id: service-topology
    resource: docs/wiki/concepts/service-topology.md
    title: "サービス構成: frontend / backend-api / search-agent / judge-agent / recommend-agent の5台体制"
    credibility_signals: "team-internal-agreement"
---

# 統合デモ環境のデプロイ済みURL

## 概要

5サービス構成(frontend / backend-api / search-agent / judge-agent / recommend-agent)を
共有プロジェクト`project-3bcd6d36-2338-4b32-848`へ実際にデプロイした結果[^service-topology]。
Places API実データ + Gemini判定によるエンドツーエンド動作を確認済み。

## 決定/結論

- frontend: https://frontend-52nrnvxjyq-an.a.run.app
- backend-api: https://backend-api-52nrnvxjyq-an.a.run.app
- search-agent: https://search-agent-52nrnvxjyq-an.a.run.app (非公開、backend-apiのみ呼び出し可能)
- judge-agent: https://judge-agent-52nrnvxjyq-an.a.run.app (非公開、backend-apiのみ呼び出し可能)
- recommend-agent: https://recommend-agent-52nrnvxjyq-an.a.run.app (非公開、backend-apiのみ呼び出し可能)

`curl -X POST <backend_api_url>/v1/recommendations -d '{"area":"福岡市中央区","wheelchair_width_cm":63}'`
で福岡市中央区の実店舗5件(Places API実データ + Gemini判定)を確認済み。

## 根拠

Task 3(walking skeleton実装計画)で確認済み。デプロイ過程で以下の実運用上の問題を発見・修正した:

- Cloud BuildデフォルトSAに`storage.objectViewer`/`artifactregistry.writer`権限が不足 → 付与
- `google_cloud_run_v2_service`の`ingress`属性はTerraformの設定から削除しても既存のライブ値を
  リセットしない(明示的に`INGRESS_TRAFFIC_ALL`を指定する必要がある) → 修正
- `INGRESS_TRAFFIC_INTERNAL_ONLY`はVPCネットワーキング経由の呼び出しを要求し、通常の
  Cloud-Run間HTTP呼び出しをGFEレベルで拒否する(IAM invoker制限だけで十分private) → 修正
- frontendの`npm run build`が`../api/openapi.yaml`を参照するため、Dockerビルドコンテキストを
  `frontend/`単体ではなくリポジトリルートにする必要があった → Dockerfile/ビルドコマンド修正
- `aiplatform.googleapis.com`(Vertex AI)が未有効化だったため judge-agent/recommend-agentが
  Gemini呼び出しで403 → 有効化
- frontendのCloud Runメモリ制限(256Mi)はCPU always-allocatedと組み合わせられない
  (512Mi以上が必要) → 修正

## 未解決の論点

- 認証方式(現在はデフォルトのIDトークン認証。backend-api/frontendは公開)
- Google Maps APIキーはAPI制限のみ(HTTPリファラー制限は未設定。frontend URL確定後に追加予定)

## 履歴

- 2026-09-12: 初回デプロイ完了、URLを記録。PR #12(backend-api+3エージェント)・PR #13(Google Maps統合)
  マージ後にデプロイを実施
