---
type: concept
title: "聖地巡礼の真正性検証エージェント(個人コンセプト案)"
status: draft
owner: human:yutaka.hakui
generated:
  by: human:yutaka.hakui
  at: 2026-09-18
sources:
  - id: phase2-brushup
    resource: docs/wiki/concepts/steering.md
    title: "本番ハッカソン向けブラッシュアップ合意(テーマ拡張・個別コンセプト・進め方)"
    credibility_signals: "team-internal-agreement"
  - id: zenn-hackathon-page
    resource: https://zenn.dev/hackathons/google-cloud-japan-ai-hackathon-vol5
    title: "第5回 Agentic AI Hackathon with Google Cloud 募集要項"
    credibility_signals: "primary-source"
  - id: x-api-pricing
    resource: https://postproxy.dev/blog/x-api-pricing-2026/
    title: "X (Twitter) API Pricing in 2026: All Tiers"
    credibility_signals: "secondary-source"
  - id: search-grounding
    resource: https://ai.google.dev/gemini-api/docs/google-search
    title: "Grounding with Google Search | Gemini API"
    credibility_signals: "primary-source"
  - id: maps-grounding
    resource: https://ai.google.dev/gemini-api/docs/maps-grounding
    title: "Grounding with Google Maps | Gemini API"
    credibility_signals: "primary-source"
  - id: places-accessibility
    resource: https://mapsplatform.google.com/resources/blog/introducing-the-new-places-api-with-access-to-new-ev-accessibility-features-and-more/
    title: "Introducing the new Places API with access to EV, accessibility features, and more"
    credibility_signals: "primary-source"
verified:
  - by: human:yutaka.hakui
    at: 2026-09-18
---

# 聖地巡礼の真正性検証エージェント

フェーズ2で合意した「移動に制約がある人の訪問先提案」というテーマ[^phase2-brushup]に対する、
個人コンセプト案。

## 一行で言うと

**「ここは本当に聖地なのか」を、AI が出典付きで裏取りして示すエージェント。**

## 解きたい課題

アイドルの「聖地」情報はネット上に大量にあるが、**真偽が曖昧**である。

- 出典が示されないまま「聖地」として拡散している情報がある
- 情報が古く、店舗が閉店している、あるいは訪問がかなり前のものである
- 誰が訪れたのか(現役メンバーか、卒業メンバーか)が不明なまま並んでいる

遠征は時間と交通費がかかるため、**現地に着いてから「違った」では取り返しがつかない**。
移動に制約がある人にとっては、この空振りのコストがさらに大きい。

## 提供する価値

### 1. 真正性の提示(コア)

複数の情報源を横断して収集し、**「なぜここが聖地と言えるのか」の根拠を出典 URL 付きで提示する**。
AI が断定するのではなく、利用者が自分で確かめられる形にする。

根拠の強さを 3 段階で表示し、強い順に並べる。

| ランク | 定義 | 例 |
|---|---|---|
| **A: 本人発信** | メンバー本人が発信している | 本人ブログ、本人 SNS、公式動画に映っている |
| **B: 公式・報道** | 第三者による公式な記録 | テレビ番組、雑誌、店舗側の来店告知 |
| **C: ファン推定** | ファンによる特定 | 背景の一致、目撃情報 |

C には「推定」と明示する。これにより **古い情報や根拠の弱い情報が上位に来る問題を構造的に防ぐ**。

### 2. 絞り込み

各レコードが「誰が」「いつ」を保持するため、次の絞り込みが成立する。

- **メンバー別**(卒業メンバーを含む/除く の切り替え)
- **期間**(例: 直近1年の訪問のみ)
- 距離・エリア

### 3. アクセシビリティ(追加レイヤー)

**車椅子ユーザー専用サービスではない。** 誰でも使える聖地巡礼サービスの上に、
「車椅子で行けるか」も判定できる機能が乗る形とする。

必要な人には決定的な情報になり、不要な人の体験を妨げない。

## データ項目

聖地 1 件あたりが持つ情報。

| 項目 | 内容 | 用途 |
|---|---|---|
| 場所 | 店名・住所・座標 | 地図表示、ルート算出 |
| 誰が | メンバー名、卒業済みか | メンバー別の絞り込み |
| いつ | 訪問日 | 期間での絞り込み、鮮度の判定 |
| 根拠 | 出典 URL、種別 | 真正性の提示 |
| 根拠ランク | A / B / C | 並び順、信頼度の明示 |
| アクセシビリティ | 入口・トイレ・座席・駐車場 | 追加レイヤー |

## 技術構成(案)

ハッカソンの必須要件は ①実行環境(Cloud Run 等) ②AI 技術(Gemini API 等) の 2 カテゴリ[^zenn-hackathon-page]。

| 用途 | 採用技術 | 備考 |
|---|---|---|
| 聖地情報の収集 | **Grounding with Google Search**(Gemini API) | リアルタイムの Web 検索。**出典 URL が付く**[^search-grounding] |
| 場所・経路の解決 | **Grounding with Google Maps**(Gemini API) | 場所・レビュー・写真・住所・営業時間に加え、2026年に経路・所要時間も正式対応[^maps-grounding] |
| アクセシビリティ判定 | **Places API (New) の `accessibilityOptions`** | 入口・トイレ・座席・駐車場の 4 項目を構造化データで取得[^places-accessibility] |
| 実行環境 | Cloud Run | 必須要件①を満たす |

### X (Twitter) API を使わない判断

当初は X からの情報収集を想定していたが、次の理由で採用しない。

- **2026年2月に無料枠が廃止**され、新規開発者は従量課金のみ(読み取り $0.005/件)[^x-api-pricing]
- 投稿は出典としての信頼性を担保しにくく、本コンセプトの核である「真正性の提示」と相性が悪い
- Grounding with Google Search であれば**出典 URL 付きで、配布される Google Cloud クレジットの範囲内**で実現できる

「リアルタイムに情報を取りに行く」という当初の意図は、Search Grounding で満たされる。

## 差別化と、チームの懸念への応答

フェーズ2の議論で、**「分身エージェントがどこまで正確に実体験を取れるのか不明。審査で指摘されうる」**
という懸念が出ている[^phase2-brushup]。

本コンセプトは、その問いに**最初から根拠で答える構造**を持つ。

- 聖地情報は出典 URL 付きで提示する
- アクセシビリティ判定は Google の構造化データを根拠とし、推測ではない

「AI が想像で言っている」のではなく「この情報源にこう書かれている」と示せることが、
審査における説明力になる。

## やらないこと(スコープ外)

時間内に作り切るため、以下は対象外とする。

- 全アイドルグループへの対応(デモは特定グループに絞る)
- 完全自動のクローリングと大規模な聖地データベース構築
- 予約・決済などの実行系機能
- 多言語対応(翻訳は将来の拡張候補)

## 未決事項

- デモ対象とするグループとメンバーの範囲
- 根拠ランクの判定を誰が(どのモデル・どのルールで)行うか
- ユーザーによるアクセシビリティ情報の追記機能を、今回の範囲に含めるか
- チームの `michibiki` プロトタイプとの統合方針、あるいは独立した提案として扱うか

[^phase2-brushup]: docs/wiki/concepts/steering.md
[^zenn-hackathon-page]: https://zenn.dev/hackathons/google-cloud-japan-ai-hackathon-vol5
[^x-api-pricing]: https://postproxy.dev/blog/x-api-pricing-2026/
[^search-grounding]: https://ai.google.dev/gemini-api/docs/google-search
[^maps-grounding]: https://ai.google.dev/gemini-api/docs/maps-grounding
[^places-accessibility]: https://mapsplatform.google.com/resources/blog/introducing-the-new-places-api-with-access-to-new-ev-accessibility-features-and-more/
