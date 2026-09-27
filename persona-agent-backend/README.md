# persona-agent-backend

音声対話でユーザーのペルソナ(移動制約・食事制約・目的など)を聞き出し、
persona JSON とパーソナライズされたアバター画像を生成する FastAPI + ADK/Gemini Live API サービス。
WebSocket `/ws/converse` 1本で対話・写真アップロード・結果取得までを行う。

## 必須環境変数

- `VERTEX_PROJECT_ID`: Gemini Live API / persona抽出 / アバター編集に使う Vertex AI プロジェクト
- `VERTEX_LOCATION`: 省略時 `us-central1`(Live API モデルはこのリージョンでのみ確認済み。`docs/wiki/concepts/` 参照)
- `PERFECTCORP_API_KEY` / `PERFECTCORP_API_SECRET`: YouCam AI Avatar Generator の認証情報(写真アップロードで基本アバターを生成する場合のみ必須。未設定でも音声対話・デフォルトアバターの進化は動作する)

## ローカル実行

```sh
pip install -r requirements.txt
python -m pytest -q
uvicorn main:app --reload
```

関連ドキュメント: [persona-json-contract](../docs/wiki/concepts/persona-json-contract.md) / [avatar-visualization-policy](../docs/wiki/concepts/avatar-visualization-policy.md)
