---
type: steering
title: "バリアフリー飲食店 推薦エージェント: 方針・体制"
status: stable
owner: all
generated:
  by: human:juhun.yu
  at: 2026-09-12
sources:
  - id: kickoff-brainstorm
    resource: docs/wiki/log.md#2026-09-12
    title: "初期brainstormingでの合意"
    credibility_signals: "team-internal-agreement"
  - id: zenn-hackathon-page
    resource: https://zenn.dev/hackathons/google-cloud-japan-ai-hackathon-vol5
    title: "Google Cloud Japan AI Hackathon vol.5 募集要項"
    credibility_signals: "primary-source"
---

# Steering: バリアフリー飲食店 推薦エージェント

## 何を作るか

車椅子ユーザー向けの「バリアフリー飲食店 推薦エージェント」。

ユーザーが希望条件(エリア・料理ジャンル・車椅子タイプ等)を伝えると、エージェントが
Google Maps上の候補店舗の情報(レビュー・写真・アクセシビリティ属性)を読み取り、
実際に利用可能かを判定した上で、理由付きで店舗を推薦する[^kickoff-brainstorm]。

Multi-Agent構成(検索エージェント → 判定エージェント → 推薦エージェント)を採用する[^kickoff-brainstorm]。

```
User -> [Web UI] -> [Orchestrator / ADK Multi-Agent]
                        - 検索エージェント: Google Places APIで候補店舗を取得
                        - 判定エージェント: レビュー/写真をGeminiに読ませてバリアフリー度をスコアリング
                        - 推薦エージェント: スコア + 希望条件を突き合わせ、理由付きで推薦
```

判定の情報源はGoogle Maps API(場所詳細/レビュー/写真)を主とする[^kickoff-brainstorm]。
判定方式の具体的なモデル呼び出し方は未確定で、検証しながら決定する[^kickoff-brainstorm]。

## なぜ作るか

車椅子ユーザーは店舗の「バリアフリー表記」だけでは実際に入店・利用できるか判断できないことが多い。
レビューや写真から段差・通路幅・トイレの有無などを人が確認するのは高コストであり、AIエージェントが
自律的に情報を集めて判断することで、この負担を減らす。

## コンテスト要件

Google Cloud Japan AI Hackathon vol.5[^zenn-hackathon-page]

- テーマ: 「作れるから使える。エージェントの新しいステージへ」
- 締切: 2026-10-15 23:59
- 審査基準: (1) 課題の新規性と解決策の有効性 (2) 自律性・エージェントらしさ (3) 実装品質と拡張性
- 提出物: GitHubリポジトリ連携、デプロイURLと動作確認方法、プロジェクト説明、アーキテクチャ図、デモ動画(3分程度)
- 必須要件: Google Cloud実行プロダクト1つ以上 + Google Cloud AI技術1つ以上
  - 本プロジェクトでの選択: 実行系 = **Cloud Run**、AI系 = **Gemini** + **Agent Development Kit (ADK)**
  - この2つはどちらのカテゴリも審査要件のため、構成を変える場合も必ず両カテゴリを維持すること

## 体制と担当

4人チーム[^kickoff-brainstorm]:

| 担当 | 役割 | 主な作業ディレクトリ(実装フェーズで作成) |
|---|---|---|
| クラウドエンジニア(あなた) | GCPインフラ全体(Cloud Run, IAM, デプロイ)、ADK基盤構築、3エージェントのオーケストレーション設計 | `agents/orchestrator/` |
| バックエンドエンジニア | 検索/判定/推薦エージェントのロジック実装、Places API連携 | `agents/search/`, `agents/judge/`, `agents/recommend/` |
| 学生 | フロントエンド(Web UI)、デモ用データ・シナリオ作成 | `frontend/` |
| 非エンジニア | 審査基準に沿ったプロジェクト説明・アーキテクチャ図・デモ動画・提出物まとめ、UXレビュー | `docs/submission/` |

## スコープ外(今回はやらない)

- 車椅子以外の障がい種別への対応(将来拡張として記録は残すが実装対象外)
- 予約・決済機能
- 独自クローラによる大規模データ収集(まずはPlaces APIのレビュー/写真の範囲で判定)

## 運用ルール

- 担当領域を越える決定(アーキテクチャ変更、API選定変更など)をした場合は、着手前に
  `docs/wiki/concepts/` へ concept ページとして記録する(`/okf-wiki ingest docs/wiki <経緯>`)
- 各担当は自分の作業ブランチ(例: `agent/search`, `frontend/ui`)で作業し、mainへはPR経由でマージする
- PRの説明に「どのwikiページの決定を前提にしたか」を明記する
- 秘密情報(APIキー等)はこのリポジトリにコミットしない
