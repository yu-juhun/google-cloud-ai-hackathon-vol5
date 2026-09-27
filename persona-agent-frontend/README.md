# persona-agent-frontend

`persona-agent-backend` に接続し、音声対話とアバター(性別/スタイル選択・顔写真アップロード・
話している間の口パク・進化後のアバター表示)を提供する React + Vite フロントエンド。

対話フローは4段階の UI(`AvatarPanel.tsx`): ① 性別とスタイル → ② 顔写真 → ③ 声 → ④ 会話。
①②が両方確定するまで写真アップロードは無効化される(サーバー側デフォルトへの意図しない
フォールバックを防ぐため)。

## 環境変数

- `VITE_BACKEND_WS_URL`: バックエンドの WebSocket URL。省略時 `ws://localhost:8080/ws/converse`。
  アバターカタログ取得(`GET /avatar-templates`)のベース URL もこの値から自動的に導出する
  (`ws(s)://host/ws/converse` → `http(s)://host/avatar-templates`)。

## ローカル実行

```sh
pnpm install
pnpm run test    # 45 tests
pnpm run build   # tsc --noEmit && vite build
pnpm run dev      # http://localhost:5173
```

バックエンドをローカルで先に起動しておくこと(`persona-agent-backend/README.md` 参照)。
バックエンドが別オリジン/別ポートの場合、`GET /avatar-templates` はプレーンな `fetch()` の
クロスオリジン呼び出しになるため、バックエンド側の CORS 設定が必要(既に `main.py` で有効)。

## デザインシステム(トークン)

`src/styles/tokens.css` は [OpenDesign](https://github.com/nexu-io/open-design) の
`design-systems/default`(Neutral Modern)パッケージをそのままコピーしたもの。
`src/ui/`(Button/Card/Select/Alert)と `AvatarPanel.css` はこのファイルの `var(--token)` だけを
参照するので、**見た目のコンセプトを変える = `tokens.css` を別パッケージのファイルに差し替えるだけ**
(コンポーネント側は無変更でよい)。詳細は `src/ui/README.md`。

## テストとレビュー観点

1. **`PersonaSocket.connect()` の呼び出しタイミング** — `connect(voiceName)` は「実際に接続を
   開く最初の呼び出し」でしか `voiceName` を使えない(Live セッションは接続時に開始されるため)。
   マウント時に安易に `connect()` を呼ぶ変更を入れると、「後で声を選んでも反映されない」という
   既知の回帰が再発する。カタログ取得(`fetchAvatarTemplates`)は意図的に `connect()` を経由しない
   プレーン `fetch()` — この分離を保つこと。
2. **`AvatarPanel`の `readyToUpload` ガード** — 性別 + スタイルの両方が確定するまで写真アップロード
   input を無効化している。片方だけで有効にすると、サーバー側のハードコードされた既定
   (`female_manga_mood`)に落ちてしまう「アップロードすると必ず女性になる」バグが再発する。
3. **`handleStart` 内での `AudioPlayback` 生成・`resume()` の位置** — クリックハンドラの中で
   *同期的に* 行う必要がある。`onAudioChunk`(非同期の WebSocket メッセージ)側に遅延させると、
   ブラウザの自動再生ポリシーで `AudioContext` が `suspended` のまま固まり、口パクは動くのに
   実際の音声が聞こえない不具合が再発する(`audioPlayback.test.ts`/`AvatarPanel.test.tsx` の
   `resume` 関連テストがこの契約を守っている)。
4. **`src/ui/` コンポーネントの token-only ルール** — 新しいコンポーネントを追加する際、色/間隔/
   角丸などを `var(--token)` 以外で直書きしないこと(デザインコンセプト差し替えの前提が崩れる)。
