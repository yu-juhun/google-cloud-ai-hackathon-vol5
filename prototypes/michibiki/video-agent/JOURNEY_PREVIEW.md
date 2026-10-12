# 旅程全体のVeo動画をCLIで試す

これはブラウザ接続前の検証用CLI。保存済み旅程の各地点を、本人画像と
実景参考写真を組み合わせてGoogle CloudのVeoで動画化する。
動画・音の編集はFFmpegで行う。アプリの既存の「1体験動画」APIとは別段階であり、
まだこの旅程動画をWeb画面から自動生成する実装ではない。

## 入力と前提

- Google CloudのADC認証と、対象プロジェクトのDB/Secret Manager/Vertex AIへの権限
- backendの仮想環境（Cloud SQL connector、SQLAlchemy、google-genai、requests）
- FFmpeg / ffprobe。日本語ラベルはmacOSのヒラギノまたはLinuxのNoto CJKを利用
- 完了済みmission ID、本人のJPEG/PNG、旅程のplace IDに対応した参考画像設定
- 参考写真はWikimedia CommonsのCC0 / Public domain / CC BYのみ。
  出典・作者・ライセンスをJSONに残し、動画にも簡潔なクレジットを入れる

`examples/nogizaka-locations.json` は、個人検証で合意した4地点の例。
他の旅程を試す場合は各place ID・場所・実景写真・場面の行動を照合し直す。
Google Mapsや検索結果に出た写真を無条件に生成素材として流用しない。

## 生成前の事前確認（Veo生成・課金なし）

```sh
backend/.venv/bin/python video-agent/preview_journey.py \
  --project YOUR_PROJECT_ID --mission-id SAVED_MISSION_ID \
  --person /absolute/path/to/person.png \
  --locations video-agent/examples/nogizaka-locations.json \
  --output-dir output/video-preview/your-trip-v1 --prepare-only
```

実景参考画像とプロンプトを目視確認してから、`--prepare-only`を外して生成する。
Veo利用料はGoogle Cloudに発生する。2〜4場面、各8秒、各1本に限定。
操作名をmanifestに保存するため、途中で停止した場合も同じ出力ディレクトリで再開できる。
失敗した場面を無断で再生成したり、キーや認証トークンを成果物に書き出したりしない。

## 自然な接続と内容確認

- 同じ本人・服装・車いすを全場面で指定する
- 各場面にはその訪問先の写真を渡す。全体の希望と実際の予定行動も渡す
- 前場面のフレームは外観の連続性を補助するが、旧背景の混入は生成後のレビューで確認する
- 例の試作では後続3場面の冒頭2秒に旧背景が残ったため、必要部分を選択して除いた
- 映像は0.6秒の短い暗転フェード。人物・字幕が二重にならないようにする
- 音は0.6秒のクロスフェード、音量の正規化、最初と最後のフェード
- 720p / 24fps / H.264 / AAC。約24〜30秒のMP4

生成後の編集だけなら、同じディレクトリに新しいファイル名を指定する。
既に存在するscene MP4は再生成しない。

```sh
# 上の入力引数に以下を追加（レビュー済みのカット秒数は映像に合わせて決める）
  --output-name journey-smooth.mp4 --head-trims 0,2,2,2
```

この映像は参考写真に基づくAIの仮想体験。現地訪問、入口幅、段差、経路の通行可能性を
証明するものではない。本人・場所・動作・切替を人間が確認してから、Web APIへ接続する。
