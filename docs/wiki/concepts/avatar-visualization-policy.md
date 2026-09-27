---
type: decision
title: "アバター画像の視覚化ドメイン許可リスト"
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

# アバター画像の視覚化ドメイン許可リスト

## 概要

`persona-agent-backend` のアバター画像(アプリ内でユーザーを表すキャラクター)は、
persona属性のうち一部のドメインだけを外見に反映してよい。この許可リストは
[`persona-agent-backend/avatar_policy.py`](../../../persona-agent-backend/avatar_policy.py)
の `VISUALIZABLE_DOMAINS` が正本。

## 決定/結論

- 現在 `VISUALIZABLE_DOMAINS = {"mobility"}` のみ。他の6ドメイン
  (`dietary` / `purpose` / `companions` / `language` / `background` / `other`)は
  アバター画像編集プロンプトに一切渡さない。
- 視覚化対象に選ばれた属性の中でも、`confidence == "low"` のものは除外し、
  `rank` が最小(最重要)のものだけ「必ず反映」、残りは「可能なら反映」と
  Nano Banana への指示を差別化する(`build_edit_instructions`)。

## 経緯・議論

`background`(宗教・出身地・国籍等)のような属性をそのまま画像編集プロンプトに渡すと、
画像生成モデルが宗教的装束など、ユーザーが実際には求めていない見た目をステレオタイプ的に
追加してしまうリスクがある。この許可リストはそのリスクを構造的に防ぐための仕組みで、
プロンプト文言の工夫だけに頼らない。

`mobility` は本サービスの核心的な提供価値(移動制約に配慮した体験提案)に直結するため、
最初から許可リストに含める。他のドメインを視覚化対象に加えるかどうかは、
今回のプロジェクトの担当領域(劉さん個別コンセプト: アバターUI/UX担当)を超える判断になるため、
`VISUALIZABLE_DOMAINS` を変更する際は変更前にこのページを更新し、チームに共有すること。
