---
type: decision
title: "サービス構成: frontend / backend-api / search-agent / judge-agent / recommend-agent の5台体制"
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
    title: "口頭合意(5台構成への変更)を記録"
    credibility_signals: "team-internal-agreement"
---

# サービス構成: frontend / backend-api / search-agent / judge-agent / recommend-agent の5台体制

## 概要

統合デモ環境は、Cloud Run上の5つのサービスで構成する(口頭で合意、本ページで正式に記録)[^verbal-agreement]。
本ページはこれ以前の「3台体制(agentサービス1つに検索/判定/推薦をまとめる)」という決定を上書きする:

1. **frontend** — Web UI。担当: 松野さん
2. **backend-api** — フロントエンド向けの安定REST API。`api/openapi.yaml`(`POST /v1/recommendations`)が
   正本[^recommendation-api-contract]。担当: 中村さん
3. **search-agent** — 候補店舗の検索。担当: 中村さん
4. **judge-agent** — バリアフリー度の判定。担当: 中村さん
5. **recommend-agent** — 推薦理由の生成。担当: 中村さん

## 決定/結論

- frontendは`backend-api`のみを呼ぶ。3つのagentサービスの存在を知らない
- オーケストレーション(search-agent → judge-agent → recommend-agentの呼び出し順序制御)は
  `backend-api`が担う。専用のorchestratorサービスは追加しない(4番目のサービスを立てない)
- `backend-api`は3つのagentサービスをそれぞれHTTPで呼び出し、結果を`RecommendationResponse`
  スキーマへ整形する
- search-agent / judge-agent / recommend-agentは、それぞれ独立したADK App(または軽量HTTPサービス)
  として実装し、個別にCloud Runへデプロイする(以前の決定「サブエージェント単位ではCloud Runを
  分けない」を撤回)
- 詳細は [`docs/superpowers/specs/2026-09-12-integration-infra-design.md`](../../superpowers/specs/2026-09-12-integration-infra-design.md) を参照

## 根拠

- frontendがADKの内部実装(agentサービスの数・構成の変更)に影響されないようにするため
- `backend-api`がすでにPR#8で`api/openapi.yaml`として契約を定義済みであり、その構成を前提に統合する
- 各agentを独立サービスにすることで、担当者が個人GCPプロジェクトで各エージェントを個別に検証・
  デプロイしやすくする(口頭合意の主な理由)

## 未解決の論点

- `backend-api`↔各agentサービス間の認証方式(未確定。デフォルトのIDトークン認証で開始する予定)
- 3つのagentサービス間でのタイムアウト・リトライ方針(未確定)

## 履歴

- 2026-09-12: 口頭合意を正式に記録。当初は2台構成(frontend + agent)で検討し、
  次に`backend-api`をADKと分離する3台構成(frontend / backend-api / agent)に変更していたが、
  実装着手後にsearch/judge/recommendをそれぞれ独立したCloud Runサービスに分離する5台構成へ
  再度変更。理由は個人GCPプロジェクトでの検証しやすさ
