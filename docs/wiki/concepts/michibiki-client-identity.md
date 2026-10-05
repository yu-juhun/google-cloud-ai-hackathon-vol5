---
type: decision
title: "michibiki prototypeのclient_hashベース所有者モデル(旅行履歴機能)"
status: stable
owner: backend
generated:
  by: human:juhun.yu
  at: 2026-10-06
sources:
  - id: e2e-test
    resource: docs/superpowers/specs/2026-10-06-mission-history-client-identity-design.md
    title: "旅行履歴機能: client_hashベースの所有者モデルへの移行 設計"
    credibility_signals: "team-internal-agreement"
---

# michibiki prototypeのclient_hashベース所有者モデル(旅行履歴機能)

## 概要

`prototypes/michibiki/backend`の実環境E2Eテスト中、「旅行履歴が復元できない」問題が
発覚した。原因は`profiles`/`missions`テーブルが`DEMO_OWNER`という単一の固定文字列で
保存されており、ブラウザ・利用者を区別する手段が全く存在しなかったこと[^e2e-test]。

同バックエンドの`media.py`/`video.py`(アバター・動画生成機能)は既に
`client_hash(token)`パターン(ブラウザ側のランダムトークンをSHA256ハッシュして
所有者キーにする、ログイン不要の軽量な識別方式)を実装済みであり、フロントエンドの
`api()`関数は既に全リクエストにこのトークンをヘッダーで送っている。

## 決定/結論

- `profiles`/`missions`の所有者識別を、新方式を発明せず既存の`client_hash`方式に
  統一する[^e2e-test]
- 実際のログイン/アカウント機能は今回作らない。将来必要になった時点で
  「`client_hash` → アカウント」のマッピングを追加する前提で、今回の設計を無駄にしない
- スキーマ変更(`migrate()`のバージョン更新)は不要。`owner_id`列は元々制限なしの
  `String`型のため、値をSHA256ハッシュに変えるだけでよい
- 既存の`DEMO_OWNER`データは削除せず、該当クライアントの`client_hash`へ
  1回限りのデータ移行(`UPDATE`)で付け替える
- 新規エンドポイント`GET /api/missions`(履歴一覧)・`GET /api/profile`
  (プロフィール取得、これまで存在しなかった)を追加する

## 根拠

`backend/README.md`には元々「利用者ログイン・ユーザーごとのデータ分離はない」と
明記されており、意図的なスコープ外判断だった。しかし実環境でのE2E確認で
「旅行履歴にアクセスできない」という形で実害が表面化したため、既存のavatar/video機能が
確立したパターンを再利用する最小限の変更で解消することにした[^e2e-test]。

## 未解決の論点

- `client_hash`はブラウザ/デバイス単位のため、ブラウザを変えると履歴は引き継がれない
  (将来ログイン機能で解消予定)
- `docs/wiki/concepts/recommendation-api-contract.md`は`prototypes/michibiki`とは
  異なる旧設計(`POST /v1/recommendations`)を記述したページであり、現行の
  `prototypes/michibiki`バックエンドの実際のAPI(`/api/missions`等)とは一致していない。
  今回はこのページへの統合は行わず、本ページを新規に作成した。両者の整合は別途要検討。

## 履歴

- 2026-10-06: 初版作成。
