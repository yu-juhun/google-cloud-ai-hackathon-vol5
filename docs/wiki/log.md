# Log

## 2026-09-12

- バンドル作成(`schema.md`, `index.md`, `concepts/`)
- brainstormingにより以下を合意し、steeringページ(`concepts/steering.md`)として記録:
  - プロダクト: 車椅子ユーザー向けバリアフリー飲食店推薦エージェント
  - アーキテクチャ: Multi-Agent(検索/判定/推薦) + ADK + Cloud Run + Gemini
  - 体制: クラウドエンジニア/バックエンドエンジニア/学生/非エンジニアの4人分担
- ADK開発ツール `google/agents-cli` を採用し、`uvx google-agents-cli setup` を実行(7スキル導入を確認)。
  決定内容は `concepts/agents-cli-adoption.md` に記録
- キックオフ会議(合意ボードで議論)にて、`concepts/steering.md` の4項目すべてを現行の定義通りで確定:
  - 何を/なぜ作るか、アーキテクチャ・判定方式、体制と担当、協業運用ルール
  - 未解決の論点(デモ対象エリア、判定エージェントの範囲、作業時間の確保、コミュニケーション手段など)は
    ボード上に残存。今後決定した時点で改めて記録する
- フロントエンド連携用に、単一の推薦API契約を `api/openapi.yaml` に定義:
  - `POST /v1/recommendations` でエリア・車椅子の横幅と任意の要望を受け取り、推薦結果を返す
  - 必須項目が不足する場合は、項目別のエラーを含む `400` を返す
