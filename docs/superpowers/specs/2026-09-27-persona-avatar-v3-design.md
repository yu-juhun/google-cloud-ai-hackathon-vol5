# Persona Avatar v3 (JSON contract validation + avatar visualization policy) Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this into a task-by-task implementation plan before implementing.

## 背景・スコープ

v1/v2 (`2026-09-13-persona-intake-agent.md`, `2026-09-14-persona-avatar-v2.md`) で YouCam 基本アバター + Nano Banana 進化 + `domain`/`rank` スキーマまでは実装済み。本設計はその実装を維持したまま、以下2トラックの「構造的な保証」を追加する。

このアバター機能の出力物には2つの役割がある:
- **トラックA — persona JSON**: 他エージェントが「このユーザーが誰か」を判断するための入力データ (`domain`/`rank`/`attributes`)。他エージェントはアバター画像そのものは消費しない。
- **トラックB — アバター画像**: アプリ内でユーザーを表すキャラクター(UX目的のみ)。

**明示的にスコープ外**: 「アバターを仮想的にどこかへ訪問させてフィードバックを生成する」機能(中村さんの個別コンセプト)は本設計に含まない。

対象ペルソナは特定のケース(車椅子ユーザー等)に限定しない汎用設計とする。

## トラックA: persona JSON

### 現状の問題

- `rank` が全 attributes を通じて一意であるという要件はプロンプト文言のみで強制されており、コードでの検証がない。
- `confidence`/`domain=other` を他エージェントがどう解釈すべきかの契約が文書化されていない。
- `schema_version` フィールドがなく、将来のスキーマ変更を他エージェントが検知できない。

### 設計

**新規: `persona-agent-backend/persona_validator.py`**

```python
def validate_persona(persona: Persona) -> list[str]:
    """Returns a list of human-readable violation messages (empty = valid).
    Checks: rank uniqueness across all attributes.
    """
```

**変更: `persona-agent-backend/persona_extraction.py`**

`extract_persona` は Gemini 応答をパースした後 `validate_persona` を呼ぶ:
1. 違反なし → そのまま返す。
2. 違反あり → 違反内容を含めた修正依頼で Gemini に**1回だけ**再要求する。
3. 再要求後も違反あり → 例外を投げず、`rank` を配列の出現順(1-based)で強制的に再割り当てするフォールバックを適用し、ログに違反内容を記録して返す。他エージェントへのデータフローを止めない。

**変更: `persona-agent-backend/schemas.py`**

`Persona` に `schema_version: str = "2"` を追加(既存フィールドは変更しない → 後方互換)。

**新規: `docs/wiki/concepts/persona-json-contract.md`**

`recommendation-api-contract.md` と同じ体裁で、他エージェント向けに以下を明文化する:
- `confidence`: `low` は参考情報として扱い判断の主根拠にしない。`high`/`medium` は判断に使ってよい。
- `rank`: 数字が小さいほど重要。全 attributes を通じて一意(バリデータが保証)。
- `domain=other`: 固定7カテゴリに当てはまらない情報。他エージェントは無視してよい(必須の解釈ではない)。
- `schema_version`: 将来の破壊的変更時にインクリメントする。

### テスト

`persona-agent-backend/tests/test_persona_validator.py`:
- rank 重複 → 違反を返す
- rank 一意 → 空リストを返す

`persona-agent-backend/tests/test_persona_extraction.py` に追加:
- 1回目の Gemini 応答が rank 重複 → 2回目の呼び出しが発生し、その結果が採用される
- 2回目も rank 重複 → フォールバックで出現順の rank が再割り当てされる(例外を投げない)

## トラックB: アバター画像

### 現状の問題

- `evolve_avatar` は `persona.attributes` を無条件に全件プロンプトへ列挙しており、`domain`/`rank`/`confidence` を一切参照しない。
- 宗教・出身地等 (`background`) のような属性がそのまま画像編集プロンプトに渡り、モデルが自己判断でステレオタイプ的な外見(宗教的装束など)を追加するリスクがある。
- 最重要属性 (`rank=1`) が他の属性と同じ重みで扱われ、埋没する可能性がある。

### 設計

**新規: `persona-agent-backend/avatar_policy.py`**

```python
VISUALIZABLE_DOMAINS: set[Domain] = {"mobility"}
# 他ドメインを視覚化対象に加える場合は、この1箇所のみを変更する。

def select_visual_attributes(persona: Persona) -> list[Attribute]:
    """Filters to VISUALIZABLE_DOMAINS, drops confidence == "low",
    sorts ascending by rank."""

def build_edit_instructions(attrs: list[Attribute]) -> str:
    """Renders attrs into prompt text: the lowest-rank attribute is
    marked "必ず反映" (must reflect), the rest "可能なら反映"
    (reflect if natural). Returns "" if attrs is empty."""
```

**変更: `persona-agent-backend/avatar_generation.py`**

`evolve_avatar` は `persona.attributes` を直接列挙する代わりに `avatar_policy.select_visual_attributes` → `avatar_policy.build_edit_instructions` を呼ぶ。`build_edit_instructions` が空文字を返す場合(視覚化対象なし)は、現状と同様に base 画像をそのまま返す(Gemini 呼び出しをスキップ)。

### テスト

`persona-agent-backend/tests/test_avatar_policy.py`:
- `mobility` は通過、`dietary`/`background`/`purpose`/`companions`/`language`/`other` は除外される
- `confidence="low"` の attribute は除外される
- 複数の `mobility` attribute がある場合、rank 昇順に並び、最小 rank のものだけ「必ず反映」文言になる
- 視覚化対象が0件のとき空文字を返す

`persona-agent-backend/tests/test_avatar_generation.py` に追加:
- `evolve_avatar` が視覚化対象なしの persona を渡されたとき、Gemini を呼ばずに base 画像を返す(既存モックを `avatar_policy` 経由に更新)

## 変更しないもの

- WebSocket メッセージ契約(`main.py` の `persona_result` 等)は変更しない — フィールド追加なし、フロントエンドは無変更で動作継続。
- YouCam 連携 (`youcam_client.py`)、デフォルトアバター (`default_avatar.py`)、生成タイミング(写真送信時に YouCam 1回、finish 時に Nano Banana 1回)は変更しない。
- 「仮想訪問フィードバック生成」機能は追加しない(スコープ外)。

## 将来課題(今回は実装しない)

- トラックB: 生成後にユーザーが確認・再生成できるプレビュー承認ループ(finish 時1回生成という現在の流れを変える必要があるため)。
- トラックA: 2段階抽出(抽出 → 自己批判で rank/confidence を再検証)。品質は上がるが遅延・コストが増える。
