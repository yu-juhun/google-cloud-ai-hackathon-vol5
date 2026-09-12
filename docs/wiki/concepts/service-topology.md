---
type: decision
title: "サービス構成: frontend / backend-api / agent の3台体制"
status: stable
owner: infra
generated:
  by: human:juhun.yu
  at: 2026-09-12
sources:
  - id: recommendation-api-contract
    resource: docs/wiki/concepts/recommendation-api-contract.md
    title: "フロントエンド連携用の推薦API契約"
    credibility_signals: "team-internal-agreement"
  - id: verbal-agreement
    resource: docs/wiki/log.md#2026-09-12
    title: "口頭合意(3台構成)を記録"
    credibility_signals: "team-internal-agreement"
---

# サービス構成: frontend / backend-api / agent の3台体制

## 概要

統合デモ環境は、Cloud Run上の3つのサービスで構成する(口頭で合意、本ページで正式に記録)[^verbal-agreement]:

1. **frontend** — Web UI。担当: 松野さん
2. **backend-api** — フロントエンド向けの安定REST API。`api/openapi.yaml`(`POST /v1/recommendations`)が
   正本[^recommendation-api-contract]。担当: 中村さん
3. **agent** — ADK App本体。orchestrator + 検索/判定/推薦の3サブエージェント。担当: 中村さん

## 決定/結論

- frontendは`backend-api`のみを呼ぶ。ADKや`agent`サービスの存在を知らない
- `backend-api`が`agent`サービスを呼び出し、ADKの生レスポンスを`RecommendationResponse`スキーマへ整形する
  (実質的なBFFの役割を、追加の4番目のサービスを立てずに担う)
- サブエージェント単位ではCloud Runを分けない(検索/判定/推薦は`agent`サービス内のコード上のツリー)
- 詳細は [`docs/superpowers/specs/2026-09-12-integration-infra-design.md`](../../superpowers/specs/2026-09-12-integration-infra-design.md) を参照

## 根拠

- frontendがADKの内部実装(orchestrator構成、サブエージェント数等)の変更に影響されないようにするため
- `backend-api`がすでにPR#8で`api/openapi.yaml`として契約を定義済みであり、その構成を前提に統合する

## 未解決の論点

- `backend-api`↔`agent`間の認証方式(未確定。デフォルトのIDトークン認証で開始する予定)

## 履歴

- 2026-09-12: 口頭合意を正式に記録。当初は2台構成(frontend + agent)で検討していたが、
  `backend-api`をADKと分離する3台構成に変更
