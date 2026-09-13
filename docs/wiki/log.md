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
- 統合デモ環境のサービス構成を口頭合意 → `concepts/service-topology.md` に正式記録:
  - Cloud Run 3台体制(frontend / backend-api / agent)。frontendはbackend-apiのみを呼び、
    backend-apiがagent(ADK App)を呼び出してレスポンスを整形する
  - 詳細なインフラ設計は `docs/superpowers/specs/2026-09-12-integration-infra-design.md` に記録
- 実装着手後、サービス構成を3台体制から5台体制(frontend / backend-api / search-agent /
  judge-agent / recommend-agent)へ変更。`concepts/service-topology.md`を更新し、
  `docs/superpowers/specs/2026-09-12-integration-infra-design.md`も合わせて修正:
  - 検索/判定/推薦をそれぞれ独立したCloud Runサービスに分離(個人GCPプロジェクトでの検証しやすさが理由)
  - オーケストレーションはbackend-apiが担う(専用orchestratorサービスは追加しない)
- フロントエンドはモック先行で開発し、環境変数で実APIへ切り替える方針を採用:
  - React + TypeScript + Viteで、条件入力・判定根拠・○△×・簡易地図を実装
  - モックとHTTPクライアントで `api/openapi.yaml` と同じ入出力型を共有
- 5サービス(frontend / backend-api / search-agent / judge-agent / recommend-agent)を
  共有プロジェクト`project-3bcd6d36-2338-4b32-848`へ初回デプロイ。詳細は`concepts/deployed-endpoints.md`:
  - Places API実データ + Gemini判定によるエンドツーエンド動作を確認(福岡市中央区で5店舗推薦)
  - デプロイ過程で発見・修正: Cloud Build SAの権限不足、Terraformの`ingress`属性を明示指定しないと
    既存値がリセットされない問題、`INGRESS_TRAFFIC_INTERNAL_ONLY`がCloud Run間通信をGFEレベルで
    拒否する問題、frontendビルドコンテキストが`../api/openapi.yaml`参照に対応していない問題、
    `aiplatform.googleapis.com`未有効化、frontendのメモリ制限不足
  - judge-agent/recommend-agentにハードコードされていた個人GCPプロジェクトIDは別PRで修正済み(#14)
  - `PLACES_API_KEY`(Secret Manager)、Google Maps用ブラウザキーを新規作成して配線
- 継続コストを避けるため、デプロイ確認後にCloud Run 5サービス、Artifact Registryリポジトリ、
  Secret Manager `places-api-key`、APIキー2つを全て削除(`terraform destroy` + `gcloud`)。
  Terraform state用GCSバケットとコード・Terraform定義は再デプロイのため残す。
  詳細は`concepts/deployed-endpoints.md`

## 2026-09-13

- ミニハッカソン(社内向け、2026-09-11)終了。本番の Google Cloud Japan AI Hackathon vol.5
  (締切2026-10-15)向けブラッシュアップとして、`concepts/steering.md`を大幅更新:
  - テーマを「車椅子ユーザー向けバリアフリー飲食店推薦」に限定しない、より広い枠へ拡張する方針に転換
  - フェーズ1(ミニハッカソン)の内容は参考情報としてsteering.md内に残し、現行スコープとしては扱わない
  - 各メンバーが個別コンセプトを立てて先行開発し、後日のミーティングで統合方針を決める進め方に変更:
    - 劉: グルメ/聖地巡礼、3人家族の父(大人代表)・イスラム教徒の車椅子ユーザー向け、
      UI/UX提供+他エージェント向け情報収集
    - 松野: 飲食店/聖地巡礼ルート提案、移動制約者向け、アクセシビリティを考慮した複数プラン提案
    - 中村: 体験フォーカス型訪問先提案(仮: 旅行先)、移動制約者向け、分身アバターによる仮想訪問+
      フィードバック生成
    - 白井: アイドルオタク向け聖地巡礼サポート、X等からの聖地履歴取得+バリアフリー情報付記+
      ユーザーによる追記機能
  - 作業方法: 各自の個人ブランチで作業し、共用ドキュメント・既存作業物への影響を最小限にする。
    共有インフラ(Cloud Run 5サービス構成、Terraform、CI/CD等)はそのまま土台として引き継ぐ
