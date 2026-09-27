# persona-agent-frontend

`persona-agent-backend` の WebSocket `/ws/converse` に接続し、音声対話とアバター(顔写真アップロード・話している間の口パク・進化後のアバター表示)を提供する React + Vite フロントエンド。

## 環境変数

- `VITE_BACKEND_WS_URL`: バックエンドの WebSocket URL。省略時 `ws://localhost:8080/ws/converse`

## ローカル実行

```sh
pnpm install
pnpm run test
pnpm run dev
```
