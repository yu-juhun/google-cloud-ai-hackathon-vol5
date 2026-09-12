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
共有プロジェクト`project-3bcd6d36-2338-4b32-848`へ実際にデプロイし、
Places API実データ + Gemini判定によるエンドツーエンド動作を確認した[^service-topology]。

**2026-09-12: 継続コストを避けるため、確認後にデプロイ済みリソースを全て削除済み**
(下記「現在の状態」参照)。コードとTerraform定義はリポジトリに残っているため、
`docs/superpowers/plans/2026-09-12-integration-infra-walking-skeleton.md` の
Task 0〜3を再実行すれば同じ構成を再デプロイできる。

## 決定/結論(デプロイ確認時点。現在は削除済み)

- frontend: ~~https://frontend-52nrnvxjyq-an.a.run.app~~
- backend-api: ~~https://backend-api-52nrnvxjyq-an.a.run.app~~
- search-agent: ~~https://search-agent-52nrnvxjyq-an.a.run.app~~ (非公開、backend-apiのみ呼び出し可能)
- judge-agent: ~~https://judge-agent-52nrnvxjyq-an.a.run.app~~ (非公開、backend-apiのみ呼び出し可能)
- recommend-agent: ~~https://recommend-agent-52nrnvxjyq-an.a.run.app~~ (非公開、backend-apiのみ呼び出し可能)

再デプロイ時、Cloud RunのURLは(同名サービスとして再作成すれば)通常同じ形式になるが、
保証はされない。確定した最新URLは再デプロイ後に本ページを更新すること。

`curl -X POST <backend_api_url>/v1/recommendations -d '{"area":"福岡市中央区","wheelchair_width_cm":63}'`
で福岡市中央区の実店舗5件(Places API実データ + Gemini判定)を確認済み(確認時点のログ)。

## 現在の状態(2026-09-12 削除済み)

以下を全て削除し、共有プロジェクトに継続コストが発生するリソースは残っていない:

- Cloud Run 5サービス(frontend, backend-api, search-agent, judge-agent, recommend-agent)
- 関連サービスアカウント5つ、IAMバインディング一式
- Artifact Registryリポジトリ`cloud-run-source-deploy`(ビルド済みイメージ含む)
- Secret Manager `places-api-key`
- API キー2つ(`search-agent-places-key`, `frontend-maps-browser-key`)

**残したもの**(コスト実質ゼロ、再デプロイに必要):
- Terraform state用GCSバケット`project-3bcd6d36-2338-4b32-848-tfstate`(182バイト)
- 有効化されたGCP API群(有効化自体は無課金)
- コード・Terraform定義一式(このリポジトリ)

## 再デプロイ手順

1. `docs/superpowers/plans/2026-09-12-integration-infra-walking-skeleton.md` の Task 0を実行
   (Places APIキーの再作成、Secret Managerへの再登録が必要 — キー自体は削除済みのため)
2. Task 1〜3を順に実行(Dockerビルド → Terraform apply → E2E確認)
3. 本ページのURLを新しい値で更新

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
