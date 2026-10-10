---
type: decision
title: "michibiki動画の個人GCP検証と体験画像への忠実性"
status: draft
owner: backend
generated:
  by: codex
  at: 2026-10-10
sources:
  - id: video-pr
    resource: https://github.com/yu-juhun/google-cloud-ai-hackathon-vol5/pull/19
    title: "体験動画生成の既存実装"
  - id: video-spec
    resource: docs/superpowers/specs/2026-10-05-michibiki-video-generation-design.md
    title: "動画生成の設計"
---

# michibiki動画の個人GCP検証

## 概要

PR #19を土台に、共有環境を変更せず個人GCPで実動作と動画内容を確認する[^video-pr]。

## 決定/結論

- 既存の動画専用Cloud RunとVeoの構成を維持する。キューや新しいDBは追加しない[^video-spec]。
- 最初は1体験につき8秒・720pの動画を生成する。体験画像を優先し、人物・車いす・場所を維持する。
- 公開情報の仮想体験であり、実測・現地訪問・通行の証拠として扱わない。
- 利用不適合の施設は外から確認する場面とし、入店成功の映像を生成しない。
- プロンプトには旅の希望・活動・確認できた事実を渡す。未知の設備、寸法、アイドルの出演を創作しない。
- レポート所有者を確認し、動画生成・取得は同じブラウザの依頼に限定する。
- ページ切断後も、保存されたジョブと既存GET APIからVeoの完了を回収できるようにする。
- 既存のプレビューUIを残す。履歴の個人化に伴う旧デモ所有者の移行は手動・個人環境のみで実施し、旧プロフィールは削除しない。

## 根拠

体験レポートと画像から任意の動画を作る設計[^video-spec]を維持しながら、PR #19の未検証部分と初期プロンプトを補強する[^video-pr]。

## 未解決の論点

- 実動画の見た目は生成後に人間がレビューする。完成前に共有ブランチへマージしない。
- 同じブラウザ識別子はログイン認証の代わりではない。ハッカソンの個人利用が前提。

## 履歴

- 2026-10-10: PR取り込み・改善の方針を記録。実デプロイ確認中。
