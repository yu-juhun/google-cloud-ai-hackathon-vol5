# 統合デモ環境 インフラ設計

## 目的

車椅子ユーザー向けバリアフリー飲食店推薦エージェントを、共有GCPプロジェクトにデプロイし、
チームメンバー全員が「自分の担当エージェントが最終的にどこに・どうハマるか」を理解した上で、
各自の個人GCPプロジェクトで開発・検証できるようにする。

本docは`docs/wiki/concepts/steering.md`(方針)を前提とし、その実装レベルの詳細を定める。
`docs/wiki/`のOKF規約に沿った知識ではなく実装計画のため、通常のspecとしてここに置く。

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│ project-3bcd6d36-2338-4b32-848 (共有GCP・統合デモ環境)         │
│                                                               │
│  ┌───────────────────┐        ┌──────────────────────────┐ │
│  │ Cloud Run          │  HTTP  │ Cloud Run                 │ │
│  │ frontend-service   │──────▶│ agent-backend-service      │ │
│  │ (学生が担当)         │        │ (ADK App)                  │ │
│  └───────────────────┘        │  ┌────────────────────┐   │ │
│                                │  │ orchestrator        │   │ │
│                                │  │  ├─ agents/search   │   │ │
│                                │  │  ├─ agents/judge    │   │ │
│                                │  │  └─ agents/recommend│   │ │
│                                │  └────────────────────┘   │ │
│                                └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
        ▲ 各自の個人GCPプロジェクトで同じ構成をローカル/デプロイして検証
        │ (下記「個人プロジェクトでの検証」参照)
   各メンバーの開発環境
```

- **frontend-service**: 学生が担当するWeb UI。ユーザー入力を受け、agent-backend-serviceを呼ぶ。
- **agent-backend-service**: ADK App。中に3つのサブエージェント(検索/判定/推薦)をコード上のツリーとして持つ
  (別々のCloud Runサービスにはしない — 2026-09-12のキックオフ会議で確定した統合単位)。
- 両サービスとも`agents-cli`でスキャフォルドし、デプロイ先は`--deployment-target cloud_run`固定(初期版)。
  Agent Runtimeへの切替は後日、必要になった時点で`agents-cli scaffold enhance --deployment-target agent_runtime`で対応する。

## リポジトリ構成(追加分)

```
agent-backend/                  # agents-cli scaffold create で生成
├── agents/
│   ├── orchestrator/          # 呼び出し順序: search → judge → recommend
│   ├── search/                # 担当: 中村さん(バックエンドエンジニア)
│   ├── judge/                 # 担当: 中村さん(バックエンドエンジニア)
│   └── recommend/             # 担当: 中村さん(バックエンドエンジニア)
├── deployment/terraform/      # agents-cli infra が生成。手動gcloudでの変更は禁止
├── tests/
└── Dockerfile

frontend/                       # 別途 agents-cli scaffold create --deployment-target cloud_run
├── src/                        # 担当: 松野さん(学生)
├── deployment/terraform/
└── Dockerfile
```

既存の`docs/wiki/`, `docs/superpowers/`, `AGENTS.md`等はそのまま維持する。

## サービス間インターフェース(担当者が個人プロジェクトで検証する際の契約)

frontend-serviceは agent-backend-serviceに対して、以下のHTTPリクエストを送る前提で開発する
(ADKのFastAPI標準エンドポイントを利用):

```
POST /apps/orchestrator/invoke
Content-Type: application/json
Authorization: Bearer <identity token>   # Cloud Run未認証アクセスを許可しない場合

{
  "area": "福岡市",
  "cuisine": "string (optional)",
  "wheelchair_type": "electric | manual",
  "session_id": "string"
}
```

レスポンス(初期スタブ版の固定スキーマ。実装が進んでも このスキーマを崩さないことをインターフェース契約とする):

```json
{
  "recommendations": [
    {
      "place_id": "string",
      "name": "string",
      "accessibility_verdict": "O | TRIANGLE | X",
      "reason": "string"
    }
  ]
}
```

各サブエージェントの入出力契約は`agents/orchestrator/`内のコード(Pythonの型定義)を正とする。
このspecは全体の輪郭のみを示す — 詳細スキーマが変わった場合はコードとdocs/wiki/の該当ページ
(未作成であれば`type: decision`ページを新規作成)を更新すること。

## GCPインフラ(Terraform管理・`agents-cli`生成分)

- 対象プロジェクト: `project-3bcd6d36-2338-4b32-848`(課金有効・確認済み)
- 有効化するAPI: `run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`
  (`agents-cli infra single-project`が自動有効化)
- サービスアカウント: `app_sa`(2つ、frontend-service用・agent-backend-service用を分ける)
- Secret Manager: Google Places APIキー等をここで管理し、`agents-cli deploy --secrets`で注入する
  (`.env`やコードへの直書きは禁止 — `steering.md`の秘密情報ルールと一致)
- Terraformの生成・適用は`agents-cli infra single-project`(単一プロジェクト構成、staging分離なし)を用いる
- **CI/CD**: mainへのマージをトリガーに共有プロジェクトへ自動デプロイするGitHub Actionsを設定する
  (「作業準備の一環として今のうちに確立する」と合意済み)。`agents-cli infra cicd`が前提とする
  staging→prod 2段階パイプラインは単一デモ環境の方針に合わないため使わず、シンプルな
  1ジョブワークフロー(`main push` → `agents-cli deploy --project project-3bcd6d36-2338-4b32-848
  --no-confirm-project`をfrontend-service/agent-backend-serviceそれぞれに対して実行)で構成する

## 個人プロジェクトでの検証(他メンバー向け)

各メンバーは以下の手順で、自分の個人GCPプロジェクトに同じ構成を再現して開発・検証できる:

1. `uvx google-agents-cli setup`(README.md記載のセットアップ、既に導入済み前提)
2. 担当ディレクトリ(`agents/search/`等、または`frontend/`)で `agents-cli scaffold enhance . --deployment-target cloud_run`
   していることを確認(このspecに沿ったscaffoldなら不要)
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

- frontend-serviceとagent-backend-service間の認証方式(Cloud Run標準のIDトークン認証か、IAPか)は
  未確定。まずは`--no-allow-unauthenticated`のデフォルト+IDトークンで開始し、必要なら見直す
- Places APIキーの取得・共有方法(誰のアカウントで取得するか)は未確定
