---
type: decision
title: "ADK開発ツールとして google/agents-cli を採用"
status: stable
owner: infra
generated:
  by: human:juhun.yu
  at: 2026-09-12
sources:
  - id: agents-cli-repo
    resource: https://github.com/google/agents-cli
    title: "google/agents-cli リポジトリ"
    credibility_signals: "primary-source"
  - id: agents-cli-setup-log
    resource: docs/wiki/log.md#2026-09-12
    title: "uvx google-agents-cli setup 実行記録"
    credibility_signals: "team-internal-agreement"
---

# ADK開発ツールとして google/agents-cli を採用

## 概要

ADK(Agent Development Kit)エージェントのscaffold・コーディング・評価・デプロイ・監視・公開を
支援するCLI/スキル集 `google/agents-cli` をチーム全員の開発環境に導入する[^agents-cli-repo]。

## 決定/結論

- 各メンバーは自分のマシンで以下を実行し、ADK関連スキル一式を導入する:
  ```bash
  uvx google-agents-cli setup
  ```
- インストールはグローバル(`~/.agents/skills/`)に行われ、Claude Code / Gemini CLI /
  Antigravity など複数のコーディングエージェントから共通で参照できる。**リポジトリには
  何もコミットされない**(このリポジトリ固有の設定ファイルは生成されない)。
- 前提環境: `uv`(Python パッケージマネージャ)がインストールされていること。
- エージェント実装(検索/判定/推薦エージェント)を書くメンバーは、導入後に
  `google-agents-cli-adk-code` / `google-agents-cli-scaffold` スキルを使ってよい。
  デプロイ(Cloud Run)を担当するメンバーは `google-agents-cli-deploy` を使ってよい。

## 根拠

- ADK自体のコード規約・デプロイ・評価パターンを毎回調べ直すコストを下げるため
- チーム全員が同じツール前提で作業することで、実装スタイルのばらつきを減らすため

## 未解決の論点

- 認証(`Auth: Not authenticated`)は未設定。実際にdeploy/publishスキルを使う段階で
  各自のGCP認証情報と紐付けが必要になる
- スキル自体はサードパーティ(Google提供だがOKF/CLAUDE.mdの管理対象外)のため、
  内容の変更・破壊的変更はこのwikiの管理範囲外(agents-cli側のリリースに追従する)

## 履歴

- 2026-09-12: 初回導入(クラウドエンジニアの環境で `uvx google-agents-cli setup` 実行、7スキルを確認)
