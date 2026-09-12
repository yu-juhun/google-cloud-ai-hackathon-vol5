# Schema: hackathon vol.5 チーム知識wiki

このファイルは OKF v0.2 の producer-defined extension(§4.1)として、このバンドル固有の
規約を定義する。すべての操作(`/okf-wiki ingest|query|lint`)はここに従う。

## 公式リファレンス

このバンドルは [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format)
に準拠する。このスキルを使わないAIエージェントやツールでこのバンドルを扱う場合、あるいは
このファイルに書かれた規約の根拠を確認したい場合は、必ず以下の一次情報を参照すること
(このファイルの記述と齟齬がある場合は公式仕様が優先する):

- 仕様本文: https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md
  (frontmatter必須/推奨/オプションフィールド、`index.md`/`log.md`の形式、`sources[]`の構造などの正式定義)
- リポジトリ本体(README・examples・reference agent実装): https://github.com/GoogleCloudPlatform/open-knowledge-format

要点だけ先に知りたい場合は下記の各セクションで十分だが、フィールドの意味や仕様の解釈に
迷った場合は上記を直接読むこと。

## 目的・範囲

Google Cloud Japan AI Hackathon vol.5 向けプロジェクト
「バリアフリー飲食店 推薦エージェント」の、チーム全員(人間・AIエージェント問わず)が
共有すべき知識を集約する。

**扱うもの**:
- プロジェクトの方針・体制(→ steering ページ、詳細は後述)
- 技術的な決定事項とその根拠(アーキテクチャ、API選定、判定方式など)
- 調査結果(Places API仕様、Geminiのマルチモーダル挙動の検証結果など)
- 未解決の論点・懸念

**扱わないもの**:
- 実装コードそのもの(コード本体はリポジトリの各ディレクトリに置く。wikiはコードを重複させない)
- 日々のタスク管理(タスクはIssue等の別システムで管理する。wikiは「決定・知見」のみを残す)
- 個々のPRの差分内容(PRの説明文で十分な場合はwiki化しない)

## ページ種別

このバンドルには2種類のページがある。OKF仕様の唯一の必須フィールドである
frontmatter の **`type`**(独自フィールドではなく仕様準拠のフィールド)で区別する。
これにより、このスキルを知らない別のAIエージェント/ツールでも、標準的なOKFパーサーとして
`type` を見るだけでページの性質を判別できる。

### 1. `type: steering`(方針ページ)

プロジェクト全体に関わる前提・方針・体制を記す、常に最新であるべきページ。
どのAIエージェント・どのツールを使うメンバーも、作業前に必ず読む想定。

- 対象: 製品の目的、コンテスト要件、必須GCPサービス、スコープ外の宣言、体制・担当分担、
  コミット/ブランチ運用
- 更新: 方針そのものが変わった時のみ。頻繁な追記はしない
- 数: 原則 `concepts/steering.md` の1ページのみに集約する(分散させない)
- `status` は常に `stable` を維持する(`deprecated` にする場合はプロジェクト自体の方針転換を意味する)

### 2. `type: <具体的な種別>`(通常の知識ページ)

技術的決定・調査結果など、蓄積型の知識。`type` の値はOKF仕様上「登録集中管理なし、
生産者が記述的で自明な値を選ぶ」ものなので、例えば `decision`(技術決定) /
`research`(調査結果) / `issue`(未解決の論点) のように具体的な種別名を使う。
`concept` という総称は使わない。

ページ作成基準:
- **2件以上の Raw Source(会話・調査・PR等)が同じ概念に言及した時点でページ化する**
- 1件のみの言及はページ化せず、既存の steering ページや将来のページ化に備えて `log.md` にのみ記録する

## frontmatter フィールド(OKF仕様準拠 + 本バンドル拡張)

仕様上必須なのは `type` のみ。他は仕様の推奨/オプションフィールドと、本バンドル独自の拡張(`owner`)。

```yaml
---
type: steering | decision | research | issue   # 必須(OKF仕様)
title: <表示用名前>                              # 推奨(OKF仕様)
status: draft | stable | deprecated             # オプション(OKF仕様、既定 stable)
stale_after: <YYYY-MM-DD>                        # オプション(OKF仕様。steeringページには付けない)
generated:                                       # オプション(OKF仕様、由来)
  by: human:<id> | <producer>/<version>
  at: <ISO8601>
verified:                                        # オプション(OKF仕様、検証)
  - by: human:<id>
    at: <ISO8601>
sources:                                         # オプション(OKF仕様)。各エントリに resource 必須
  - id: <引用キー>
    resource: <URLまたはファイル相対パス>
    title: <表示用タイトル>
    credibility_signals: <任意。例: "team-internal-agreement">
owner: <本バンドル拡張フィールド。担当領域。例: backend / infra / frontend / submission / all>
---
```

## 本文の標準セクション構成

- steering ページ: `## 何を作るか` `## なぜ作るか` `## コンテスト要件` `## 体制と担当` `## スコープ外` `## 運用ルール`
- concept ページ: `## 概要` `## 決定/結論` `## 根拠` `## 未解決の論点` `## 履歴`

## 引用(Citation)の記法

本文中の主張には `[^id]` 形式で `sources[]` の `id` を参照する。例:

```
Cloud Run上でADK Multi-Agentを動かす方針を採用した[^kickoff-brainstorm]。
```

`sources[]` エントリ例:
```yaml
sources:
  - id: kickoff-brainstorm
    resource: docs/wiki/log.md#2026-09-12
    title: "初期brainstormingでの合意"
```

## lint 固有ルール

- `type: steering` のページが複数存在してはならない(L2/L7 相当。統合されていること自体を検査する)
- steering ページの `status` が `deprecated` になっていないか(なっていたら要確認として報告)
- `decision` / `research` ページで `stale_after` を過ぎているものは L8 として報告する

## 消費者

- チームメンバー全員(役割問わず)。使用するAIエージェント/ツールは問わない — OKFはツール非依存の
  markdown+frontmatter形式であるため、どのエージェントでも `docs/wiki/` を読めば方針と決定事項を把握できる
