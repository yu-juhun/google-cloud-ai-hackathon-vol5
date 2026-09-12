# 統合デモ環境 インフラ設計

## 目的

車椅子ユーザー向けバリアフリー飲食店推薦エージェントを、共有GCPプロジェクトにデプロイし、
チームメンバー全員が「自分の担当エージェントが最終的にどこに・どうハマるか」を理解した上で、
各自の個人GCPプロジェクトで開発・検証できるようにする。

本docは`docs/wiki/concepts/steering.md`(方針)を前提とし、その実装レベルの詳細を定める。
`docs/wiki/`のOKF規約に沿った知識ではなく実装計画のため、通常のspecとしてここに置く。

## 全体アーキテクチャ

3台構成(frontend / backend API / Agent、それぞれ1台のCloud Run)は口頭で合意済みの内容を
本specと [`docs/wiki/concepts/service-topology.md`](../wiki/concepts/service-topology.md)(決定ページ)に記録する。

```
┌───────────────────────────────────────────────────────────────────────┐
│ project-3bcd6d36-2338-4b32-848 (共有GCP・統合デモ環境)                   │
│                                                                       │
│ ┌─────────────┐  HTTP  ┌──────────────────┐  HTTP  ┌───────────────┐ │
│ │ Cloud Run    │───────▶│ Cloud Run         │───────▶│ Cloud Run      │ │
│ │ frontend     │        │ backend-api        │        │ agent          │ │
│ │ (Web UI)     │        │ POST /v1/          │        │ (ADK App)      │ │
│ │ 担当: 松野さん │        │ recommendations     │        │  ├─ orchestrator│ │
│ │              │        │ 契約: api/openapi.yaml│        │  ├─ agents/search│ │
│ │              │        │ 担当: 中村さん        │        │  ├─ agents/judge│ │
│ │              │        │                     │        │  └─ agents/recommend│ │
│ └─────────────┘        └──────────────────┘        │ 担当: 中村さん   │ │
│                                                       └───────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
        ▲ 各自の個人GCPプロジェクトで同じ構成をローカル/デプロイして検証
        │ (下記「個人プロジェクトでの検証」参照)
   各メンバーの開発環境
```

- **frontend**: Web UI。`backend-api`の`/v1/recommendations`のみを呼ぶ。ADKや`agent`サービスの存在を知らない
- **backend-api**: フロントエンド向けの安定REST API。`api/openapi.yaml`が正本。内部で`agent`サービスを呼び出し、
  ADKの生のレスポンスを`RecommendationResponse`スキーマに整形する
- **agent**: ADK App本体。orchestrator + 3サブエージェント(検索/判定/推薦)をコード上のツリーとして持つ
  (サブエージェント単位ではCloud Runを分けない — 2026-09-12のキックオフ会議で確定した統合単位)
- 3サービスとも`agents-cli`でスキャフォルドし、デプロイ先は`--deployment-target cloud_run`固定(初期版)。
  Agent Runtimeへの切替は後日、必要になった時点で`agents-cli scaffold enhance --deployment-target agent_runtime`で対応する

## リポジトリ構成(追加分)

```
agent/                          # agents-cli scaffold create で生成(ADK App)
├── agents/
│   ├── orchestrator/          # 呼び出し順序: search → judge → recommend
│   ├── search/                # 担当: 中村さん(バックエンドエンジニア)
│   ├── judge/                 # 担当: 中村さん(バックエンドエンジニア)
│   └── recommend/             # 担当: 中村さん(バックエンドエンジニア)
├── deployment/terraform/      # agents-cli infra が生成。手動gcloudでの変更は禁止
├── tests/
└── Dockerfile

backend-api/                     # 別途 agents-cli scaffold create --deployment-target cloud_run
├── api/openapi.yaml            # 正本。frontendとの契約(すでにPR#8でマージ済み)
├── src/                        # OpenAPIをagentサービス呼び出しに変換する実装。担当: 中村さん
├── deployment/terraform/
└── Dockerfile

frontend/                       # 別途 agents-cli scaffold create --deployment-target cloud_run
├── src/                        # 担当: 松野さん(学生)
├── deployment/terraform/
└── Dockerfile
```

既存の`docs/wiki/`, `docs/superpowers/`, `AGENTS.md`, ルートの`api/openapi.yaml`等はそのまま維持する。

## サービス間インターフェース

- **frontend → backend-api**: `api/openapi.yaml`(`POST /v1/recommendations`)が正本。すでにPR#8で
  マージ済みのため、これ以上このspecでは再定義しない
- **backend-api → agent**: ADKのFastAPI標準エンドポイント(`/apps/orchestrator/invoke`相当)を呼ぶ。
  詳細スキーマは`agents/orchestrator/`内のコード(Pythonの型定義)を正とし、backend-api側が
  `RecommendationResponse`への変換を担う。この境界のスキーマが変わった場合は
  `docs/wiki/concepts/`に`type: decision`ページを追加して記録すること

## GCPインフラ(Terraform管理・`agents-cli`生成分)

- 対象プロジェクト: `project-3bcd6d36-2338-4b32-848`(課金有効・確認済み)
- 有効化するAPI: `run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`
  (`agents-cli infra single-project`が自動有効化)
- サービスアカウント: `app_sa`(3つ、frontend / backend-api / agent サービスそれぞれに分ける)
- Secret Manager: Google Places APIキー等をここで管理し、`agents-cli deploy --secrets`で注入する
  (`.env`やコードへの直書きは禁止 — `steering.md`の秘密情報ルールと一致)
- Terraformの生成・適用は`agents-cli infra single-project`(単一プロジェクト構成、staging分離なし)を用いる
- **CI/CD**: mainへのマージをトリガーに共有プロジェクトへ自動デプロイするGitHub Actionsを設定する
  (「作業準備の一環として今のうちに確立する」と合意済み)。`agents-cli infra cicd`が前提とする
  staging→prod 2段階パイプラインは単一デモ環境の方針に合わないため使わず、シンプルな
  1ジョブワークフロー(`main push` → `agents-cli deploy --project project-3bcd6d36-2338-4b32-848
  --no-confirm-project`をfrontend/backend-api/agentの3サービスそれぞれに対して実行)で構成する

## 個人プロジェクトでの検証(他メンバー向け)

各メンバーは以下の手順で、自分の個人GCPプロジェクトに同じ構成を再現して開発・検証できる:

1. `uvx google-agents-cli setup`(README.md記載のセットアップ、既に導入済み前提)
2. 担当ディレクトリ(`agent/agents/search/`等、`backend-api/`、または`frontend/`)で
   `agents-cli scaffold enhance . --deployment-target cloud_run` していることを確認
   (このspecに沿ったscaffoldなら不要)
3. `agents-cli deploy --project <自分の個人GCPプロジェクトID> --no-confirm-project` で自分のプロジェクトにデプロイして動作確認
4. 動作確認できたら、実装をこのリポジトリの該当ディレクトリへPRとして提出する
   (mainへマージされると、GitHub Actionsが共有プロジェクトへ自動デプロイする。手動で
   `agents-cli deploy`を共有プロジェクトに対して打つ必要はない)
5. サービス間インターフェース(上記契約)を変えずに実装すれば、他の担当者の作業をブロックしない

## 今回のスコープに含めないもの

- `agents-cli infra cicd`によるstaging→prod 2段階パイプライン(単一デモ環境の方針のため不要)
- Agent Runtimeへの切替(必要になった時点で再検討)
- Agent Gateway / Semantic Governance Policies(VPC-SC等の高度な要件が出た場合のみ検討)

## オープンな論点

- frontend↔backend-api、backend-api↔agent、それぞれの認証方式(Cloud Run標準のIDトークン認証か、
  IAPか)は未確定。まずは`--no-allow-unauthenticated`のデフォルト+IDトークンで開始し、必要なら見直す
- Places APIキーの取得・共有方法(誰のアカウントで取得するか)は未確定
