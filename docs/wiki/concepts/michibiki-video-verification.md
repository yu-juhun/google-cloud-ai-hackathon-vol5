---
type: decision
title: "michibikiの旅程全体を体験する動画と個人GCP検証"
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
  - id: journey-preview
    resource: prototypes/michibiki/video-agent/JOURNEY_PREVIEW.md
    title: "旅程全体のCLI試作と確認手順"
---

# michibiki動画の個人GCP検証

## 概要

PR #19を土台に、共有環境を変更せず個人GCPで実動作と動画内容を確認する[^video-pr]。

## 決定/結論

- 既存の動画専用Cloud RunとVeoの構成を維持する。キューや新しいDBは追加しない[^video-spec]。
- PR #19の既存APIは1体験・8秒だが、ユーザーが求める主出力は旅程全体を体験する物語。まずCLIで訪問順に4場面を生成し、内容確認後にWebへ接続する[^journey-preview]。
- 同じ本人画像と訪問先の実景写真をVeoへ渡す。写真はCC0・Public domain・CC BYを確認し、Google Maps写真を無条件に生成素材へ流用しない。
- 乃木坂到着、国立新美術館、乃木神社、ミッドタウン休憩の4場面を実際に生成した。場面ごとの必要部分を選び、24.3秒・720pの試作にした[^journey-preview]。
- 映像は0.6秒の短い暗転フェード、音はクロスフェードで接続する。人物・字幕が二重になる接続と、旧背景が残る冒頭は採用しない。
- 公開情報の仮想体験であり、実測・現地訪問・通行の証拠として扱わない。
- 利用不適合の施設は外から確認する場面とし、入店成功の映像を生成しない。
- プロンプトには旅の希望・活動・確認できた事実を渡す。未知の設備、寸法、アイドルの出演を創作しない。
- レポート所有者を確認し、動画生成・取得は同じブラウザの依頼に限定する。
- ページ切断後も、保存されたジョブと既存GET APIからVeoの完了を回収できるようにする。
- 既存のプレビューUIを残す。履歴の個人化に伴う旧デモ所有者の移行は手動・個人環境のみで実施し、旧プロフィールは削除しない。

## 根拠

体験レポートと画像から任意の動画を作る設計[^video-spec]を維持しながら、PR #19の未検証部分と初期プロンプトを補強する[^video-pr]。

## 未解決の論点

- 試作の見た目はユーザーがレビューする。旅程全体のWeb API接続と、共有ブランチへのマージは承認後に行う。
- 同じブラウザ識別子はログイン認証の代わりではない。ハッカソンの個人利用が前提。

## 履歴

- 2026-10-10: PR取り込み・個人GCPの基盤検証を実施。ユーザーとの確認で「単一体験ではなく旅程全体」が必要と合意し、実景と本人参照の4場面動画をCLIで試作。映像の承認待ち。
