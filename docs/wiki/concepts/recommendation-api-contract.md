---
type: decision
title: "フロントエンド連携用の推薦API契約"
status: stable
owner: all
generated:
  by: codex
  at: 2026-09-12
sources:
  - id: steering
    resource: docs/wiki/concepts/steering.md
    title: "バリアフリー飲食店 推薦エージェント: 方針・体制"
    credibility_signals: "team-internal-agreement"
---

# フロントエンド連携用の推薦API契約

## 概要

フロントエンドとエージェントバックエンドの連携は、単一の推薦APIで行う。
仕様の正本は [`api/openapi.yaml`](../../../api/openapi.yaml) とする。

## 決定/結論

- エンドポイントは `POST /v1/recommendations` とする
- 必須入力は `area` と `wheelchair_width_cm` とする
- 料理ジャンルと、エージェントに伝える自由形式の要望は任意とする
- 必須入力の不足や値の不正は `400` を返し、`fields` 配列に項目別のエラーを含める
- 結果には、地図表示用の座標、Google Maps URL、入店可否の判定、判定根拠、推薦理由を含める
- 入店可否は `accessible` / `uncertain` / `not_accessible` とし、UI上で○・△・✕に変換する

## 根拠

推薦の利用者体験は、条件入力、店舗の入店可否の判定、地図上での結果確認を中心とする[^steering]。

## 未解決の論点

- Places API以外の補助情報源を使う場合の根拠表示
- 評価の詳細なスコアリング方式

## 履歴

- 2026-09-12: 初版作成。フロントエンド連携用の単一推薦APIと入力検証エラー形式を定義
