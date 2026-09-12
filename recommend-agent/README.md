# recommend-agent

候補と判定を OpenAPI の推薦レスポンスへ整形する独立 ADK stage service。個人検証では search-agent と同じ stage image を `AGENT_ROLE=recommend` で起動する。

## 環境変数

- `VERTEX_PROJECT_ID`(必須): Vertex AI(Gemini)を呼び出すGCPプロジェクトID
- `VERTEX_LOCATION`(任意、デフォルト`global`): Vertex AIのロケーション
