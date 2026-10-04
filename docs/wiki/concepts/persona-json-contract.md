---
type: decision
title: "他エージェント向けpersona JSON契約"
status: stable
owner: yu-juhun
generated:
  by: claude
  at: 2026-09-27
sources:
  - id: persona-avatar-v3-design
    resource: docs/superpowers/specs/2026-09-27-persona-avatar-v3-design.md
    title: "Persona Avatar v3 (JSON contract validation + avatar visualization policy) Design"
    credibility_signals: "team-internal-agreement"
---

# 他エージェント向けpersona JSON契約

## 概要

`persona-agent-backend` が `finish` 時に生成する `Persona` JSON は、アバター画像とは独立に、
他エージェントが「このユーザーが誰か」を判断するための入力データとして使われる。
他エージェントはアバター画像そのものは消費しない — このJSONのみを見る。

スキーマの正本は [`persona-agent-backend/schemas.py`](../../../persona-agent-backend/schemas.py) とする。

## 決定/結論

- `domain` は固定7値のいずれか(`mobility` / `dietary` / `purpose` / `companions` /
  `language` / `background` / `other`)。`category`/`description` は自由形式のテキスト。
- `rank` は1から始まる整数で、全 `attributes` を通じて一意。数字が小さいほど重要。
  一意性は `persona_validator.validate_persona` がコードで保証する(重複時はGeminiへの
  1回の再要求、それでも解決しない場合は出現順に再割り当てするフォールバックが動く)。
- `confidence` の解釈:
  - `high` / `medium`: 判断の根拠として使ってよい
  - `low`: あくまで参考情報として扱い、判断の主根拠にしない
- `domain == "other"` は固定7カテゴリに当てはまらない情報。他エージェントは無視してよい
  (必須の解釈ではない)。
- `schema_version` フィールド(現在 `"2"`)を持つ。将来の破壊的スキーマ変更時にこの値を
  インクリメントする。他エージェントはこの値で自分が対応しているスキーマかどうかを判定できる。

## 経緯・議論

`rank`/`confidence` の意味と一意性保証は、v1/v2実装当時はプロンプト文言としてのみ存在し、
コードでの検証も他エージェント向けの明文化もされていなかった。アバター画像の視覚化ポリシー
([avatar-visualization-policy](./avatar-visualization-policy.md) 参照)と合わせて、persona-avatar v3
設計([`2026-09-27-persona-avatar-v3-design.md`](../../superpowers/specs/2026-09-27-persona-avatar-v3-design.md))
で構造的な保証として追加した。
