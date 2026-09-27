# persona-agent-backend

音声対話でユーザーのペルソナ(移動制約・食事制約・目的など)を聞き出し、
persona JSON とパーソナライズされたアバター画像を生成する FastAPI + ADK/Gemini Live API サービス。
WebSocket `/ws/converse` 1本で対話・写真アップロード・結果取得までを行う
(アバターのスタイル/性別カタログだけは `GET /avatar-templates` という別の
プレーン HTTP エンドポイント — 理由は下記「エンドポイント一覧」参照)。

## 必須環境変数

`.env.example` を `.env` にコピーして埋める(`.env` は gitignore 済み)。

- `VERTEX_PROJECT_ID`: Gemini Live API / persona抽出 / アバター編集に使う Vertex AI プロジェクト
- `VERTEX_LOCATION`: 省略時 `us-central1`(Live API モデルはこのリージョンでのみ確認済み)
- `PERFECTCORP_API_KEY` / `PERFECTCORP_API_SECRET`: YouCam AI Avatar Generator の認証情報(写真アップロードで基本アバターを生成する場合のみ必須。未設定でも音声対話・デフォルトアバターの進化・`/avatar-templates` の静的フォールバックは動作する)

```sh
cp .env.example .env   # 値を埋める
```

## ローカル実行

```sh
pip install -r requirements-dev.txt   # プロダクション用のみなら requirements.txt
python -m pytest -q

set -a; source .env; set +a
uvicorn main:app --reload --port 8080
```

`curl http://localhost:8080/health` が `{"status":"healthy"}` を返せば起動確認完了。

## エンドポイント一覧

- `WS /ws/converse` — 音声対話・写真アップロード・結果取得。`?voice=<name>` クエリパラメータで
  Live API のボイスを指定(`live_session.VOICE_NAMES` の値のみ有効、未対応値は無視されデフォルト)。
- `GET /avatar-templates` — アバターのスタイル/性別カタログ(`{gender: {category: [{id,title,thumb}]}}`)。
  **意図的にプレーン HTTP**: ユーザーがボイスをまだ選んでいない/対話をまだ始めていない段階で
  必要になるデータなので、WebSocket 接続(= Live セッション開始)を前提にできない。
  フロントエンドの別オリジンからの `fetch()` を受けるため `CORSMiddleware` を有効化している。
  `persona-agent-backend/assets/avatar_templates.json` の事前加工済みスナップショットを読むだけで、
  リクエストごとに YouCam API を呼ばない(カタログはほぼ変化しないため)。
- `GET /health` — ヘルスチェック。

### アバターカタログの再生成

`assets/avatar_templates.json` が古くなった(YouCam 側にテンプレートが追加/削除された)と思ったら:

```sh
set -a; source .env; set +a
python -c "
import json
from collections import defaultdict
from youcam_client import list_avatar_templates

grouped = defaultdict(lambda: defaultdict(list))
for t in list_avatar_templates():
    grouped[t['gender']][t['category']].append({'id': t['id'], 'title': t['title'], 'thumb': None})
json.dump({g: dict(c) for g, c in grouped.items()}, open('assets/avatar_templates.json', 'w'), ensure_ascii=False, indent=2)
"
```
(`thumb` の実サムネイル URL が要るなら `list_avatar_templates()` の返り値に含まれる元データを使う —
上のスニペットは骨組みのみ。新しい `template_id` を `youcam_client.VERIFIED_TEMPLATE_IDS` の
フォールバックにも追加するかは、静的ファイルが読めない場合の劣化動作として要否を判断する。)

## テストとレビュー観点

```sh
python -m pytest -q          # 77 tests
python -m coverage run -m pytest -q && python -m coverage report -m   # 99%
```

このサービスをレビューするとき、特に見てほしい点:

1. **WebSocket メッセージハンドラ(`main.py`)の例外境界** — `audio_chunk`/`avatar_photo`/`finish`/
   非JSON/非オブジェクトメッセージそれぞれに個別の try/except があり、どれも「1回の不正フレームで
   セッション全体を落とさない」ことを目的にしている。新しいメッセージ型を追加する場合、この境界を
   壊さないこと(テストは `tests/test_main.py` の `test_websocket_survives_*` 系を参照)。
2. **`avatar_policy.py` の domain 許可リスト** — 宗教/出身等の属性がアバター画像生成プロンプトに
   絶対に渡らない設計(`docs/wiki/concepts/avatar-visualization-policy.md`)。新しい domain を
   `VISUALIZABLE_DOMAINS` に追加する変更は、この方針からの逸脱になるため要注意。
3. **`youcam_client.py` の「実測のみ」原則** — `template_id`/ボイス名など、公式ドキュメントで
   確認できない値は絶対に推測で追加しない(`male_manga_mood` が実在しないことを実 API で確認済み、
   というコメントが該当箇所にある)。
4. **`/avatar-templates` が Live セッションと無関係であること** — この分離を壊す変更(例:再び
   WebSocket 経由に戻す)は、「ボイスを選ぶ前に接続してしまい、後から選んだボイスが反映されない」
   という既知の回帰を再発させる(git log で `fix: ship a pre-processed avatar-template snapshot`
   を参照)。

関連ドキュメント: [persona-json-contract](../docs/wiki/concepts/persona-json-contract.md) / [avatar-visualization-policy](../docs/wiki/concepts/avatar-visualization-policy.md)
