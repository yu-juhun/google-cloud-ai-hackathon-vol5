# judge-agent

バリアフリー判定を返す独立 ADK stage service。個人検証では search-agent と同じ stage image を `AGENT_ROLE=judge` で起動する。

## 環境変数

- `VERTEX_PROJECT_ID`(必須): Vertex AI(Gemini)を呼び出すGCPプロジェクトID
- `VERTEX_LOCATION`(任意、デフォルト`global`): Vertex AIのロケーション
