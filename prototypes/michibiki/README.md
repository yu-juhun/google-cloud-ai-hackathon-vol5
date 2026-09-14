# michibiki

車いすユーザーの身体・移動条件に合わせ、旅の「分身」が現地の情報を確認して、行き先を選べるようにする Zenn AI Hackathon 向けモックです。

## Frontend

React + Vite の単一画面モックです。`frontend/` で実行します。

```bash
cd frontend
npm install
npm run dev
```

`npm run build` は Cloudflare Pages の静的出力先 `frontend/dist` を生成します。デプロイ時はビルドコマンドを `npm run build`、出力ディレクトリを `dist` に設定してください。

## 現在のデモ

- 「mio」の条件（車いす幅 70cm、段差 2cmまで）を持つ分身
- 東京・丸の内のルート上を移動する分身アニメーション
- 地点ごとの確認状況と、幅・段差・混雑を集める状態
- 将来の現地画像／動画を差し込むためのスケルトン UI
