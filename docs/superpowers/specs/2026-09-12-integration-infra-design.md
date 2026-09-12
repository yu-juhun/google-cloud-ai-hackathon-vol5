# 統合デモ環境 インフラ設計

## 目的

車椅子ユーザー向けバリアフリー飲食店推薦エージェントを、共有GCPプロジェクトにデプロイし、
チームメンバー全員が「自分の担当エージェントが最終的にどこに・どうハマるか」を理解した上で、
各自の個人GCPプロジェクトで開発・検証できるようにする。

本docは`docs/wiki/concepts/steering.md`(方針)を前提とし、その実装レベルの詳細を定める。
`docs/wiki/`のOKF規約に沿った知識ではなく実装計画のため、通常のspecとしてここに置く。

## 全体アーキテクチャ

5台構成(frontend / backend-api / search-agent / judge-agent / recommend-agent、それぞれ1台の
Cloud Run)は口頭で合意済みの内容を本specと
[`docs/wiki/concepts/service-topology.md`](../wiki/concepts/service-topology.md)(決定ページ)に記録する。
**この5台構成は、以前このspecに記載していた3台構成(frontend / backend-api / agent1台にまとめる)
を上書きする** — 実装着手後、個人GCPプロジェクトでの検証しやすさを理由にsearch/judge/recommendを
それぞれ独立サービスへ分離する方針に変更した。

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ project-3bcd6d36-2338-4b32-848 (共有GCP・統合デモ環境)                            │
│                                                                                 │
│ ┌───────────┐  HTTP  ┌───────────────┐  HTTP  ┌─────────────┐                 │
│ │ Cloud Run  │───────▶│ Cloud Run      │───────▶│ Cloud Run    │ search-agent   │
│ │ frontend   │        │ backend-api     │───────▶│ Cloud Run    │ judge-agent    │
│ │ (Web UI)   │        │ POST /v1/       │───────▶│ Cloud Run    │ recommend-agent│
│ │ 担当: 松野さん│        │ recommendations  │        └─────────────┘                 │
│ │           │        │ 契約:            │        担当(3サービスとも): 中村さん      │
│ │           │        │ api/openapi.yaml │                                        │
│ │           │        │ オーケストレーション│                                        │
│ │           │        │ を担う。担当: 中村さん│                                       │
│ └───────────┘        └───────────────┘                                        │
└───────────────────────────────────────────────────────────────────────────────┘
        ▲ 各自の個人GCPプロジェクトで同じ構成をローカル/デプロイして検証
        │ (下記「個人プロジェクトでの検証」参照)
   各メンバーの開発環境
```

- **frontend**: Web UI。`backend-api`の`/v1/recommendations`のみを呼ぶ。3つのagentサービスの存在を知らない
- **backend-api**: フロントエンド向けの安定REST API。`api/openapi.yaml`が正本。
  **オーケストレーション(search-agent → judge-agent → recommend-agentの呼び出し順序制御)を
  自ら担う**(専用orchestratorサービスは追加しない)。各agentサービスの生レスポンスを
  `RecommendationResponse`スキーマに整形する
- **search-agent / judge-agent / recommend-agent**: それぞれ独立したADK Appとして実装し、
  個別にCloud Runへデプロイする(以前の「サブエージェント単位ではCloud Runを分けない」という
  決定を撤回)
- 5サービスとも`agents-cli`でスキャフォルドし、デプロイ先は`--deployment-target cloud_run`固定(初期版)。
  Agent Runtimeへの切替は後日、必要になった時点で`agents-cli scaffold enhance --deployment-target agent_runtime`で対応する

## リポジトリ構成(追加分)

```
search-agent/                   # agents-cli scaffold create で生成(ADK App)
├── app/agent.py                # 候補店舗の検索。担当: 中村さん
├── deployment/terraform/      # agents-cli infra が生成。手動gcloudでの変更は禁止
├── tests/
└── Dockerfile

judge-agent/                    # agents-cli scaffold create で生成(ADK App)
├── app/agent.py                # バリアフリー度の判定。担当: 中村さん
├── deployment/terraform/
├── tests/
└── Dockerfile

recommend-agent/                # agents-cli scaffold create で生成(ADK App)
├── app/agent.py                # 推薦理由の生成。担当: 中村さん
├── deployment/terraform/
├── tests/
└── Dockerfile

backend-api/                     # 別途 agents-cli scaffold create --deployment-target cloud_run
├── api/openapi.yaml            # 正本。frontendとの契約(すでにPR#8でマージ済み)
├── src/                        # 3つのagentサービスの呼び出し順序制御 + OpenAPIへの整形。担当: 中村さん
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
- **backend-api → search-agent / judge-agent / recommend-agent**: 各ADKサービスのFastAPI標準
  エンドポイント(`/apps/<agent>/invoke`相当)を、`backend-api`が上記の順序で呼び出す。
  各サービスの入出力スキーマは各サービスのコード(Pythonの型定義)を正とし、`backend-api`側が
  3つの結果を合成して`RecommendationResponse`への変換を担う。この境界のスキーマが変わった場合は
  `docs/wiki/concepts/`に`type: decision`ページを追加して記録すること

## GCPインフラ(Terraform管理・`agents-cli`生成分)

- 対象プロジェクト: `project-3bcd6d36-2338-4b32-848`(課金有効・確認済み)
- 有効化するAPI: `run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`
  (`agents-cli infra single-project`が自動有効化)
- サービスアカウント: `app_sa`(5つ、frontend / backend-api / search-agent / judge-agent /
  recommend-agent サービスそれぞれに分ける)
- Secret Manager: Google Places APIキー等をここで管理し、`agents-cli deploy --secrets`で注入する
  (`.env`やコードへの直書きは禁止 — `steering.md`の秘密情報ルールと一致)
- Terraformの生成・適用は`agents-cli infra single-project`(単一プロジェクト構成、staging分離なし)を用いる
- **CI/CD**: mainへのマージをトリガーに共有プロジェクトへ自動デプロイするGitHub Actionsを設定する
  (「作業準備の一環として今のうちに確立する」と合意済み)。`agents-cli infra cicd`が前提とする
  staging→prod 2段階パイプラインは単一デモ環境の方針に合わないため使わず、シンプルな
  1ジョブワークフロー(`main push` → `agents-cli deploy --project project-3bcd6d36-2338-4b32-848
  --no-confirm-project`をfrontend/backend-api/search-agent/judge-agent/recommend-agentの
  5サービスそれぞれに対して実行)で構成する

## 個人プロジェクトでの検証(他メンバー向け)

各メンバーは以下の手順で、自分の個人GCPプロジェクトに同じ構成を再現して開発・検証できる:

1. `uvx google-agents-cli setup`(README.md記載のセットアップ、既に導入済み前提)
2. 担当ディレクトリ(`search-agent/`, `judge-agent/`, `recommend-agent/`, `backend-api/`, `frontend/`
   のいずれか)で `agents-cli scaffold enhance . --deployment-target cloud_run` していることを確認
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

- frontend↔backend-api、backend-api↔各agentサービス、それぞれの認証方式(Cloud Run標準の
  IDトークン認証か、IAPか)は未確定。まずは`--no-allow-unauthenticated`のデフォルト+IDトークンで
  開始し、必要なら見直す
- Places APIキーの取得・共有方法(誰のアカウントで取得するか)は未確定
- backend-apiが3つのagentサービスを呼ぶ際のタイムアウト・リトライ方針は未確定
